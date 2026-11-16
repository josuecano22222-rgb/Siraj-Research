/* Per-DocType coordinate map editor.
 *
 * Every DocType that carries `latitude` and `longitude` fields (whether they
 * are Float or Data) gets one shared editor mounted INSIDE the Position
 * section, right after the longitude field. The editor behaves as the
 * designated "map field": clicking the map writes the coordinates (respecting
 * read-only / permission state), typing in the fields moves the pin, the
 * toolbar comes from the shared SirajMapKit/TOOL_SPEC registry so it is
 * structurally identical to the Explorer's map, and layout changes (tab
 * switch, section collapse) invalidate the Leaflet size.
 *
 * No per-doctype code is needed: any DocType exposing `latitude`/`longitude`
 * fields automatically gets the editor, whether they're Float, Data, or any
 * numeric text type.
 */
(() => {
	'use strict';
	window.SIRAJ_COORDINATE_MAP_VERSION = 2;   // bumped for cache-bust detection
	const states = new WeakMap();
	const registered = new Set();
	const t = s => __(s);

	// Accept both text and numeric fieldtypes (Float, Int, Data, Small Text).
	const writableFieldTypes = new Set(['Data','Small Text','Text','Long Text','Float','Int','Currency','Percent']);
	const readableFieldTypes = new Set([...writableFieldTypes, 'Read Only']);

	let assetsPromise;
	const assets = () => {
		if (!assetsPromise) {
			assetsPromise = Promise.resolve(frappe.require([
				'/assets/siraj_research/vendor/leaflet/leaflet.css',
				'/assets/siraj_research/vendor/leaflet/leaflet.js',
				'/assets/siraj_research/vendor/topojson/topojson-client.min.js',
			])).then(() => {
				if (window.SirajMapKit) return;
				// Kit is loaded via app_include_js in production; this retry
				// only fires if something odd happened with the bundle.
				return new Promise(res => {
					const check = () => window.SirajMapKit ? res() : setTimeout(check, 30);
					check();
				});
			}).catch(err => { assetsPromise = null; throw err; });
		}
		return assetsPromise;
	};

	/* ------- Coordinate parsing (handles Float, arabic numerals, scientific notation) ------- */
	function parseCoordinate(value, max) {
		if (value === undefined || value === null || typeof value === 'boolean') return null;
		if (typeof value === 'number') return Number.isFinite(value) && Math.abs(value) <= max ? value : null;
		const normalized = String(value).trim()
			.replace(/[٠-٩]/g, c => String(c.charCodeAt(0) - 0x660))
			.replace(/[۰-۹]/g, c => String(c.charCodeAt(0) - 0x6f0))
			.replace(/٫/g, '.');
		if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(e[+-]?\d+)?$/i.test(normalized)) return null;
		const number = Number(normalized);
		if (!Number.isFinite(number) || Math.abs(number) > max) return null;
		return number;
	}
	function decimalText(number) {
		// Float fields accept numeric strings; Frappe will coerce on save.
		const text = String(number);
		if (!/[eE]/.test(text)) return text;
		const [coefficient, exponent] = text.toLowerCase().split('e');
		const negative = coefficient.startsWith('-');
		const unsigned = coefficient.replace(/^-/, '');
		const [whole, fraction = ''] = unsigned.split('.');
		const digits = whole + fraction, position = whole.length + Number(exponent);
		const result = position <= 0 ? '0.' + '0'.repeat(-position) + digits
			: position >= digits.length ? digits + '0'.repeat(position - digits.length)
			: digits.slice(0, position) + '.' + digits.slice(position);
		return (negative ? '-' : '') + result;
	}
	function controls(frm) {
		const fields = frm.fields_dict || {};
		const lat = fields.latitude, lon = fields.longitude;
		if (!lat || !lon || typeof lat.get_status !== 'function' || typeof lon.get_status !== 'function') return null;
		const a = lat.get_status(), b = lon.get_status();
		if (a === 'None' || b === 'None') return null;
		const latOk = readableFieldTypes.has(lat.df.fieldtype);
		const lonOk = readableFieldTypes.has(lon.df.fieldtype);
		if (!latOk || !lonOk) return null;
		return {
			lat, lon,
			editable: a === 'Write' && b === 'Write' && writableFieldTypes.has(lat.df.fieldtype) && writableFieldTypes.has(lon.df.fieldtype),
		};
	}
	function currentValue(field, doc, name) {
		if (field.get_status() === 'Write' && field.$input && field.$input.length) return field.$input.val();
		return doc[name];
	}
	function remove(frm) {
		const state = states.get(frm); if (!state) return;
		state.lat.$input?.off('.sirajCoordinates');
		state.lon.$input?.off('.sirajCoordinates');
		if (state.tabObserver) { state.tabObserver.disconnect(); state.tabObserver = null; }
		if (state.resizeObserver) state.resizeObserver.disconnect();
		if (state.measure) { state.measure.deactivate(); }
		if (state.map) state.map.remove();
		state.box.remove();
		states.delete(frm);
	}

	function pinIcon(doctype, color, size) {
		const s = size || 32;
		return L.divIcon({
			className: 'sx-pin-wrapper',
			// Teardrop anchor: the point is at the bottom of the pin.
			iconSize: [s, s], iconAnchor: [s/2, s/2],
			html: window.sirajIcons ? window.sirajIcons.pin(doctype || 'Place', color, s) : '',
		});
	}

	function update(frm, center = true) {
		const state = states.get(frm), fields = controls(frm);
		if (!state) return;
		if (!fields || fields.lat !== state.lat || fields.lon !== state.lon || frm.docname !== state.docname) { remove(frm); return; }
		state.editable = fields.editable;
		const a = currentValue(fields.lat, frm.doc, 'latitude');
		const b = currentValue(fields.lon, frm.doc, 'longitude');
		const lat = parseCoordinate(a, 90), lon = parseCoordinate(b, 180);
		if (lat === null || lon === null) {
			if (state.marker) { state.map.removeLayer(state.marker); state.marker = null; }
			state.status.text((String(a ?? '').trim() || String(b ?? '').trim())
				? t('Enter valid decimal coordinates: latitude −90 to 90, longitude −180 to 180.')
				: t('Click the map to pick a point, or type coordinates above.'));
		} else {
			if (!state.marker) {
				state.marker = L.marker([lat, lon], { icon: pinIcon('Place', null, 32), draggable: !!fields.editable }).addTo(state.map);
				state.marker.on('dragend', () => {
					if (!fields.editable) return;
					const p = state.marker.getLatLng();
					writePoint(frm, p, false);
				});
			} else state.marker.setLatLng([lat, lon]);
			if (center) state.map.setView([lat, lon], Math.max(state.map.getZoom(), 6));
			state.status.text((lat === 0 && lon === 0)
				? t('Zero pair shown; legacy zero may also mean unknown. Confirm before interpreting.')
				: t('Location shown. Click the map to move the pin, or drag the pin directly.'));
		}
		if (!fields.editable) state.status.text(t('Location preview (read-only).'));
	}

	async function writePoint(frm, latlng, doMove = true) {
		const state = states.get(frm), fields = controls(frm);
		if (!state || !fields || !fields.editable || frm.docname !== state.docname) return;
		const latitude = Number(latlng.lat), longitude = Number(latlng.lng);
		if (!Number.isFinite(latitude) || !Number.isFinite(longitude) || Math.abs(latitude) > 90 || Math.abs(longitude) > 180) return;
		const latText = decimalText(latitude), lonText = decimalText(longitude);
		try {
			await frm.set_value({ latitude: latText, longitude: lonText });
			// Also record the geocoding method as 'map_pick' if the field is present and writable.
			if (frm.fields_dict.geocoding_method && frm.fields_dict.geocoding_method.get_status() === 'Write') {
				try { frm.set_value('geocoding_method', 'map_pick'); } catch (_) { /* optional */ }
			}
			if (doMove && state.marker) state.marker.setLatLng([latitude, longitude]);
			update(frm, false);
		} catch (_) { state.status.text(t('Could not update the coordinate fields.')); }
	}

	async function mount(frm) {
		const fields = controls(frm);
		if (!fields || !fields.lon.$wrapper?.length) { remove(frm); return; }
		const old = states.get(frm);
		if (old && old.docname === frm.docname && old.lat === fields.lat && old.lon === fields.lon && old.box[0].isConnected) {
			update(frm);
			setTimeout(() => { if (states.get(frm) === old) old.map.invalidateSize(); }, 0);
			return;
		}
		remove(frm);
		const docname = frm.docname;
		try { await assets(); } catch (_) { return; }
		const current = controls(frm);
		if (frm.docname !== docname || !current || current.lat !== fields.lat || current.lon !== fields.lon || states.has(frm)) return;

		// Mount inside the Position section, right after the longitude wrapper.
		// This makes the map a natural child of the "Position & evidence" group.
		const box = $('<div class="siraj-coordinate-map"></div>').css({ margin: '10px 0', clear: 'both' });
		const heading = $('<div class="siraj-coord-heading" style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px"></div>').appendTo(box);
		$('<strong></strong>').text(t('Coordinate map')).appendTo(heading);
		const help = $('<div style="margin-bottom:6px;font-size:12px;color:var(--text-muted)"></div>').text(t('Click the map to place the pin, or drag the pin to move it. Tools live in the dock on the right edge of the map.')).appendTo(box);
		const canvas = $('<div role="region" class="siraj-coord-canvas"></div>').attr('aria-label', t('Coordinate map')).css({
			height: '380px', width: '100%', background: '#dce8ed', borderRadius: '8px',
			border: '1px solid var(--border-color,#d9e2e7)', position: 'relative', overflow:'hidden',
		}).appendTo(box);
		const status = $('<div role="status" aria-live="polite" style="margin-top:6px;font-size:12px;color:var(--text-muted)"></div>').appendTo(box);
		fields.lon.$wrapper.after(box);

		const map = L.map(canvas[0], { maxZoom: 22, scrollWheelZoom: false, zoomControl: false }).setView([33.3152, 44.3661], 4);
		L.control.scale({ imperial: false, position: 'bottomleft' }).addTo(map);
		if (map.attributionControl) map.attributionControl.addAttribution('Natural Earth');

		const state = {
			lat: fields.lat, lon: fields.lon, docname, box, map, status, marker: null,
			tileLayer: null, offlineLayer: null, packLayer: null, editable: current.editable,
		};
		states.set(frm, state);

		if (window.ResizeObserver) {
			state.resizeObserver = new ResizeObserver(() => {
				if (states.get(frm) === state && canvas[0].clientWidth && canvas[0].clientHeight) map.invalidateSize();
			});
			state.resizeObserver.observe(canvas[0]);
		}

		// Invalidate when the enclosing tab/section becomes visible.
		const watchVisibility = () => {
			let wasHidden = !canvas[0].offsetParent;
			state.tabObserver = new MutationObserver(() => {
				const hidden = !canvas[0].offsetParent;
				if (wasHidden && !hidden) { setTimeout(() => map.invalidateSize(), 30); }
				wasHidden = hidden;
			});
			state.tabObserver.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['class','style','hidden'] });
		};
		watchVisibility();

		// Register click-to-pick via the shared MeasureTool set to 'pick' mode.
		const Kit = window.SirajMapKit;
		state.measure = new Kit.MeasureTool(map, {
			onStatus: text => status.text(text),
			onPick: latlng => { if (current.editable) writePoint(frm, latlng); },
		});

		// Default click (no tool active) places the pin directly.
		map.on('click', e => {
			if (state.measure.isActive()) return;
			if (current.editable) writePoint(frm, e.latlng);
		});

		/* ------ Toolbar (shared declarative registry, form-map subset) ------ */
		const toolbar = L.control.sirajToolbar({ position: 'topright' }).addTo(map);
		state.toolbar = toolbar;
		const localPacks = new Map();

		// Navigate
		toolbar.group(t('Navigate'))
			.add({ icon:'zoom_in', label:t('In'),  action: () => map.zoomIn() })
			.add({ icon:'zoom_out',label:t('Out'), action: () => map.zoomOut() })
			.add({ icon:'home',    label:t('Home'),action: () => map.setView([33.3152, 44.3661], 4) })
			.add({ icon:'locate_me', label:t('My loc'), action: () => map.locate({ setView:true, maxZoom:12, enableHighAccuracy:true }) })
			.add({ icon:'locate', label:t('Coords'), menuTitle:t('Go to coordinates'), menu: pop => {
				const w = $('<div></div>').appendTo(pop);
				const row = $('<div style="display:flex;gap:4px"></div>').appendTo(w);
				const lat = $('<input type="number" step="any" min="-90" max="90" class="form-control input-sm" placeholder="' + t('Lat') + '">').appendTo(row);
				const lon = $('<input type="number" step="any" min="-180" max="180" class="form-control input-sm" placeholder="' + t('Lon') + '">').appendTo(row);
				$('<button type="button" class="btn btn-sm btn-primary" style="margin-top:4px">' + t('Go') + '</button>').appendTo(w).on('click', () => {
					const la = Number(lat.val()), lo = Number(lon.val());
					if (![la,lo].every(Number.isFinite) || Math.abs(la)>90 || Math.abs(lo)>180) return;
					map.setView([la,lo], Math.max(8, map.getZoom()));
				});
			}});

		// Basemap (same switcher as Explorer, kept consistent)
		const selectBasemap = val => {
			if (state.tileLayer) { map.removeLayer(state.tileLayer); state.tileLayer = null; }
			if (state.packLayer) { map.removeLayer(state.packLayer); state.packLayer = null; }
			map.setMinZoom(0);
			const pack = localPacks.get(String(val).replace(/^pack-/, ''));
			if (pack) {
				if (state.offlineLayer) map.removeLayer(state.offlineLayer);
				map.setMinZoom(pack.minzoom);
				state.packLayer = L.tileLayer('/api/method/siraj_research.local_maps.tile?kind=' + encodeURIComponent(pack.kind) + '&z={z}&x={x}&y={y}', {
					minZoom: pack.minzoom, maxZoom: 22, maxNativeZoom: pack.maxzoom, attribution: pack.attribution || ''
				}).addTo(map);
				state.packLayer.on('tileerror', () => status.text(t('Some local tiles are unavailable at this location or zoom.')));
			} else if (val === 'online') {
				if (state.offlineLayer) map.removeLayer(state.offlineLayer);
				state.tileLayer = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
					maxZoom:22, maxNativeZoom:19, attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
				}).addTo(map);
				status.text(t('Online tiles disclose your IP address and viewed area to OpenStreetMap.'));
			} else {
				if (state.offlineLayer) state.offlineLayer.addTo(map).bringToBack();
			}
		};
		const basemapMenu = pop => {
			const w = $('<div></div>').appendTo(pop);
			const opt = (val, icon, label, active) => {
				const b = $('<button type="button" class="siraj-toolbar-opt"></button>')
					.html((window.sirajIcons ? window.sirajIcons.toolSvg(icon,{size:16}) : '') + '<span>' + label + '</span>');
				if (active) b.addClass('is-active');
				b.on('click', () => { w.find('.is-active').removeClass('is-active'); b.addClass('is-active'); selectBasemap(val); });
				b.appendTo(w); return b;
			};
			opt('local','offline',t('Offline basemap'),true);
			opt('online','online',t('Online: OpenStreetMap'),false);
			$('<hr>').appendTo(w);
			$('<div style="font-size:11px;color:var(--text-muted);padding:4px"></div>').text(t('Downloaded local packs appear here.')).appendTo(w);
			frappe.call({method:'siraj_research.local_maps.available_packs', type:'GET', silent:true}).then(res => {
				if (states.get(frm) !== state || !Array.isArray(res.message)) return;
				res.message.forEach(pack => {
					if (pack.unavailable || !['standard','aerial'].includes(pack.kind)) return;
					localPacks.set(pack.kind, pack);
					opt('pack-'+pack.kind,'layers', pack.kind==='aerial'?t('Local aerial'):t('Local standard'), false);
				});
			}).catch(()=>{});
		};
		toolbar.group(t('Basemap'))
			.add({ icon:'layers', label:t('Basemap'), menuTitle:t('Basemap'), menu: basemapMenu });

		toolbar.separator();

		// Measurement group (uses the shared MeasureTool state machine)
		toolbar.group(t('Measure'))
			.add({ icon:'ruler',   label:t('Distance'), action: () => state.measure.activate('distance') })
			.add({ icon:'area',    label:t('Area'),     action: () => state.measure.activate('area') })
			.add({ icon:'radius',  label:t('Radius'),   action: () => state.measure.activate('radius') })
			.add({ icon:'bearing', label:t('Bearing'),  action: () => state.measure.activate('bearing') })
			.add({ icon:'clear',   label:t('Clear'),    action: () => state.measure.clear() });

		toolbar.separator();

		// Point actions
		toolbar.group(t('Point'))
			.add({ icon:'pick',  label:t('Pick'), action: () => {
				if (!current.editable) { status.text(t('You do not have write access to these coordinates.')); return; }
				status.text(t('Click the map to place this record.'));
				state.measure.activate('pick');
			}})
			.add({ icon:'clear', label:t('Clear'), action: async () => {
				if (!current.editable || frm.docname !== state.docname) return;
				try { await frm.set_value({latitude:'', longitude:''}); update(frm, false); }
				catch (_) { status.text(t('Could not clear the coordinate fields.')); }
			}});

		// Wire input fields for bidirectional sync.
		for (const field of [fields.lat, fields.lon]) {
			field.$input?.off('.sirajCoordinates').on('input.sirajCoordinates change.sirajCoordinates', () => update(frm));
		}

		update(frm);
		setTimeout(() => { if (states.get(frm) === state) map.invalidateSize(); }, 0);

		// Load offline base layer (countries-110m topojson) the same way Explorer does.
		try {
			const response = await fetch('/assets/siraj_research/vendor/world-atlas/countries-110m.json');
			if (!response.ok) throw new Error('basemap');
			const world = await response.json();
			if (states.get(frm) !== state) return;
			state.offlineLayer = L.geoJSON(topojson.feature(world, world.objects.countries), {
				style: { color:'#7793a0', weight:1, fillColor:'#eef3ed', fillOpacity:1 }, interactive:false,
			});
			if (!state.tileLayer && !state.packLayer) state.offlineLayer.addTo(map);
			if (state.marker?.bringToFront) state.marker.bringToFront();
		} catch (_) { if (states.get(frm) === state) status.text(t('Offline basemap could not be loaded. Online tiles remain optional.')); }
	}

	$(document).on('form-refresh.sirajCoordinates', (_event, frm) => {
		if (!frm || !frm.doctype) return;
		if (frm.fields_dict?.latitude && frm.fields_dict?.longitude && !registered.has(frm.doctype)) {
			registered.add(frm.doctype);
			frappe.ui.form.on(frm.doctype, { latitude: (f) => update(f), longitude: (f) => update(f) });
		}
		setTimeout(() => mount(frm), 0);
	});
})();
