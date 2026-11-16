frappe.pages['siraj-explorer'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __('SIRAJ Explorer'), single_column: true });
	new SirajExplorer(page);
};

class SirajExplorer {
	constructor(page) {
		this.page = page;
		this.root = $('<div class="siraj-explorer"></div>').appendTo(page.main);
		this.kind = 'geography';
		this.map = null;
		this.network = null;
		// All type colours/glyphs come from the global registry so every
		// surface (map, graph, deck, lists) stays consistent.
		this.colors = window.sirajColours || {};
		this.render();
	}

	escape(value) { return $('<div>').text(value == null ? '' : String(value)).html(); }
	id(node) { return JSON.stringify([node.doctype, node.name]); }
	t(label) { return this.escape(__(label)); }
	button(text, handler, primary = false) {
		const b = $('<button type="button" class="btn btn-sm"></button>').addClass(primary ? 'btn-primary' : 'btn-default').text(text);
		b.on('click', handler);
		return b;
	}
	async render() {
		if (this.downloadController) { this.downloadController.abort(); this.downloadController = null; }
		if (this.map) { this.map.remove(); this.map = null; }
		if (this.network) { this.network.destroy(); this.network = null; }
		const renderId = this.renderId = (this.renderId || 0) + 1;
		this.root.empty();
		const tabs = $('<div class="sx-tabs"></div>').appendTo(this.root);
		[['geography', __('Geographic map')], ['relationships', __('Relationship map')], ['structures', __('Structures')]].forEach(([key, title]) => {
			this.button(title, () => { this.kind = key; this.render(); }).toggleClass('active', this.kind === key).appendTo(tabs);
		});
		this.tools = $('<div class="sx-tools"></div>').appendTo(this.root);
		this.note = $('<div class="sx-note" role="status"></div>').text(__('Loading…')).appendTo(this.root);
		this.legend = $('<div class="sx-legend"></div>').appendTo(this.root);
		const layout = $('<div class="sx-layout"></div>').toggleClass('sx-layout-geo', this.kind === 'geography').toggleClass('sx-layout-relationships', this.kind === 'relationships').appendTo(this.root);
		this.rail = this.kind === 'relationships' ? $('<aside class="sx-atlas-rail"></aside>').appendTo(layout) : null;
		this.records = this.kind === 'geography' ? $('<aside class="sx-records"></aside>').appendTo(layout) : null;
		this.canvas = $('<div class="sx-canvas"></div>').appendTo(layout);
		this.aside = $('<aside class="sx-aside"></aside>').appendTo(layout);
		try {
			if (this.kind === 'structures') {
				await this.structures(renderId);
			} else if (this.kind === 'geography') {
				// A failing data endpoint must not prevent the local base map loading.
				let data = { points: [], edges: [], truncated: [], unavailable: false };
				try {
					const res = await frappe.call({ method: 'siraj_research.visualization.geographic_data' });
					if (res && res.message && typeof res.message === 'object') {
						data = Object.assign(data, res.message);
					}
					if (!Array.isArray(data.points)) data.points = [];
					if (!Array.isArray(data.edges))  data.edges  = [];
				} catch (error) {
					console.error('[SIRAJ Explorer] geographic_data failed:', error);
					data = { points: [], edges: [], truncated: [], unavailable: true, error: (error && error.exception) || (error && error.message) || String(error) };
				}
				if (renderId === this.renderId) await this.geography(data, renderId);
			} else {
				const res = await frappe.call({ method: 'siraj_research.visualization.relationship_data' });
				if (renderId === this.renderId) await this.relationships(res.message, renderId);
			}
		} catch (error) {
			if (renderId !== this.renderId) return;
			console.error('[SIRAJ Explorer] render failed:', error);
			this.note.addClass('sx-warning')
				.html(
					$('<div></div>').text(__('Unable to load the explorer.')).append(' ')
						.append($('<code style="font-size:11px;opacity:0.8"></code>').text(String((error && error.exception) || (error && error.message) || error)))
				);
			// Keep the layout skeleton intact so the user can retry rather than
			// seeing a crushed column.
			if (this.canvas && !this.canvas.children().length) {
				$('<div class="sx-empty-state"></div>')
					.css({padding:'48px', textAlign:'center', color:'var(--text-muted)'})
					.text(__('Map shell is ready but data failed to load.'))
					.appendTo(this.canvas);
			}
		}
	}
	warning(data) {
		if (data.truncated && (Array.isArray(data.truncated) ? data.truncated.length : data.truncated)) {
			return __('Results are limited to {0} visible records per type; the view is incomplete.', [data.limit]);
		}
		return '';
	}
	showDetails(title, rows, target) {
		this.aside.empty();
		$('<h4></h4>').text(title).appendTo(this.aside);
		const dl = $('<dl></dl>').appendTo(this.aside);
		rows.forEach(([label, value]) => {
			if (value === null || value === undefined || value === '') return;
			$('<dt></dt>').text(label).appendTo(dl);
			$('<dd></dd>').text(value).appendTo(dl);
		});
		if (target) this.button(__('Open record'), () => frappe.set_route('Form', target.doctype, target.name), true).addClass('sx-open').appendTo(this.aside);
	}
	showLegend(types, icons = null) {
		types.forEach(type => {
			const item = $('<span class="sx-legend-item"></span>').appendTo(this.legend);
			if (icons && icons[type]) {
				// SVG fragments are fixed application constants, never record data.
				$('<span class="sx-map-pin sx-legend-pin"><svg viewBox="0 0 24 24" aria-hidden="true">' + icons[type] + '</svg></span>').css('background', this.colors[type]).appendTo(item);
			} else $('<i class="sx-pin-key"></i>').css('background', this.colors[type]).appendTo(item);
			item.append(document.createTextNode(__(type)));
		});
	}
	filterControls(types, onChange, host = this.tools) {
		const search = $('<input class="form-control input-sm" type="search">').attr('placeholder', __('Search records')).appendTo(host);
		const select = $('<select class="form-control input-sm"></select>').appendTo(host);
		$('<option value=""></option>').text(__('All types')).appendTo(select);
		types.forEach(type => $('<option></option>').val(type).text(__(type)).appendTo(select));
		search.on('input', () => onChange(search.val(), select.val()));
		select.on('change', () => onChange(search.val(), select.val()));
		return {search, select};
	}
	async geography(data, renderId) {
		// Explicitly require shared map assets here. In page contexts (like
		// /app/siraj-explorer) app_include_js load order is not guaranteed to
		// have completed by the time page JS runs, so we list them explicitly.
		await frappe.require([
			'/assets/siraj_research/vendor/leaflet/leaflet.css',
			'/assets/siraj_research/vendor/leaflet/leaflet.js',
			'/assets/siraj_research/vendor/leaflet-markercluster/leaflet.markercluster.js',
			'/assets/siraj_research/vendor/topojson/topojson-client.min.js',
			'/assets/siraj_research/js/siraj-map-kit.js',
			'/assets/siraj_research/js/siraj-map-toolbar.js',
			'/assets/siraj_research/css/siraj-map-toolbar.css',
			'/assets/siraj_research/css/siraj-icons.css',
			'/assets/siraj_research/css/siraj_explorer.css',
		]);
		if (renderId !== this.renderId) return;
		const Kit = window.SirajMapKit;
		const map = this.map = L.map(this.canvas[0], { worldCopyJump: true, preferCanvas: true, minZoom: 0, maxZoom: 22, zoomAnimation: false, zoomControl: false }).setView([33.3152, 44.3661], 4);
		L.control.scale({ imperial: false, position: 'bottomleft' }).addTo(map);
		const dms = (value, latitude) => {
			const n = Number(value), tenths = Math.round(Math.abs(n) * 36000);
			const d = Math.floor(tenths/36000), m = Math.floor((tenths%36000)/600), s = ((tenths%600)/10).toFixed(1);
			return d + '° ' + m + '′ ' + s + '″ ' + (latitude ? (n<0?'S':'N') : (n<0?'W':'E'));
		};
		const mapStatus = (text, warn) => {
			if (this.toolbar) this.toolbar.status(text, warn ? 'warning' : null);
			if (this.note) this.note.text(text).toggleClass('sx-warning', !!warn);
		};
		let offlineLayer = null, onlineLayer = null, localPackLayer = null, selectedCircle = null;
		// Basemap
		try {
			const response = await fetch('/assets/siraj_research/vendor/world-atlas/countries-110m.json');
			if (!response.ok) throw new Error('offline basemap HTTP ' + response.status);
			const world = await response.json();
			if (renderId !== this.renderId) return;
			offlineLayer = L.geoJSON(topojson.feature(world, world.objects.countries), {
				interactive: false, style: { color:'#a4b4a8', weight:0.7, fillColor:'#e8e4cf', fillOpacity:1 }
			}).addTo(map);
			map.attributionControl.addAttribution('Natural Earth / world-atlas');
			mapStatus(__('Offline basemap: Natural Earth, low detail.'));
		} catch (err) {
			console.error(err);
			if (renderId !== this.renderId) return;
			mapStatus(__('Local basemap could not be loaded. You can still use the markers or enable online tiles.'), true);
		}
		// Icons
		const pointIcon = p => L.divIcon({
			className: 'sx-pin-wrapper', iconSize:[36,36], iconAnchor:[18,18],
			html: window.sirajIcons.pin(p.doctype, this.colors[p.doctype], 36)
		});
		const itemGlyph = doctype => {
			const c = this.colors[doctype] || '#6a7a7e';
			return `<span class="sx-item-glyph" style="background:${c}">${(window.sirajIcons ? window.sirajIcons.svg(doctype,{size:12}) : '')}</span>`;
		};
		const types = [...new Set(data.points.map(p => p.doctype))];
		this.showLegend(types, window.sirajIcons ? window.sirajIcons.types : null);
		let clustered = true, overlayEnabled = false, currentPoints = [], searchTerm = '', selectedType = '', listLimit = 100;
		const pointsById = new Map();
		data.points.forEach(p => pointsById.set(this.id(p), p));

		// Geography uses a two-column grid (full-width canvas + details aside),
		// hiding the legacy sx-records left column since records now live in the
		// in-map app panel. The previous 3-column grid with a hidden column was
		// leaving a 220px crushed gap (S4).
		this.root.find('.sx-layout').addClass('sx-no-records').removeClass('sx-no-details');
		if (this.records) this.records.hide();
		// ------ App panel (records + filters + export) — overlay over the map canvas ------
		const appPanel = $('<div class="sx-app-panel"></div>');
		const recSection = $('<div class="sx-app-section"></div>').appendTo(appPanel);
		const recordHeading = $('<h5></h5>').text(__('Mapped records')).appendTo(recSection);
		const searchBox = $('<input type="search" class="form-control input-sm" style="width:100%;box-sizing:border-box;margin-bottom:6px" placeholder="' + __('Search records') + '">').appendTo(recSection);
		const typeSel = $('<select class="form-control input-sm" style="width:100%;box-sizing:border-box;margin-bottom:6px"><option value="">' + __('All types') + '</option></select>').appendTo(recSection);
		types.forEach(t => $('<option></option>').val(t).text(__(t)).appendTo(typeSel));
		const recordList = $('<div></div>').css({maxHeight:'40vh',overflow:'auto'}).appendTo(recSection);
		const listMore = this.button(__('Show more'), () => { listLimit += 100; renderList(); }).appendTo(recSection);
		const dataSection = $('<div class="sx-app-section"></div>').appendTo(appPanel);
		$('<h5></h5>').text(__('Data')).appendTo(dataSection);
		const exportBtn = this.button(__('Export GeoJSON'), () => {
			const geojson = { type:'FeatureCollection', features: currentPoints.map(p => ({
				type:'Feature', geometry:{ type:'Point', coordinates:[Number(p.longitude),Number(p.latitude)] },
				properties:{ doctype:p.doctype, name:p.name, label:p.label, precision:p.geo_precision, method:p.geocoding_method, uncertainty_m:p.geo_uncertainty_m, source:p.geometry_source }
			})) };
			const url = URL.createObjectURL(new Blob([JSON.stringify(geojson)],{type:'application/geo+json'}));
			const a = document.createElement('a'); a.href=url; a.download='siraj-visible-points.geojson'; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
		}).appendTo(dataSection);
		appPanel.appendTo(this.canvas);
		// Close button so the panel can be dismissed.
		$('<button type="button" class="close" style="position:absolute;top:6px;right:8px" aria-label="' + __('Close panel') + '">×</button>').prependTo(appPanel).on('click', () => appPanel.hide());

		const selectPoint = p => {
			if (selectedCircle) { map.removeLayer(selectedCircle); selectedCircle = null; }
			const r = Number(p.geo_uncertainty_m);
			if (Number.isFinite(r) && r>0 && r<=1000000) selectedCircle = L.circle([p.latitude,p.longitude],{radius:r,color:this.colors[p.doctype],fillOpacity:0.1,interactive:false}).addTo(map);
			this.showDetails(p.label, [[__('Type'),__(p.doctype)],[__('ID'),p.name],[__('Latitude'),p.latitude],[__('Longitude'),p.longitude],[__('DMS'),dms(p.latitude,true)+' / '+dms(p.longitude,false)],[__('Coordinate precision'),p.geo_precision],[__('Method'),p.geocoding_method],[__('Uncertainty radius (m)'),p.geo_uncertainty_m],[__('Source'),p.geometry_source]],p);
			if (this.relLayer && this.relLayer.setEgo) { this.relLayer.setEgo(this.id(p)); }
		};
		const renderList = () => {
			recordHeading.text(__('Mapped records ({0})',[currentPoints.length]));
			recordList.empty();
			currentPoints.slice(0, listLimit).forEach(p => {
				const b = $('<button type="button"></button>').on('click', () => {
					selectPoint(p); map.panTo([Number(p.latitude),Number(p.longitude)]);
				}).appendTo(recordList);
				b.addClass('sx-record-item').attr('title',__(p.doctype)+' · '+p.name)
					.html(itemGlyph(p.doctype) + '<span class="sx-item-label">' + this.escape(p.label) + '</span>'
						+ '<span class="sx-item-type" style="margin-inline-start:auto;font-size:10px;color:var(--text-muted);padding:2px 6px;border-radius:999px;background:'+this.colors[p.doctype]+';color:#fff;opacity:0.85">'+__(p.doctype)+'</span>');
			});
			listMore.toggle(currentPoints.length > listLimit);
		};

		// Relationship overlay (shared RelLayer).
		let relData = null;
		this.relLayer = new Kit.RelLayer(map, { pointsById });
		this.relLayer.onEdgeClick = edge => {
			const a = pointsById.get(JSON.stringify(edge.source)), b = pointsById.get(JSON.stringify(edge.target));
			this.showDetails(edge.type || __('Relationship'), [
				[__('Subject'), a ? a.label : JSON.stringify(edge.source)],
				[__('Object'),  b ? b.label : JSON.stringify(edge.target)],
				[__('Direction'), edge.direction],[__('Description'), edge.description],[__('Status'), edge.state],
			], {doctype:'Relationship', name:edge.name});
		};
		const ensureRelData = async () => {
			if (relData) return relData;
			relData = (await frappe.call({method:'siraj_research.visualization.relationship_data'})).message;
			this.relLayer.setEdges(relData.edges || []);
			relData.edges.forEach(e => { if (e.type) this.relLayer.registerType(e.type, this.colors.Relationship || '#53706b', null); });
			return relData;
		};

		// Marker cluster layer
		let markers = L.markerClusterGroup({
			maxClusterRadius:45, showCoverageOnHover:false, spiderfyOnMaxZoom:true,
			iconCreateFunction: c => L.divIcon({className:'sx-cluster', html:'<span>'+c.getChildCount()+'</span>', iconSize:[40,40]})
		}).addTo(map);
		const draw = () => {
			if (selectedCircle) { map.removeLayer(selectedCircle); selectedCircle=null; }
			markers.clearLayers();
			const term = searchTerm.toLocaleLowerCase();
			currentPoints = data.points.filter(p => (!selectedType || p.doctype===selectedType) && (p.label+' '+p.name).toLocaleLowerCase().includes(term));
			currentPoints.forEach(p => {
				const m = L.marker([Number(p.latitude),Number(p.longitude)],{icon:pointIcon(p),title:p.label,keyboard:true});
				m.bindTooltip(this.escape(p.label));
				m.on('click', () => selectPoint(p));
				markers.addLayer(m);
			});
			// Rebuild pointsById for the current set so rel layer resolves correctly.
			pointsById.clear();
			currentPoints.forEach(p => pointsById.set(this.id(p), p));
			const text = data.unavailable ? __('Record data could not be loaded.') : __('Showing {0} record points.',[currentPoints.length]) + ' ' + this.warning(data);
			this.note.toggleClass('sx-warning',!!data.unavailable).text(text);
			renderList();
			this.relLayer.redraw();
		};
		searchBox.on('input', () => { searchTerm = searchBox.val(); listLimit = 100; draw(); });
		typeSel.on('change', () => { selectedType = typeSel.val(); listLimit = 100; draw(); });

		// ------ Measurement tool (shared state machine, single-click model) ------
		const measure = new Kit.MeasureTool(map, { onStatus: mapStatus });

		// ------ Pick-to-link flow ------
		const startPick = () => {
			mapStatus(__('Click a point to link it to an existing or new record.'));
			measure.onPick = async latlng => {
				measure.onPick = null;
				const dlg = new frappe.ui.Dialog({
					title: __('Link a record to this point'),
					fields: [
						{ fieldname:'doctype', label:__('Record type'), fieldtype:'Select', options:types.join('\n'), reqd:1 },
						{ fieldname:'target',  label:__('Record'),      fieldtype:'Link',   options:'Person', depends_on:'eval:doc.doctype', reqd:1,
						  description: __('Leave blank to create a new record after saving.') },
						{ fieldname:'note',    label:__('Note'),        fieldtype:'Small Text' },
					],
					primary_action_label: __('Set coordinates'),
					primary_action: async vals => {
						if (!vals.doctype) return;
						if (vals.target) {
							try {
								await frappe.call({ method:'frappe.client.set_value', args: {
									doctype: vals.doctype, name: vals.target,
									fieldname: { latitude: Number(latlng.lat).toFixed(6), longitude: Number(latlng.lng).toFixed(6), geocoding_method:'map_pick' }
								}});
								frappe.show_alert({message:__('Coordinates updated for {0}',[vals.target]), indicator:'green'});
								dlg.hide();
								draw();
							} catch (e) { frappe.msgprint(__('Could not update: ') + (e.message||e)); }
						} else {
							frappe.new_doc(vals.doctype, { latitude: Number(latlng.lat).toFixed(6), longitude: Number(latlng.lng).toFixed(6), geocoding_method:'map_pick' });
							dlg.hide();
						}
					}
				});
				// Update the Link field's options when doctype changes.
				dlg.fields_dict.doctype.$input.on('change', () => {
					const dt = dlg.get_value('doctype');
					if (dt && dlg.fields_dict.target) {
						dlg.fields_dict.target.df.options = dt;
						dlg.fields_dict.target.refresh();
					}
				});
				dlg.show();
				// Display the clicked point temporarily so the user sees what they picked.
				L.circleMarker(latlng,{radius:6,color:'#1a6670',weight:2,fillColor:'#1a6670',fillOpacity:0.4}).addTo(map).bindTooltip(dms(latlng.lat,true)+' · '+dms(latlng.lng,false)).openTooltip();
			};
			measure.activate('pick');
		};

		// ------ In-map toolbar (MAP TOOLS ONLY) ------
		this.toolbar = L.control.sirajToolbar({ position:'topright' }).addTo(map);
		const localPacks = new Map();
		const toggleBtn = (key, on) => { const b=this.toolbar._buttons && this.toolbar._buttons.get(key); if (b) b.classList.toggle('is-active',!!on); };

		// Navigate
		this.toolbar.group(__('Navigate'))
			.add({ icon:'zoom_in',   label:__('In'),    action: () => map.zoomIn() })
			.add({ icon:'zoom_out',  label:__('Out'),   action: () => map.zoomOut() })
			.add({ icon:'home',      label:__('Home'),  action: () => map.setView([33.3152,44.3661],4) })
			.add({ icon:'fit',       label:__('Fit'),   action: () => {
				if (currentPoints.length) map.fitBounds(L.latLngBounds(currentPoints.map(p=>[Number(p.latitude),Number(p.longitude)])).pad(0.15),{maxZoom:12});
			}})
			.add({ icon:'locate_me', label:__('My loc'),action: () => map.locate({setView:true,maxZoom:12,enableHighAccuracy:true}) })
			.add({ icon:'locate',    label:__('Coords'),menuTitle:__('Go to coordinates'), menu: pop => {
				const w=$('<div></div>').appendTo(pop);
				const row=$('<div style="display:flex;gap:4px"></div>').appendTo(w);
				const lat=$('<input type="number" step="any" min="-90" max="90" class="form-control input-sm" placeholder="'+__('Lat')+'">').appendTo(row);
				const lon=$('<input type="number" step="any" min="-180" max="180" class="form-control input-sm" placeholder="'+__('Lon')+'">').appendTo(row);
				$('<button type="button" class="btn btn-sm btn-primary" style="margin-top:4px">'+__('Go')+'</button>').appendTo(w).on('click',()=>{
					const la=Number(lat.val()),lo=Number(lon.val());
					if (![la,lo].every(Number.isFinite)||Math.abs(la)>90||Math.abs(lo)>180) return;
					map.setView([la,lo],Math.max(8,map.getZoom()));
				});
			}});

		// Basemap
		const selectBasemap = val => {
			if (onlineLayer) { map.removeLayer(onlineLayer); onlineLayer=null; }
			if (localPackLayer) { map.removeLayer(localPackLayer); localPackLayer=null; }
			map.setMinZoom(0);
			const pack = localPacks.get(String(val).replace(/^pack-/,''));
			if (pack) {
				if (offlineLayer) map.removeLayer(offlineLayer);
				map.setMinZoom(pack.minzoom);
				localPackLayer = L.tileLayer('/api/method/siraj_research.local_maps.tile?kind='+encodeURIComponent(pack.kind)+'&z={z}&x={x}&y={y}',{minZoom:pack.minzoom,maxZoom:22,maxNativeZoom:pack.maxzoom,attribution:pack.attribution||''}).addTo(map);
				localPackLayer.on('tileerror',()=>mapStatus(__('Some local tiles are unavailable.'),true));
			} else if (val==='online') {
				if (offlineLayer) map.removeLayer(offlineLayer);
				onlineLayer = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:22,maxNativeZoom:19,attribution:'&copy; OpenStreetMap contributors'}).addTo(map);
				mapStatus(__('Online tiles disclose your IP to OpenStreetMap.'));
			} else {
				if (offlineLayer) offlineLayer.addTo(map).bringToBack();
			}
		};
		this.toolbar.group(__('Basemap'))
			.add({ icon:'layers', label:__('Basemap'), menuTitle:__('Basemap'), menu: pop => {
				const w=$('<div></div>').appendTo(pop);
				const opt=(val,icon,label,active)=>{
					const b=$('<button type="button" class="siraj-toolbar-opt"></button>').html(window.sirajIcons.toolSvg(icon,{size:16})+'<span>'+label+'</span>');
					if (active) b.addClass('is-active');
					b.on('click',()=>{w.find('.is-active').removeClass('is-active');b.addClass('is-active');selectBasemap(val);});
					b.appendTo(w); return b;
				};
				opt('local','offline',__('Offline'),true);
				opt('online','online',__('Online: OSM'),false);
				$('<hr>').appendTo(w);
				frappe.call({method:'siraj_research.local_maps.available_packs',type:'GET',silent:true}).then(res=>{
					if (!Array.isArray(res.message)) return;
					res.message.forEach(pack=>{
						if (pack.unavailable||!['standard','aerial'].includes(pack.kind)) return;
						localPacks.set(pack.kind,pack);
						opt('pack-'+pack.kind,'layers',pack.kind==='aerial'?__('Local aerial'):__('Local standard'),false);
					});
				}).catch(()=>{});
			}});
		this.toolbar.separator();

		// Measure group
		this.toolbar.group(__('Measure'))
			.add({ icon:'ruler',   label:__('Distance'), action: () => measure.activate('distance') })
			.add({ icon:'area',    label:__('Area'),     action: () => measure.activate('area') })
			.add({ icon:'radius',  label:__('Radius'),   action: () => measure.activate('radius') })
			.add({ icon:'bearing', label:__('Bearing'),  action: () => measure.activate('bearing') })
			.add({ icon:'clear',   label:__('Clear'),    action: () => measure.clear() });
		this.toolbar.separator();

		// Pick
		this.toolbar.group(__('Pick'))
			.add({ icon:'pick', label:__('Link record'), action: startPick });
		this.toolbar.separator();

		// Overlays (toggles)
		this.toolbar.group(__('Overlays'))
			.add({ icon:'cluster', label:__('Clusters'), active:true, key:'clusters', action: function() {
				clustered=!clustered; toggleBtn('clusters',clustered);
				map.removeLayer(markers);
				markers = clustered
					? L.markerClusterGroup({maxClusterRadius:45,showCoverageOnHover:false,spiderfyOnMaxZoom:true,iconCreateFunction:c=>L.divIcon({className:'sx-cluster',html:'<span>'+c.getChildCount()+'</span>',iconSize:[40,40]})})
					: L.featureGroup();
				markers.addTo(map); draw();
			}})
			.add({ icon:'lines', label:__('Relationships'), key:'rel_lines', action: async function() {
				const btn=$(this);
				if (overlayEnabled) { overlayEnabled=false; map.removeLayer(this.relLayer.layer); btn.removeClass('is-active'); return; }
				btn.prop('disabled',true);
				try { await ensureRelData(); overlayEnabled=true; this.relLayer.layer.addTo(map); btn.addClass('is-active'); draw(); }
				catch { mapStatus(__('Unable to load relationship lines.'),true); }
				finally { btn.prop('disabled',false); }
			}.bind(this)});

		// Empty the legacy top strip (we now use appPanel + in-canvas dock).
		this.tools.empty();

		draw();
		this.showDetails(__('Geographic map'), [[__('About this view'),__('Map tools (navigate, basemap, measure, pick, overlays) live in the dock on the right edge of the map. Records, filters, and export live in the panel at the upper left.')]]);
		if (currentPoints.length) map.fitBounds(L.latLngBounds(currentPoints.map(p=>[Number(p.latitude),Number(p.longitude)])).pad(0.15),{maxZoom:12});
		setTimeout(()=>map.invalidateSize(),0);
	}
	async relationships(data, renderId) {
		await frappe.require(['/assets/siraj_research/vendor/vis-network/vis-network.min.js', '/assets/siraj_research/css/siraj_explorer.css']);
		if (renderId !== this.renderId) return;
		this.canvas.addClass('sx-graph');
		const types = [...new Set(data.nodes.map(n => n.doctype))];
		this.showLegend(types);
		const all = new Map(data.nodes.map(n => [this.id(n), n]));
		const edgeLookup = new Map(data.edges.map(e => [e.name, e]));
		const nodeSet = new vis.DataSet();
		const edgeSet = new vis.DataSet();
		let currentEdges = [], currentNodes = [], history = [], trail = [], currentId = null, centerId = null;
		let searchTerm = '', selectedType = '', edgeType = '', hideEnded = false, evidenceOnly = false, evidenceLoaded = false, layout = 'force', maxDistance = 1;
		let centerButton, resetButton;
		const graphHost = $('<div class="sx-graph-host"></div>').appendTo(this.canvas);
		const matrixHost = $('<div class="sx-atlas-matrix"></div>').hide().appendTo(this.canvas);
		// Generate a data-URI for each doctype so the network shows the same
		// glyph+colour that appears on map pins, list avatars, and form pills.
		const nodeImageCache = new Map();
		const nodeImage = doctype => {
			if (nodeImageCache.has(doctype)) return nodeImageCache.get(doctype);
			const colour = this.colors[doctype] || '#6a7a7e';
			// Use the server/boot GLYPH strings directly (just path/circle fragments
			// on a 24×24 grid), so we can draw them white inside a coloured disc.
			const meta = (window.sirajRecordMeta && window.sirajRecordMeta.glyphs) ? window.sirajRecordMeta.glyphs[doctype] : null;
			const glyphPaths = meta || (window.sirajIcons && window.sirajIcons.types[doctype] && window.sirajIcons.types[doctype].replace
				? window.sirajIcons.types[doctype]
				: '<path d="M6 3h9l3 3v15H6Z"/><path d="M9 10h6M9 14h6"/>');
			const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48"><circle cx="24" cy="24" r="21" fill="${colour}" stroke="#fff" stroke-width="3"/><g transform="translate(12 12) scale(1)" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${glyphPaths}</g></svg>`;
			const uri = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
			nodeImageCache.set(doctype, uri);
			return uri;
		};
		this.network = new vis.Network(graphHost[0], { nodes: nodeSet, edges: edgeSet }, {
			interaction: { hover: true, navigationButtons: true, keyboard: true },
			physics: { stabilization: { iterations: 100 }, barnesHut: { gravitationalConstant: -5000, springLength: 150 } },
			nodes: { shape: 'circularImage', size: 22, borderWidth: 3, color: { border:'#fff', background:'#6a7a7e' }, font: { size:13, color:'#233b37' } },
			edges: { color: { color: '#9aa9b1', highlight: '#267b77' }, smooth: { type: 'dynamic' }, font: { size: 11, align: 'middle' } }
		});
		const showNode = (id, remember = true) => {
			const node = all.get(id);
			if (!node || !nodeSet.get(id)) return;
			if (remember && currentId && currentId !== id) history.push(currentId);
			currentId = id;
			if (centerButton) centerButton.prop('disabled', false);
			this.network.selectNodes([id]);
			this.network.focus(id, { scale: 1, animation: { duration: 400 } });
			this.showDetails(node.label, [[__('Type'), __(node.doctype)], [__('ID'), node.name], ...Object.entries(node.details || {}).map(([label, value]) => [__(label), value])], node);
			const connected = currentEdges.filter(e => JSON.stringify(e.source) === id || JSON.stringify(e.target) === id);
			$('<h5 class="sx-neighbors-heading"></h5>').text(__('Connections ({0})', [connected.length])).appendTo(this.aside);
			if (!connected.length) $('<p class="sx-muted"></p>').text(__('No visible connections in this view.')).appendTo(this.aside);
			connected.forEach(edge => {
				const sourceId = JSON.stringify(edge.source), targetId = JSON.stringify(edge.target);
				const neighbor = all.get(sourceId === id ? targetId : sourceId);
				if (!neighbor) return;
				const row = $('<div class="sx-neighbor"></div>').appendTo(this.aside);
				this.button(edge.type || __('Relationship'), () => showEdge(edge)).addClass('sx-edge-link').appendTo(row);
				this.button(neighbor.label, () => showNode(this.id(neighbor))).addClass('sx-neighbor-link').appendTo(row);
			});
		};
		const showEdge = edge => {
			if (!edge) return;
			currentId = null;
			if (centerButton) centerButton.prop('disabled', true);
			this.showDetails(edge.type || __('Relationship'), [[__('ID'), edge.name], [__('Direction'), edge.direction], [__('Description'), edge.description], [__('Record status'), edge.state], [__('Authentication level'), edge.authentication_level], [__('End date'), edge.end_date], [__('Primary source'), edge.primary_source], [__('Evidence'), edge.evidence_count]], { doctype: 'Relationship', name: edge.name });
			[edge.source, edge.target].forEach((key, index) => {
				const id = JSON.stringify(key), node = all.get(id);
				if (!node) return;
				const row = $('<div class="sx-neighbor"></div>').appendTo(this.aside);
				$('<small></small>').text(index === 0 ? __('Subject') : __('Object')).appendTo(row);
				this.button(node.label, () => showNode(id)).addClass('sx-neighbor-link').appendTo(row);
			});
		};
		const drawMatrix = (nodes, edges) => {
			matrixHost.empty();
			const NS = 'http://www.w3.org/2000/svg', step = 24, offset = 160;
			const side = Math.max(450, offset + nodes.length * step + 20);
			const svg = document.createElementNS(NS, 'svg');
			svg.setAttribute('width', side); svg.setAttribute('height', side);
			svg.setAttribute('role', 'group'); svg.setAttribute('aria-label', __('Relationship matrix'));
			matrixHost.append(svg);
			const positions = new Map(nodes.map((node, i) => [this.id(node), i]));
			const text = (x, y, label, transform, node) => {
				const el = document.createElementNS(NS, 'text'); el.setAttribute('x', x); el.setAttribute('y', y);
				if (transform) el.setAttribute('transform', transform);
				el.textContent = label.length > 22 ? label.slice(0, 21) + '…' : label;
				el.setAttribute('tabindex', '0'); el.setAttribute('role', 'button'); el.setAttribute('aria-label', label);
				el.setAttribute('class', 'sx-matrix-label');
				el.addEventListener('click', () => showNode(this.id(node)));
				el.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); showNode(this.id(node)); } });
				svg.appendChild(el);
			};
			nodes.forEach((n, i) => {
				const y = offset + i * step + 16, x = offset + i * step + 16;
				text(4, y, n.label, null, n); text(x, offset - 8, n.label, `rotate(-90 ${x} ${offset - 8})`, n);
			});
			const pairCounts = new Map();
			edges.forEach(edge => {
				const i = positions.get(JSON.stringify(edge.source)), j = positions.get(JSON.stringify(edge.target));
				if (i === undefined || j === undefined) return;
				const pair = i + ':' + j, overlap = pairCounts.get(pair) || 0; pairCounts.set(pair, overlap + 1);
				const rect = document.createElementNS(NS, 'rect');
				rect.setAttribute('x', offset + j * step + 2 + (overlap % 3) * 4);
				rect.setAttribute('y', offset + i * step + 2 + (overlap % 3) * 4);
				rect.setAttribute('width', 18 - (overlap % 3) * 4); rect.setAttribute('height', 18 - (overlap % 3) * 4);
				rect.setAttribute('fill', this.colors[nodes[i].doctype]); rect.setAttribute('class', 'sx-matrix-cell');
				rect.setAttribute('tabindex', '0'); rect.setAttribute('role', 'button');
				rect.setAttribute('aria-label', nodes[i].label + ' → ' + nodes[j].label + ': ' + (edge.type || __('Relationship')));
				const title = document.createElementNS(NS, 'title'); title.textContent = rect.getAttribute('aria-label'); rect.appendChild(title);
				rect.addEventListener('click', () => showEdge(edge));
				rect.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); showEdge(edge); } });
				svg.appendChild(rect);
			});
		};
		const update = () => {
			const term = searchTerm.toLocaleLowerCase();
			let nodes = data.nodes.filter(n => (!selectedType || n.doctype === selectedType) && (n.label + ' ' + n.name).toLocaleLowerCase().includes(term));
			let ids = new Set(nodes.map(n => this.id(n)));
			const eligibleEdges = data.edges.filter(e => ids.has(JSON.stringify(e.source)) && ids.has(JSON.stringify(e.target)) && (!edgeType || e.type === edgeType) && (!hideEnded || !e.end_date) && (!evidenceOnly || Number(e.evidence_count) > 0));
			const distance = new Map();
			if (centerId && ids.has(centerId)) {
				const neighbors = new Map();
				eligibleEdges.forEach(e => {
					const a = JSON.stringify(e.source), b = JSON.stringify(e.target);
					if (!neighbors.has(a)) neighbors.set(a, []);
					if (!neighbors.has(b)) neighbors.set(b, []);
					neighbors.get(a).push(b); neighbors.get(b).push(a);
				});
				distance.set(centerId, 0);
				const queue = [centerId];
				for (let index = 0; index < queue.length; index++) {
					const id = queue[index], depth = distance.get(id);
					if (depth >= maxDistance) continue;
					(neighbors.get(id) || []).forEach(neighbor => {
						if (!distance.has(neighbor)) { distance.set(neighbor, depth + 1); queue.push(neighbor); }
					});
				}
				nodes = nodes.filter(n => distance.has(this.id(n)));
				ids = new Set(distance.keys());
			} else { centerId = null; }
			currentEdges = eligibleEdges.filter(e => ids.has(JSON.stringify(e.source)) && ids.has(JSON.stringify(e.target)));
			currentNodes = nodes;
			edgeSet.clear(); nodeSet.clear(); history = []; currentId = null;
			if (centerButton) centerButton.prop('disabled', true);
			if (resetButton) resetButton.prop('disabled', !centerId);
			const large = nodes.length > 500;
			this.network.setOptions({ physics: { enabled: layout === 'force' && !large } });
			const columns = Math.ceil(Math.sqrt(nodes.length || 1));
			const positions = new Map(), rings = new Map();
			nodes.forEach(n => {
				const id = this.id(n), ring = centerId ? distance.get(id) : 1;
				if (!rings.has(ring)) rings.set(ring, []);
				rings.get(ring).push(id);
			});
			let previousRadius = 0;
			[...rings.keys()].sort((a, b) => a - b).forEach(ring => {
				const idsInRing = rings.get(ring);
				if (ring === 0) { positions.set(idsInRing[0], {x: 0, y: 0}); return; }
				const radius = Math.max(previousRadius + 220, idsInRing.length * 22);
				previousRadius = radius;
				idsInRing.forEach((id, i) => {
					const angle = 2 * Math.PI * i / idsInRing.length;
					positions.set(id, {x: radius * Math.cos(angle), y: radius * Math.sin(angle)});
				});
			});
			nodeSet.add(nodes.map((n, i) => ({ id: this.id(n), label: n.label, image: nodeImage(n.doctype), color: { border:'#fff', background: this.colors[n.doctype] || '#6a7a7e', highlight:{border:'#fff',background: this.colors[n.doctype] || '#6a7a7e'} },
				...(layout === 'orbit' ? positions.get(this.id(n)) : large ? { x: (i % columns) * 180, y: Math.floor(i / columns) * 110 } : {}) })));
			graphHost.toggle(layout !== 'matrix'); matrixHost.toggle(layout === 'matrix');
			if (layout === 'matrix') drawMatrix(nodes, currentEdges);
			edgeSet.add(currentEdges.map(e => ({ id: e.name, from: JSON.stringify(e.source), to: JSON.stringify(e.target), label: e.type, arrows: /^(directed|one.way)$/i.test(e.direction) ? 'to' : '' })));
			this.note.text(__('Showing {0} records and {1} relationships. Only visible records and links are included.', [nodes.length, currentEdges.length]) + ' ' + this.warning(data) + (evidenceOnly && data.edges.some(e => e.evidence_count == null) ? ' ' + __('Evidence counts are unavailable for some relationships.') : ''));
			this.showDetails(__('Relationship map'), [[__('About this view'), __('Select a record or a connection to inspect it. Drag nodes to rearrange the network.')]]);
		};
		this.network.on('selectNode', event => showNode(event.nodes[0]));
		this.network.on('selectEdge', event => showEdge(edgeLookup.get(event.edges[0])));
		$('<h5></h5>').text(__('Filters')).appendTo(this.rail);
		const filters = this.filterControls(types, (search, type) => { searchTerm = search; selectedType = type; centerId = null; trail = []; centerSelect.val(''); update(); }, this.rail);
		$('<h5></h5>').text(__('Arrangement')).appendTo(this.rail);
		const layoutSelect = $('<select class="form-control input-sm" aria-label="Relationship layout"></select>').appendTo(this.rail);
		[['force', __('Force')], ['orbit', __('Orbit')], ['matrix', __('Matrix')]].forEach(([id, title]) => $('<option></option>').val(id).text(title).appendTo(layoutSelect));
		layoutSelect.on('change', () => { const selected = currentId; layout = layoutSelect.val(); update(); if (selected && nodeSet.get(selected)) showNode(selected, false); if (layout !== 'matrix') this.network.fit({animation: true}); });
		$('<h5></h5>').text(__('Relationship type')).appendTo(this.rail);
		const edgeSelect = $('<select class="form-control input-sm" aria-label="Relationship type"></select>').appendTo(this.rail);
		$('<option value=""></option>').text(__('All relationship types')).appendTo(edgeSelect);
		[...new Set(data.edges.map(e => e.type).filter(Boolean))].sort().forEach(type => $('<option></option>').val(type).text(type).appendTo(edgeSelect));
		edgeSelect.on('change', () => { edgeType = edgeSelect.val(); update(); });
		const ended = $('<label class="sx-check"></label>').appendTo(this.rail);
		$('<input type="checkbox">').on('change', e => { hideEnded = e.target.checked; update(); }).appendTo(ended);
		ended.append(document.createTextNode(__('Hide ended relationships')));
		const evidenceLabel = $('<label class="sx-check"></label>').appendTo(this.rail);
		const evidenceCheck = $('<input type="checkbox">').appendTo(evidenceLabel);
		evidenceLabel.append(document.createTextNode(__('Only relationships with evidence')));
		evidenceCheck.on('change', async () => {
			if (!evidenceCheck.prop('checked')) { evidenceOnly = false; update(); return; }
			if (!evidenceLoaded) {
				evidenceCheck.prop('disabled', true);
				try {
					const response = await frappe.call({method: 'siraj_research.visualization.relationship_data', args: {include_evidence: 1}});
					if (renderId !== this.renderId) return;
					const counts = new Map(response.message.edges.map(edge => [edge.name, edge.evidence_count]));
					data.edges.forEach(edge => { edge.evidence_count = counts.has(edge.name) ? counts.get(edge.name) : null; });
					evidenceLoaded = true;
				} catch (error) {
					if (renderId === this.renderId) { evidenceCheck.prop('checked', false); this.note.text(__('Unable to load evidence counts.')).addClass('sx-warning'); }
					return;
				} finally { evidenceCheck.prop('disabled', false); }
			}
			evidenceOnly = evidenceCheck.prop('checked'); update();
		});
		const depthSelect = $('<select class="form-control input-sm" aria-label="Relationship depth"></select>').appendTo(this.tools);
		[[1, __('Direct relationships')], [2, __('Two degrees')], [3, __('Three degrees')]].forEach(([value, title]) => $('<option></option>').val(value).text(title).appendTo(depthSelect));
		depthSelect.on('change', () => {
			maxDistance = Number(depthSelect.val()); update();
			if (centerId) { showNode(centerId, false); if (layout !== 'matrix') this.network.fit({animation: true}); }
		});
		const centerSelect = $('<select class="form-control input-sm sx-center-select" aria-label="Center on a person or organization"></select>').appendTo(this.tools);
		$('<option value=""></option>').text(__('Center on a person or organization')).appendTo(centerSelect);
		['Person', 'Institution'].forEach(type => {
			const group = $('<optgroup></optgroup>').attr('label', __(type)).appendTo(centerSelect);
			data.nodes.filter(n => n.doctype === type).sort((a, b) => a.label.localeCompare(b.label)).forEach(n => $('<option></option>').val(this.id(n)).text(n.label + ' · ' + n.name).appendTo(group));
		});
		centerSelect.on('change', () => {
			const id = centerSelect.val();
			searchTerm = ''; selectedType = ''; filters.search.val(''); filters.select.val('');
			if (centerId && id && centerId !== id) trail.push(centerId);
			centerId = id || null; if (!id) trail = []; update();
			if (centerId) { showNode(centerId, false); if (layout !== 'matrix') this.network.fit({animation: true}); }
		});
		centerButton = this.button(__('Center on selected record'), () => {
			if (!currentId) return;
			if (centerId && centerId !== currentId) trail.push(centerId);
			centerId = currentId;
			update();
			showNode(centerId, false);
			if (layout !== 'matrix') this.network.fit({animation: true});
		}).prop('disabled', true).appendTo(this.tools);
		resetButton = this.button(__('Show all records'), () => { centerId = null; trail = []; centerSelect.val(''); update(); }).prop('disabled', true).appendTo(this.tools);
		this.button(__('Back'), () => {
			while (history.length) { const id = history.pop(); if (nodeSet.get(id)) { showNode(id, false); return; } }
			if (trail.length) { centerId = trail.pop(); centerSelect.val(centerId); update(); if (centerId) { showNode(centerId, false); if (layout !== 'matrix') this.network.fit({animation: true}); } }
		}).appendTo(this.tools);
		this.button(__('Export SVG'), () => {
			const ns = 'http://www.w3.org/2000/svg';
			const make = (tag, attrs, text) => {
				const el = document.createElementNS(ns, tag);
				Object.entries(attrs || {}).forEach(([key, value]) => el.setAttribute(key, value));
				if (text != null) el.textContent = text;
				return el;
			};
			let svg;
			if (layout === 'matrix') {
				svg = matrixHost.find('svg')[0].cloneNode(true);
				svg.querySelectorAll('text').forEach(el => { el.setAttribute('font-family', 'sans-serif'); el.setAttribute('font-size', '11'); el.setAttribute('fill', '#233b37'); });
				svg.querySelectorAll('rect').forEach(el => { el.setAttribute('stroke', '#fff'); el.setAttribute('stroke-width', '1'); });
			} else {
				// vis-network is canvas-based. Export a standalone vector rendering
				// of the current nodes/edges at their current network positions.
				const positions = this.network.getPositions(currentNodes.map(n => this.id(n)));
				const placed = currentNodes.filter(n => positions[this.id(n)] && Number.isFinite(positions[this.id(n)].x) && Number.isFinite(positions[this.id(n)].y));
				if (placed.length !== currentNodes.length) {
					this.note.text(__('Unable to export: some node positions are unavailable. Try again after the layout settles.')).addClass('sx-warning');
					return;
				}
				let minX = 0, maxX = 0, minY = 0, maxY = 0;
				if (placed.length) {
					minX = maxX = positions[this.id(placed[0])].x; minY = maxY = positions[this.id(placed[0])].y;
					placed.forEach(n => { const p = positions[this.id(n)]; minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x); minY = Math.min(minY, p.y); maxY = Math.max(maxY, p.y); });
				}
				const pairKey = edge => JSON.stringify([JSON.stringify(edge.source), JSON.stringify(edge.target)].sort());
				const pairTotals = new Map();
				currentEdges.forEach(edge => { const key = pairKey(edge); pairTotals.set(key, (pairTotals.get(key) || 0) + 1); });
				let padding = 180;
				pairTotals.forEach(total => { padding = Math.max(padding, 70 + total * 25); });
				placed.forEach(node => { padding = Math.max(padding, String(node.label).length * 8); });
				currentEdges.forEach(edge => { padding = Math.max(padding, String(edge.type || '').length * 7); });
				svg = make('svg', {xmlns: ns, viewBox: `${minX - padding} ${minY - padding} ${Math.max(2 * padding, maxX - minX + 2 * padding)} ${Math.max(2 * padding, maxY - minY + 2 * padding)}`, role: 'img', 'aria-label': __('Relationship map')});
				const defs = make('defs');
				const arrow = make('marker', {id: 'sx-arrow', viewBox: '0 0 10 10', refX: '9', refY: '5', markerWidth: '6', markerHeight: '6', orient: 'auto-start-reverse'});
				arrow.appendChild(make('path', {d: 'M 0 0 L 10 5 L 0 10 z', fill: '#64777d'})); defs.appendChild(arrow); svg.appendChild(defs);
				const multiplicity = new Map();
				currentEdges.forEach(edge => {
					const a = positions[JSON.stringify(edge.source)], b = positions[JSON.stringify(edge.target)];
					if (!a || !b || ![a.x, a.y, b.x, b.y].every(Number.isFinite)) return;
					const pair = pairKey(edge);
					const index = multiplicity.get(pair) || 0; multiplicity.set(pair, index + 1);
					let path, labelX, labelY;
					if (a.x === b.x && a.y === b.y) {
						const r = 35 + index * 12;
						path = `M ${a.x - 10} ${a.y - 10} C ${a.x - r} ${a.y - r * 2}, ${a.x + r} ${a.y - r * 2}, ${a.x + 10} ${a.y - 10}`;
						labelX = a.x; labelY = a.y - r * 1.5;
					} else {
						const dx = b.x - a.x, dy = b.y - a.y, length = Math.hypot(dx, dy), offset = index ? (Math.ceil(index / 2) * 25 * (index % 2 ? 1 : -1)) : 0;
						const x1 = a.x + dx / length * 14, y1 = a.y + dy / length * 14, x2 = b.x - dx / length * 18, y2 = b.y - dy / length * 18;
						const cx = (a.x + b.x) / 2 - dy / length * offset, cy = (a.y + b.y) / 2 + dx / length * offset;
						path = `M ${x1} ${y1} Q ${cx} ${cy} ${x2} ${y2}`;
						labelX = (x1 + 2 * cx + x2) / 4; labelY = (y1 + 2 * cy + y2) / 4;
					}
					const line = make('path', {d: path, fill: 'none', stroke: '#64777d', 'stroke-width': 2});
					if (/^(directed|one.way)$/i.test(edge.direction)) line.setAttribute('marker-end', 'url(#sx-arrow)');
					line.appendChild(make('title', {}, edge.type || __('Relationship'))); svg.appendChild(line);
					if (edge.type) svg.appendChild(make('text', {x: labelX, y: labelY - 4, 'text-anchor': 'middle', 'font-family': 'sans-serif', 'font-size': 11, fill: '#344c4c'}, edge.type));
				});
				placed.forEach(node => {
					const p = positions[this.id(node)], group = make('g', {});
					group.appendChild(make('circle', {cx: p.x, cy: p.y, r: 13, fill: this.colors[node.doctype] || '#64777d', stroke: '#344c4c', 'stroke-width': 2}));
					group.appendChild(make('text', {x: p.x, y: p.y + 31, 'text-anchor': 'middle', 'font-family': 'sans-serif', 'font-size': 13, fill: '#233b37'}, node.label));
					group.appendChild(make('title', {}, __(node.doctype) + ' · ' + node.name)); svg.appendChild(group);
				});
			}
			svg.setAttribute('xmlns', ns);
			const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(svg)], {type: 'image/svg+xml'}));
			const a = document.createElement('a'); a.href = url; a.download = 'siraj-relationships.svg'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
		}).appendTo(this.tools);
		this.button(__('Fit network'), () => this.network.fit({ animation: true })).appendTo(this.tools);
		this.button(__('Stabilize layout'), () => this.network.stabilize()).appendTo(this.tools);
		update();
	}

	async structures(renderId) {
		await frappe.require(['/assets/siraj_research/vendor/d3/d3.min.js', '/assets/siraj_research/css/siraj_explorer.css']);
		await frappe.require('/assets/siraj_research/vendor/d3-sankey/d3-sankey.min.js');
		await frappe.require('/assets/siraj_research/js/structure_deck.js');
		if (renderId !== this.renderId) return;
		this.canvas.removeClass('sx-canvas');
		const choices = [['people', __('Person')], ['institutions', __('Institution')], ['places', __('Place')], ['events', __('Research Event')], ['relationships', __('Relationship')], ['sources', __('Source')], ['units', __('Units — command hierarchy')], ['regions', __('Regions — command hierarchy')], ['regions-units', __('Regions × Units')], ['units-ops', __('Units × Operations')], ['forces', __('Forces — echelon, status, classification')]];
		const select = $('<select class="form-control input-sm" aria-label="Structure source"></select>').appendTo(this.tools);
		choices.forEach(([id, title]) => $('<option></option>').val(id).text(title).appendTo(select));
		let request = 0;
		const load = async () => {
			const current = ++request;
			this.structureDeck = null;
			this.canvas.empty(); this.aside.empty(); this.note.removeClass('sx-warning').text(__('Loading…'));
			try {
				const result = await frappe.call({ method: 'siraj_research.visualization.structure_data', args: { source: select.val() } });
				if (renderId !== this.renderId || current !== request) return;
				const data = result.message;
				this.note.text(__('Counting {0} visible records.', [data.count]) + (data.unavailable_types && data.unavailable_types.length ? ' ' + __('Some record types are not readable: {0}', [data.unavailable_types.map(type => __(type)).join(', ')]) : ''));
				new window.SirajStructureDeck(this, this.canvas, this.aside, data);
			} catch (error) {
				if (renderId !== this.renderId || current !== request) return;
				this.canvas.empty(); this.aside.empty(); this.note.text(__('Unable to load this structure. Check permissions.')).addClass('sx-warning');
				console.error(error);
			}
		};
		select.on('change', load);
		await load();
	}
}
