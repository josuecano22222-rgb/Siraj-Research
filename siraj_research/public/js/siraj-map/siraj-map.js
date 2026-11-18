/* siraj-map.js — engine abstraction for SIRAJ maps.
 *
 * Creates a map instance and exposes a small engine-neutral API (fit, setCenter,
 * addSource, addLayer, on, off, remove) so the rest of the application never
 * talks to MapLibre or Leaflet directly. This lets us migrate surfaces from
 * Leaflet to MapLibre GL incrementally and swap engines later (e.g. MapLibre v6,
 * or a WebGPU engine) without changing call sites.
 *
 * Today:
 *   - 'maplibre' is the recommended engine for new surfaces (Explorer, forms,
 *     the new native Map view replacement).
 *   - 'leaflet' is retained as a compatibility target while surfaces are
 *     migrated; it will be removed once the purge is complete.
 *
 * The factory returns an object with:
 *   .engine         'maplibre' | 'leaflet'
 *   .map            the underlying engine map instance
 *   .container      DOM element
 *   .addControl(ctl, pos)
 *   .fit(bounds, opts)
 *   .setView(lnglat, zoom)
 *   .on(evt, fn) / .off(evt, fn)
 *   .addMarker(opts) -> {setLngLat, setPopup, remove}
 *   .addGeojsonSource(id, geojson)
 *   .addVectorLayer(spec)
 *   .remove()
 *   ._registerTool/activateTool/deactivateTool (thin wrapper for shared state)
 */
