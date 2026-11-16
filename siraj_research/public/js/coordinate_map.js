/* Generic Desk form coordinate picker. No server calls or automatic external tiles. */
(() => {
	'use strict';
	const states = new WeakMap();
	const registered = new Set();
	const textTypes = new Set(['Data', 'Small Text', 'Text', 'Long Text']);
	let assetsPromise;
	const t = s => __(s);
	const assets = () => {
		if (!assetsPromise) {
			assetsPromise = Promise.resolve(frappe.require([
				'/assets/siraj_research/vendor/leaflet/leaflet.css',
				'/assets/siraj_research/vendor/leaflet/leaflet.js',
				'/assets/siraj_research/vendor/topojson/topojson-client.min.js',
			])).catch(error => { assetsPromise = null; throw error; });
		}
		return assetsPromise;
	};
	function parseCoordinate(value, max) {
		if (value === undefined || value === null) return null;
		const normalized = String(value).trim()
			.replace(/[٠-٩]/g, c => String(c.charCodeAt(0) - 0x660))
			.replace(/[۰-۹]/g, c => String(c.charCodeAt(0) - 0x6f0))
			.replace(/٫/g, '.');
		if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(normalized)) return null;
		const unsigned = normalized.replace(/^[+-]/, '');
		const [wholePart, fraction = ''] = unsigned.split('.');
		const whole = (wholePart || '0').replace(/^0+(?=\d)/, '');
		const bound = String(max);
		if (whole.length > bound.length || (whole.length === bound.length && whole > bound) ||
			(whole === bound && /[1-9]/.test(fraction))) return null;
		const number = Number(normalized);
		return Number.isFinite(number) ? number : null;
	}
	function decimalText(number) {
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
		return {lat, lon, editable: a === 'Write' && b === 'Write' && textTypes.has(lat.df.fieldtype) && textTypes.has(lon.df.fieldtype),
			textFields: textTypes.has(lat.df.fieldtype) && textTypes.has(lon.df.fieldtype)};
	}
	function currentValue(field, doc, name) {
		if (field.get_status() === 'Write' && field.$input && field.$input.length) return field.$input.val();
		return doc[name];
	}
	function remove(frm) {
		const state = states.get(frm);
		if (!state) return;
		state.lat.$input?.off('.sirajCoordinates');
		state.lon.$input?.off('.sirajCoordinates');
		if (state.resizeObserver) state.resizeObserver.disconnect();
		if (state.map) state.map.remove();
		state.box.remove();
		states.delete(frm);
	}
	function update(frm, center = true) {
		const state = states.get(frm), fields = controls(frm);
		if (!state) return;
		if (!fields || fields.lat !== state.lat || fields.lon !== state.lon || frm.docname !== state.docname) {
			remove(frm); return;
		}
		state.editable = fields.editable;
		state.clear.prop('disabled', !fields.editable);
		const a = currentValue(fields.lat, frm.doc, 'latitude');
		const b = currentValue(fields.lon, frm.doc, 'longitude');
		const lat = parseCoordinate(a, 90), lon = parseCoordinate(b, 180);
		if (lat === null || lon === null) {
			if (state.marker) { state.map.removeLayer(state.marker); state.marker = null; }
			state.status.text((String(a ?? '').trim() || String(b ?? '').trim())
				? t('Enter valid decimal coordinates: latitude −90 to 90, longitude −180 to 180.')
				: t('Enter coordinates or select a point on the map.'));
		} else {
			if (!state.marker) state.marker = L.marker([lat, lon]).addTo(state.map);
			else state.marker.setLatLng([lat, lon]);
			if (center) state.map.setView([lat, lon], Math.max(state.map.getZoom(), 6));
			state.status.text(t('Location shown. Typed coordinate text is not rounded by the map.'));
		}
		if (!fields.textFields) state.status.text(t('Preview only: both coordinate fields must be text fields to select a point.'));
		else if (!fields.editable) state.status.text(t('Location preview (read-only).'));
	}
	async function writePoint(frm, latlng) {
		const state = states.get(frm), fields = controls(frm);
		if (!state || !fields || !fields.editable || frm.docname !== state.docname) return;
		const latitude = Number(latlng.lat), longitude = Number(latlng.lng);
		if (!Number.isFinite(latitude) || !Number.isFinite(longitude) || Math.abs(latitude) > 90 || Math.abs(longitude) > 180) return;
		const latText = decimalText(latitude), lonText = decimalText(longitude);
		const maxLength = field => Number(field.df.length) > 0 ? Number(field.df.length) : (field.df.fieldtype === 'Data' ? 140 : Infinity);
		if (latText.length > maxLength(fields.lat) || lonText.length > maxLength(fields.lon)) { state.status.text(t('Selected coordinates exceed the text field length.')); return; }
		try {
			await frm.set_value({latitude: latText, longitude: lonText});
			update(frm, false);
		} catch (_) { state.status.text(t('Could not update the coordinate fields.')); }
	}
	async function mount(frm) {
		const fields = controls(frm);
		if (!fields || !fields.lon.$wrapper?.length) { remove(frm); return; }
		const old = states.get(frm);
		if (old && old.docname === frm.docname && old.lat === fields.lat && old.lon === fields.lon && old.box[0].isConnected) {
			update(frm); setTimeout(() => { if (states.get(frm) === old) old.map.invalidateSize(); }, 0); return;
		}
		remove(frm);
		const docname = frm.docname;
		try { await assets(); } catch (_) { return; }
		const current = controls(frm);
		if (frm.docname !== docname || !current || current.lat !== fields.lat || current.lon !== fields.lon || states.has(frm)) return;
		const box = $('<div class="siraj-coordinate-map"></div>').css({margin: '12px 0', clear: 'both'});
		const heading = $('<div></div>').css({fontWeight: '600', marginBottom: '6px'}).text(t('Coordinate map')).appendTo(box);
		const help = $('<div></div>').css({marginBottom: '6px'}).text(t('Click the map to select a point, or type latitude and longitude above.')).appendTo(box);
		const toolbar = $('<div></div>').css({display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '8px'}).appendTo(box);
		const clear = $('<button type="button" class="btn btn-default btn-xs"></button>').text(t('Clear coordinates')).appendTo(toolbar);
		const tiles = $('<button type="button" class="btn btn-default btn-xs"></button>').text(t('Enable online street map')).appendTo(toolbar);
		const notice = $('<div></div>').css({fontSize: '12px', marginBottom: '6px'}).text(t('Online map tiles are optional; enabling them shares your IP address and viewed area with OpenStreetMap.')).appendTo(box);
		const canvas = $('<div role="region"></div>').attr('aria-label', t('Coordinate map')).css({height: '320px', width: '100%', background: '#dce8ed'}).appendTo(box);
		const status = $('<div role="status" aria-live="polite"></div>').css({marginTop: '6px'}).appendTo(box);
		fields.lon.$wrapper.after(box);
		const map = L.map(canvas[0], {maxZoom: 22, scrollWheelZoom: false}).setView([33.3152, 44.3661], 4);
		if (map.attributionControl) map.attributionControl.addAttribution('Natural Earth');
		const state = {lat: fields.lat, lon: fields.lon, docname, box, map, status, clear, marker: null, tileLayer: null, editable: fields.editable, offlineLayer: null, packLayer: null};
		states.set(frm, state);
		if (window.ResizeObserver) {
			state.resizeObserver = new window.ResizeObserver(() => {
				if (states.get(frm) === state && canvas[0].clientWidth && canvas[0].clientHeight) map.invalidateSize();
			});
			state.resizeObserver.observe(canvas[0]);
		}
		map.on('click', e => writePoint(frm, e.latlng));
		clear.on('click', async () => {
			if (!controls(frm)?.editable || frm.docname !== state.docname) return;
			try { await frm.set_value({latitude: '', longitude: ''}); update(frm, false); }
			catch (_) { status.text(t('Could not update the coordinate fields.')); }
		});
		const packSelect = $('<select class="form-control input-sm"></select>').attr('aria-label', t('Local basemap')).hide().appendTo(toolbar);
		$('<option value=""></option>').text(t('Local overview')).appendTo(packSelect);
		const localPacks = new Map();
		frappe.call({method: 'siraj_research.local_maps.available_packs', type: 'GET', silent: true, error_handlers: {403: () => {}}}).then(res => {
			if (states.get(frm) !== state || !Array.isArray(res.message)) return;
			res.message.forEach(pack => {
				if (pack.unavailable || !['standard', 'aerial'].includes(pack.kind)) return;
				localPacks.set(pack.kind, pack);
				$('<option></option>').val(pack.kind).text(pack.kind === 'aerial' ? t('Local aerial') : t('Local standard')).appendTo(packSelect);
			});
			if (localPacks.size) packSelect.show();
		}).catch(() => {});
		packSelect.on('change', () => {
			if (state.tileLayer) { map.removeLayer(state.tileLayer); state.tileLayer = null; tiles.text(t('Enable online street map')); }
			if (state.packLayer) { map.removeLayer(state.packLayer); state.packLayer = null; }
			map.setMinZoom(0);
			const pack = localPacks.get(packSelect.val());
			if (!pack) { if (state.offlineLayer) state.offlineLayer.addTo(map); return; }
			if (state.offlineLayer) map.removeLayer(state.offlineLayer);
			map.setMinZoom(pack.minzoom);
			const url = '/api/method/siraj_research.local_maps.tile?kind=' + encodeURIComponent(pack.kind) + '&z={z}&x={x}&y={y}';
			state.packLayer = L.tileLayer(url, {minZoom: pack.minzoom, maxZoom: 22, maxNativeZoom: pack.maxzoom,
				attribution: $('<div></div>').text(pack.attribution || '').html()}).addTo(map);
			state.packLayer.on('tileerror', () => status.text(t('Some local tiles are unavailable at this location or zoom.')));
		});
		tiles.on('click', () => {
			if (state.tileLayer) {
				map.removeLayer(state.tileLayer); state.tileLayer = null;
				if (state.offlineLayer) state.offlineLayer.addTo(map);
				tiles.text(t('Enable online street map'));
			} else {
				if (state.offlineLayer) map.removeLayer(state.offlineLayer);
				if (state.packLayer) { map.removeLayer(state.packLayer); state.packLayer = null; packSelect.val(''); map.setMinZoom(0); }
				state.tileLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
					maxZoom: 22, maxNativeZoom: 19, attribution: '&copy; OpenStreetMap contributors',
				}).addTo(map);
				tiles.text(t('Disable online street map'));
			}
		});
		for (const field of [fields.lat, fields.lon]) field.$input?.off('.sirajCoordinates').on('input.sirajCoordinates change.sirajCoordinates', () => update(frm));
		update(frm);
		setTimeout(() => { if (states.get(frm) === state) map.invalidateSize(); }, 0);
		try {
			const response = await fetch('/assets/siraj_research/vendor/world-atlas/countries-110m.json');
			if (!response.ok) throw new Error('basemap');
			const world = await response.json();
			if (states.get(frm) !== state) return;
			state.offlineLayer = L.geoJSON(topojson.feature(world, world.objects.countries), {
				style: {color: '#7793a0', weight: 1, fillColor: '#eef3ed', fillOpacity: 1}, interactive: false,
			});
			if (!state.tileLayer && !state.packLayer) state.offlineLayer.addTo(map);
			if (state.marker?.bringToFront) state.marker.bringToFront();
		} catch (_) { if (states.get(frm) === state) status.text(t('Offline basemap could not be loaded. Online tiles remain optional.')); }
	}
	$(document).on('form-refresh.sirajCoordinates', (_event, frm) => {
		if (!frm || !frm.doctype) return;
		if (frm.fields_dict?.latitude && frm.fields_dict?.longitude && !registered.has(frm.doctype)) {
			registered.add(frm.doctype);
			frappe.ui.form.on(frm.doctype, {latitude: update, longitude: update});
		}
		setTimeout(() => mount(frm), 0);
	});
})();
