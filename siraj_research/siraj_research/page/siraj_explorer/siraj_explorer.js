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
				let data;
				try {
					const res = await frappe.call({ method: 'siraj_research.visualization.geographic_data' });
					data = res.message;
				} catch (error) {
					console.error(error);
					data = { points: [], truncated: [], unavailable: true };
				}
				if (renderId === this.renderId) await this.geography(data, renderId);
			} else {
				const res = await frappe.call({ method: 'siraj_research.visualization.relationship_data' });
				if (renderId === this.renderId) await this.relationships(res.message, renderId);
			}
		} catch (error) {
			if (renderId !== this.renderId) return;
			this.note.text(__('Unable to load the explorer. Check permissions and try again.')).addClass('sx-warning');
			console.error(error);
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
		await frappe.require([
			'/assets/siraj_research/vendor/leaflet/leaflet.css',
			'/assets/siraj_research/vendor/leaflet/leaflet.js',
			'/assets/siraj_research/vendor/leaflet-markercluster/leaflet.markercluster.js',
			'/assets/siraj_research/vendor/topojson/topojson-client.min.js',
			'/assets/siraj_research/js/siraj-icons.js',
			'/assets/siraj_research/js/siraj-map-toolbar.js',
			'/assets/siraj_research/css/siraj_explorer.css',
			'/assets/siraj_research/css/siraj-map-toolbar.css',
		]);
		if (renderId !== this.renderId) return;
		// Suppress Leaflet's default zoom control: our in-map toolbar provides it.
		const map = this.map = L.map(this.canvas[0], { worldCopyJump: true, preferCanvas: true, minZoom: 0, maxZoom: 22, zoomAnimation: false, zoomControl: false }).setView([33.3152, 44.3661], 4);
		L.control.scale({ imperial: false, position: 'bottomleft' }).addTo(map);
		let offlineLayer = null, onlineLayer = null, localPackLayer = null, selectedCircle = null;
		const mapStatus = (text, warn) => {
			if (this.toolbar) this.toolbar.status(text, warn ? 'warning' : null);
			if (this.note) this.note.text(text).toggleClass('sx-warning', !!warn);
		};
		try {
			const response = await fetch('/assets/siraj_research/vendor/world-atlas/countries-110m.json');
			if (!response.ok) throw new Error('Offline basemap HTTP ' + response.status);
			const world = await response.json();
			if (renderId !== this.renderId) return;
			offlineLayer = L.geoJSON(topojson.feature(world, world.objects.countries), {
				interactive: false, style: { color: '#a4b4a8', weight: 0.7, fillColor: '#e8e4cf', fillOpacity: 1 }
			}).addTo(map);
			map.attributionControl.addAttribution('Natural Earth / world-atlas');
			mapStatus(__('Offline basemap: Natural Earth, low detail.'));
		} catch (error) {
			console.error(error);
			if (renderId !== this.renderId) return;
			mapStatus(__('Local basemap could not be loaded. You can still use the markers or enable online tiles.'), true);
		}
		// Shared SIRAJ icons for pins — pulled from the global registry.
		const pointIcon = p => L.divIcon({
			className: 'sx-pin-wrapper', iconSize: [36, 36], iconAnchor: [18, 18],
			html: window.sirajIcons.pin(p.doctype, this.colors[p.doctype], 36)
		});
		const pinIcons = {};
		const types = [...new Set(data.points.map(p => p.doctype))];
		types.forEach(t => { if (window.sirajIcons.types[t]) pinIcons[t] = window.sirajIcons.types[t]; });
		this.showLegend(types, pinIcons);
		let clustered = true, currentPoints = [], searchTerm = '', selectedType = '', listLimit = 100;
		const recordHeading = $('<h4></h4>').text(__('Mapped records')).appendTo(this.records);
		const recordList = $('<div class="sx-record-list"></div>').appendTo(this.records);
		const listMore = this.button(__('Show more'), () => { listLimit += 100; renderList(); }).appendTo(this.records);
		const dms = (value, latitude) => {
			const number = Number(value), tenths = Math.round(Math.abs(number) * 36000);
			const degrees = Math.floor(tenths / 36000), minutes = Math.floor((tenths % 36000) / 600);
			const seconds = ((tenths % 600) / 10).toFixed(1);
			return degrees + '° ' + minutes + '′ ' + seconds + '″ ' + (latitude ? (number < 0 ? 'S' : 'N') : (number < 0 ? 'W' : 'E'));
		};
		const selectPoint = p => {
			if (selectedCircle) map.removeLayer(selectedCircle);
			const radius = Number(p.geo_uncertainty_m);
			if (Number.isFinite(radius) && radius > 0 && radius <= 1000000) selectedCircle = L.circle([p.latitude, p.longitude], { radius, color: this.colors[p.doctype], fillOpacity: 0.1, interactive: false }).addTo(map);
			this.showDetails(p.label, [[__('Type'), __(p.doctype)], [__('ID'), p.name], [__('Latitude'), p.latitude], [__('Longitude'), p.longitude], [__('DMS coordinates'), dms(p.latitude, true) + ' / ' + dms(p.longitude, false)], [__('Coordinate precision'), p.geo_precision], [__('How the point was obtained'), p.geocoding_method], [__('Uncertainty radius (m)'), p.geo_uncertainty_m], [__('Point source'), p.geometry_source]], p);
		};
		const renderList = () => {
			recordHeading.text(__('Mapped records ({0})', [currentPoints.length]));
			recordList.empty();
			currentPoints.slice(0, listLimit).forEach(p => {
				const button = this.button(p.label, () => { selectPoint(p); map.panTo([Number(p.latitude), Number(p.longitude)]); }).appendTo(recordList);
				button.addClass('sx-record-item').attr('title', __(p.doctype) + ' · ' + p.name);
			});
			listMore.toggle(currentPoints.length > listLimit);
		};
		let overlayData = null, overlayEnabled = false;
		const overlay = L.featureGroup().addTo(map);
		const drawOverlay = () => {
			overlay.clearLayers();
			if (!overlayEnabled || !overlayData) return;
			const positioned = new Map(currentPoints.map(p => [this.id(p), p]));
			overlayData.edges.forEach(edge => {
				const a = positioned.get(JSON.stringify(edge.source)), b = positioned.get(JSON.stringify(edge.target));
				if (!a || !b) return;
				const line = L.polyline([[Number(a.latitude), Number(a.longitude)], [Number(b.latitude), Number(b.longitude)]], {color: '#536b78', weight: 2, opacity: 0.55});
				line.on('click', () => this.showDetails(edge.type || __('Relationship'), [[__('Subject'), a.label], [__('Object'), b.label], [__('Direction'), edge.direction], [__('Description'), edge.description], [__('Record status'), edge.state]], {doctype: 'Relationship', name: edge.name}));
				overlay.addLayer(line);
			});
		};
		let markers = L.markerClusterGroup({
			maxClusterRadius: 45, showCoverageOnHover: false, spiderfyOnMaxZoom: true,
			iconCreateFunction: cluster => L.divIcon({ className: 'sx-cluster', html: '<span>' + cluster.getChildCount() + '</span>', iconSize: [40, 40] })
		}).addTo(map);
		const draw = () => {
			if (selectedCircle) { map.removeLayer(selectedCircle); selectedCircle = null; }
			markers.clearLayers();
			const term = searchTerm.toLocaleLowerCase();
			currentPoints = data.points.filter(p => (!selectedType || p.doctype === selectedType) && (p.label + ' ' + p.name).toLocaleLowerCase().includes(term));
			currentPoints.forEach(p => {
				const marker = L.marker([Number(p.latitude), Number(p.longitude)], { icon: pointIcon(p), title: p.label, keyboard: true });
				marker.bindTooltip(this.escape(p.label));
				marker.on('click', () => selectPoint(p));
				markers.addLayer(marker);
			});
			const text = data.unavailable ? __('Record data could not be loaded. The local basemap may still be available.') : __('Showing {0} record-owned points. Unset and ambiguous 0,0 coordinates are excluded.', [currentPoints.length]) + ' ' + this.warning(data);
			this.note.toggleClass('sx-warning', !!data.unavailable).text(text);
			renderList();
			drawOverlay();
		};

		// ========== EMBEDDED TOOLBAR (in-canvas) ==========
		this.toolbar = L.control.sirajToolbar({ position: 'topright' }).addTo(map);
		const localPacks = new Map();
		const panels = { records: true, details: true };
		// Always-visible search at the top of the dock.
		const searchBox = $('<div class="siraj-toolbar-search"><input type="search" class="form-control input-sm" placeholder="' + __('Search records') + '" aria-label="' + __('Search records') + '"></div>');
		searchBox.find('input').on('input', e => { searchTerm = e.target.value; listLimit = 100; draw(); });
		this.toolbar.attachNode(searchBox);

		// Type filter (popover)
		const typeFilterMenu = pop => {
			const w = $('<div></div>').appendTo(pop);
			const opt = (val, label, active) => {
				const b = $('<button type="button" class="siraj-toolbar-opt"></button>').html('<span>' + label + '</span>');
				if (active) b.addClass('is-active');
				b.on('click', () => {
					selectedType = val;
					w.find('.is-active').removeClass('is-active');
					b.addClass('is-active');
					listLimit = 100; draw();
				});
				b.appendTo(w);
			};
			opt('', __('All types'), true);
			types.forEach(t => opt(t, __(t), false));
		};
		this.toolbar.group(__('Filter'))
			.add({ icon: 'search', label: __('Type'), menuTitle: __('Record type'), menu: typeFilterMenu });

		// Navigate group
		this.toolbar.group(__('Navigate'))
			.add({ icon: 'zoom_in', label: __('In'), action: () => map.zoomIn() })
			.add({ icon: 'zoom_out', label: __('Out'), action: () => map.zoomOut() })
			.add({ icon: 'home', label: __('Home'), action: () => map.setView([33.3152, 44.3661], 4) })
			.add({ icon: 'fit', label: __('Fit'), action: () => {
				if (currentPoints.length) map.fitBounds(L.latLngBounds(currentPoints.map(p => [Number(p.latitude), Number(p.longitude)])).pad(0.15), { maxZoom: 12 });
			}})
			.add({ icon: 'locate', label: __('Coords'), menuTitle: __('Go to coordinates'), menu: pop => {
				const w = $('<div></div>').appendTo(pop);
				const row = $('<div style="display:flex;gap:4px"></div>').appendTo(w);
				const lat = $('<input type="number" step="any" min="-90" max="90" class="form-control input-sm" placeholder="' + __('Lat') + '">').appendTo(row);
				const lon = $('<input type="number" step="any" min="-180" max="180" class="form-control input-sm" placeholder="' + __('Lon') + '">').appendTo(row);
				const stat = $('<div style="font-size:11px;color:var(--text-muted);margin-top:4px"></div>').appendTo(w);
				$('<button type="button" class="btn btn-sm btn-primary" style="margin-top:4px">' + __('Go') + '</button>').appendTo(w).on('click', () => {
					const la = Number(lat.val()), lo = Number(lon.val());
					if (![la,lo].every(Number.isFinite) || Math.abs(la)>90 || Math.abs(lo)>180) { stat.text(__('Enter valid decimal coordinates.')); return; }
					stat.text(dms(la,true) + ' / ' + dms(lo,false));
					map.setView([la,lo], 8);
				});
			}});

		// Basemap group
		const selectBasemap = val => {
			if (onlineLayer) { map.removeLayer(onlineLayer); onlineLayer = null; }
			if (localPackLayer) { map.removeLayer(localPackLayer); localPackLayer = null; }
			map.setMinZoom(0);
			const selectedPack = localPacks.get(String(val).replace(/^pack-/, ''));
			if (selectedPack) {
				if (offlineLayer) map.removeLayer(offlineLayer);
				const url = '/api/method/siraj_research.local_maps.tile?kind=' + encodeURIComponent(selectedPack.kind) + '&z={z}&x={x}&y={y}';
				map.setMinZoom(selectedPack.minzoom);
				localPackLayer = L.tileLayer(url, {minZoom: selectedPack.minzoom, maxZoom:22, maxNativeZoom: selectedPack.maxzoom,
					attribution: this.escape(selectedPack.attribution || '')}).addTo(map);
				localPackLayer.on('tileerror', () => mapStatus(__('Some local tiles are unavailable at this location or zoom.'), true));
				mapStatus(__('Local map pack: coverage depends on supplied data.'));
			} else if (val === 'online') {
				if (offlineLayer) map.removeLayer(offlineLayer);
				onlineLayer = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom:22, maxNativeZoom:19, attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(map);
				onlineLayer.on('tileerror', () => mapStatus(__('Some online tiles failed to load. Choose the offline basemap to continue.'), true));
				mapStatus(__('Online tiles disclose your IP address and viewed area to OpenStreetMap.'));
			} else {
				if (offlineLayer) offlineLayer.addTo(map).bringToBack();
				mapStatus(offlineLayer ? __('Offline basemap: Natural Earth, low detail.') : __('Local basemap could not be loaded.'), !offlineLayer);
			}
		};
		const basemapMenu = pop => {
			const w = $('<div></div>').appendTo(pop);
			const opt = (val, icon, label, active) => {
				const b = $('<button type="button" class="siraj-toolbar-opt"></button>')
					.html(window.sirajIcons.svg(icon,{size:16}) + '<span>' + label + '</span>');
				if (active) b.addClass('is-active');
				b.on('click', () => { w.find('.is-active').removeClass('is-active'); b.addClass('is-active'); selectBasemap(val); });
				b.appendTo(w); return b;
			};
			opt('local','offline',__('Offline basemap'), true);
			opt('online','online',__('Online: OpenStreetMap'), false);
			$('<hr>').appendTo(w);
			const note = $('<div style="font-size:11px;color:var(--text-muted);padding:4px"></div>').text(__('Downloaded local packs appear here.')).appendTo(w);
			frappe.call({method:'siraj_research.local_maps.available_packs', type:'GET', silent:true, error_handlers:{403:()=>{}}}).then(res => {
				if (!Array.isArray(res.message)) return;
				res.message.forEach(pack => {
					if (pack.unavailable || !['standard','aerial'].includes(pack.kind)) return;
					localPacks.set(pack.kind, pack);
					opt('pack-'+pack.kind,'layers',pack.kind==='aerial'?__('Local aerial'):__('Local standard'),false);
				});
				if (localPacks.size) note.remove();
			}).catch(()=>{});
		};
		this.toolbar.group(__('Basemap'))
			.add({ icon: 'layers', label: __('Basemap'), menuTitle: __('Basemap'), menu: basemapMenu });

		this.toolbar.separator();

		// Display group
		let clusterBtn, relBtn, recsBtn, detailsBtn;
		this.toolbar.group(__('Display'))
			.add({ icon: 'cluster', label: __('Clusters'), active: true, key: 'clusters', action: function() {
				clustered = !clustered;
				map.removeLayer(markers);
				markers = clustered
					? L.markerClusterGroup({ maxClusterRadius:45, showCoverageOnHover:false, spiderfyOnMaxZoom:true, iconCreateFunction: c => L.divIcon({ className:'sx-cluster', html:'<span>'+c.getChildCount()+'</span>', iconSize:[40,40] }) })
					: L.featureGroup();
				markers.addTo(map); draw();
			}})
			.add({ icon: 'lines', label: __('Rel lines'), key: 'rel_lines', action: async function() {
				const btn = $(this);
				if (overlayEnabled) { overlayEnabled=false; drawOverlay(); btn.removeClass('is-active'); return; }
				btn.prop('disabled', true);
				try {
					if (!overlayData) overlayData = (await frappe.call({method:'siraj_research.visualization.relationship_data'})).message;
					if (renderId !== this.renderId) return;
					overlayEnabled = true; drawOverlay(); btn.addClass('is-active');
				} catch { mapStatus(__('Unable to load relationship lines.'), true); }
				finally { btn.prop('disabled', false); }
			}})
			.add({ icon: 'panel_left', label: __('Records'), active: true, key: 'records', action: function() {
				panels.records = !panels.records;
				$('.sx-layout').toggleClass('sx-no-records', !panels.records);
				this.records.toggle(panels.records);
				setTimeout(()=>map.invalidateSize(),0);
			}.bind(this)})
			.add({ icon: 'panel_right', label: __('Details'), active: true, key: 'details', action: function() {
				panels.details = !panels.details;
				$('.sx-layout').toggleClass('sx-no-details', !panels.details);
				this.aside.toggle(panels.details);
				setTimeout(()=>map.invalidateSize(),0);
			}.bind(this)});

		this.toolbar.separator();

		// Tools group
		let measuring = '', measurePoints = [], measureLine = null;
		const clearMeasure = () => { measurePoints=[]; if (measureLine){map.removeLayer(measureLine); measureLine=null;} };
		this.toolbar.group(__('Tools'))
			.add({ icon: 'ruler', label: __('Distance'), action: () => { measuring='distance'; clearMeasure(); mapStatus(__('Click two points to measure distance.')); }})
			.add({ icon: 'area', label: __('Area'), action: () => { measuring='area'; clearMeasure(); mapStatus(__('Click at least three points to measure area.')); }})
			.add({ icon: 'clear', label: __('Clear'), action: () => { measuring=''; clearMeasure(); mapStatus(''); }})
			.add({ icon: 'export', label: __('GeoJSON'), action: () => {
				const geojson = { type:'FeatureCollection', features: currentPoints.map(p => ({ type:'Feature', geometry:{ type:'Point', coordinates:[Number(p.longitude),Number(p.latitude)] }, properties:{ doctype:p.doctype, name:p.name, label:p.label, precision:p.geo_precision, method:p.geocoding_method, uncertainty_m:p.geo_uncertainty_m, source:p.geometry_source }})) };
				const url=URL.createObjectURL(new Blob([JSON.stringify(geojson)],{type:'application/geo+json'}));
				const a=document.createElement('a'); a.href=url; a.download='siraj-visible-points.geojson'; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
			}})
			.add({ icon: 'info', label: __('About'), menuTitle: __('About this map'), menu: pop => {
				$('<div style="font-size:12px;line-height:1.5;color:#3c5054"></div>')
					.text(__('Select a marker to inspect its record. Clusters group nearby points; tools live in the dock at the right edge of the map. Online tiles are opt-in.'))
					.appendTo(pop);
			}});

		map.on('click', event => {
			if (!measuring) return;
			if (measuring === 'distance' && measurePoints.length === 2) clearMeasure();
			measurePoints.push(event.latlng);
			if (measureLine) map.removeLayer(measureLine);
			if (measurePoints.length >= 2) measureLine = (measuring === 'area' && measurePoints.length >= 3 ? L.polygon : L.polyline)(measurePoints, {color:'#1a6670',weight:3,dashArray:'6 5',fillOpacity:0.1,interactive:false}).addTo(map);
			if (measuring === 'distance' && measurePoints.length === 2) mapStatus(__('Distance: {0} km', [(map.distance(measurePoints[0], measurePoints[1])/1000).toFixed(2)]));
			if (measuring === 'area' && measurePoints.length >= 3) {
				const R=6371008.8, pts=measurePoints; let sum=0;
				pts.forEach((p,i)=>{ const n=pts[(i+1)%pts.length]; let d=(n.lng-p.lng)*Math.PI/180; while(d>Math.PI)d-=2*Math.PI; while(d<-Math.PI)d+=2*Math.PI; sum+=d*(2+Math.sin(p.lat*Math.PI/180)+Math.sin(n.lat*Math.PI/180)); });
				const sph=4*Math.PI*R*R, raw=Math.abs(sum*R*R/2)%sph;
				mapStatus(__('Approximate area: {0} km²', [(Math.min(raw,sph-raw)/1e6).toFixed(2)]));
			}
		});

		// Clear the legacy horizontal tool strip now that everything is in the map dock.
		this.tools.empty();

		draw();
		this.showDetails(__('Geographic map'), [[__('About this view'), __('Select a marker to inspect its record. Clusters show the number of nearby points. Map tools live in the dock on the right edge of the map.')]]);
		if (currentPoints.length) map.fitBounds(L.latLngBounds(currentPoints.map(p => [Number(p.latitude), Number(p.longitude)])).pad(0.15), { maxZoom: 12 });
		setTimeout(()=>map.invalidateSize(), 0);
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
		this.network = new vis.Network(graphHost[0], { nodes: nodeSet, edges: edgeSet }, {
			interaction: { hover: true, navigationButtons: true, keyboard: true },
			physics: { stabilization: { iterations: 100 }, barnesHut: { gravitationalConstant: -5000, springLength: 150 } },
			nodes: { shape: 'dot', size: 13, font: { size: 13 }, borderWidth: 2 },
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
			nodeSet.add(nodes.map((n, i) => ({ id: this.id(n), label: n.label, color: this.colors[n.doctype],
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