(() => {
	'use strict';
	// Map engine build tag — mirrors window.SIRAJ_BUILD from siraj-record-meta.js
	// so diagnostic lines in the console agree on the deployed revision.
	const SIRAJ_MAP_BUILD = (window.SIRAJ_BUILD) || '2026-11-17.coord-field-slice-a.28';
	console.info('%c[SIRAJ Map]', 'color:#0c5e5b;font-weight:bold', 'build', SIRAJ_MAP_BUILD, '| default engine: maplibre');

	const engines = { maplibre: null, leaflet: null };
	let loaded = { maplibre: false, leaflet: false };

	function loadMapLibre() {
		if (loaded.maplibre) return Promise.resolve();
		return new Promise((res, rej) => {
			if (window.maplibregl) { loaded.maplibre = true; return res(); }
			frappe.require([
				'/assets/siraj_research/vendor/maplibre-gl/maplibre-gl.css',
				'/assets/siraj_research/vendor/maplibre-gl/maplibre-gl.js',
			], () => {
				if (!window.maplibregl) return rej(new Error('maplibre-gl failed to load'));
				// RTL text plugin for Arabic shaping. Worker path for CSP.
				try {
					if (window.maplibregl.getRTLTextPluginStatus && maplibregl.getRTLTextPluginStatus() === 'unavailable') {
						maplibregl.setRTLTextPlugin('/assets/siraj_research/vendor/maplibre-gl/maplibre-gl-rtl-text.js', true);
					}
					maplibregl.workerUrl = '/assets/siraj_research/vendor/maplibre-gl/maplibre-gl-csp-worker.js';
				} catch (_) { /* non-fatal: Arabic labels will render unshaped */ }
				loaded.maplibre = true; res();
			});
		});
	}
	function loadLeaflet() {
		if (loaded.leaflet) return Promise.resolve();
		return new Promise((res, rej) => {
			if (window.L) { loaded.leaflet = true; return res(); }
			frappe.require([
				'/assets/siraj_research/vendor/leaflet/leaflet.css',
				'/assets/siraj_research/vendor/leaflet/leaflet.js',
			], () => { if (!window.L) rej(new Error('leaflet failed to load')); else { loaded.leaflet = true; res(); } });
		});
	}

	/* ---------------- MapLibre adapter ---------------- */
	async function createMapLibre(container, opts) {
		await loadMapLibre();
		const ml = window.maplibregl;
		// Default style: solid background only. No text labels, no glyph PBFs, no
		// external requests of any kind. Label layers and glyphs endpoint must be
		// added explicitly by a later basemap style (vector PMTiles) once local
		// font PBFs are bundled; demotiles.maplibre.org must never be referenced
		// in the default configuration.
		const style = opts.style || {
			version: 8,
			name: 'siraj-offline-zero',
			sources: {},
			layers: [
				{ id: 'background', type: 'background', paint: { 'background-color': '#e8e4cf' } },
			],
			// glyphs intentionally omitted; styles that render labels must set this
			// to a locally-hosted URL (e.g. '/assets/siraj_research/fonts/{fontstack}/{range}.pbf').
		};
		const map = new ml.Map({
			container,
			style,
			center: opts.center || [44.3661, 33.3152],   // [lng, lat] for MapLibre
			zoom: opts.zoom || 4,
			minZoom: opts.minZoom || 0,
			maxZoom: opts.maxZoom || 22,
			attributionControl: { compact: true },
			scrollZoom: opts.scrollZoom === false ? false : true,
		});
		// Controls
		if (opts.navControl !== false) map.addControl(new ml.NavigationControl({ visualizePitch: true }), 'top-right');
		if (opts.scale !== false) map.addControl(new ml.ScaleControl({ unit: 'metric' }), 'bottom-left');
		return {
			engine: 'maplibre', map, container, ml,
			addControl(ctl, pos) { map.addControl(ctl, pos || 'top-right'); return this; },
			fit(bounds, o) { map.fitBounds(bounds, Object.assign({padding:20}, o||{})); return this; },
			setView(lnglat, z) { map.flyTo({center: lnglat, zoom: z == null ? map.getZoom() : z}); return this; },
			on(ev, fn) { map.on(ev, fn); return this; },
			off(ev, fn) { map.off(ev, fn); return this; },
			addGeojsonSource(id, geojson) {
				if (map.getSource(id)) map.removeSource(id);
				map.addSource(id, { type:'geojson', data: geojson || {type:'FeatureCollection', features:[]}, cluster: opts.cluster || false, clusterMaxZoom: 14 });
				return this;
			},
			addMarker(o) {
				const el = document.createElement('div');
				el.className = 'sx-pin-wrapper';
				if (o && o.html) el.innerHTML = o.html;
				const m = new ml.Marker({ element: el, anchor: 'center', draggable: !!(o && o.draggable) }).setLngLat(o.lnglat || opts.center).addTo(map);
				return {
					setLngLat(ll) { m.setLngLat(ll); return this; },
					getLngLat() { return m.getLngLat(); },
					setPopup(html) { const p = new ml.Popup({offset:20}).setHTML(html); m.setPopup(p); return this; },
					on(ev,fn){m.on(ev,fn);return this;},
					remove() { m.remove(); }
				};
			},
			remove() { map.remove(); },
		};
	}

	/* ---------------- Leaflet adapter (compatibility shim) ---------------- */
	async function createLeaflet(container, opts) {
		await loadLeaflet();
		const L = window.L;
		const map = L.map(container, {
			zoomControl: false, worldCopyJump: true,
			minZoom: opts.minZoom || 0, maxZoom: opts.maxZoom || 22,
			scrollWheelZoom: opts.scrollZoom !== false,
			zoomSnap: 0.25,
			// Keep pins/popups inside the frame (containers are overflow:hidden).
			autoPanPadding: [60, 60],
		}).setView([(opts.center||[])[1] || 33.3152, (opts.center||[])[0] || 44.3661], opts.zoom || 4);
		L.control.scale({imperial:false, position:'bottomleft'}).addTo(map);
		return {
			engine: 'leaflet', map, container, L,
			addControl(ctl, pos) { if (ctl.addTo) ctl.addTo(map); else map.addControl(ctl); return this; },
			fit(bounds, o) { map.fitBounds(bounds, o||{}); return this; },
			setView(lnglat, z) { map.setView([lnglat[1], lnglat[0]], z == null ? map.getZoom() : z); return this; },
			on(ev, fn) { map.on(ev, fn); return this; },
			off(ev, fn) { map.off(ev, fn); return this; },
			addGeojsonSource() { /* no-op; legacy surfaces use L.geoJSON directly */ return this; },
			addMarker(o) {
				const m = L.marker([o.lnglat[1], o.lnglat[0]], { icon: o.icon, draggable: !!o.draggable }).addTo(map);
				return { setLngLat(ll){m.setLatLng([ll[1],ll[0]]);return this;}, getLngLat(){const p=m.getLatLng();return[p.lng,p.lat];}, setPopup(h){m.bindPopup(h);return this;}, on(ev,fn){m.on(ev,fn);return this;}, remove(){map.removeLayer(m);} };
			},
			remove() { map.remove(); },
		};
	}

	/* ---------------- Public factory ---------------- */
	window.SirajMap = {
		BUILD: SIRAJ_MAP_BUILD,
		async create(container, opts = {}) {
			const engine = opts.engine || (window.SIRAJ_MAP_DEFAULT_ENGINE || 'maplibre');
			if (engine === 'maplibre') return createMapLibre(container, opts);
			if (engine === 'leaflet') return createLeaflet(container, opts);
			throw new Error('SirajMap: unknown engine "' + engine + '"');
		},
		setDefaultEngine(engine) { window.SIRAJ_MAP_DEFAULT_ENGINE = engine; },
	};
})();
