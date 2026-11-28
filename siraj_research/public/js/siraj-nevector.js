/* siraj-nevector.js — Natural Earth Vector basemap + advanced map layers.
 *
 * Renders the Natural Earth Vector dataset (public domain, see
 * public/natural_earth/LICENSE.md) as a proper *vector* basemap on both
 * engines supported by the SIRAJ map kit:
 *
 *   - MapLibre GL: geojson sources + fill/line/circle/symbol layers.
 *   - Leaflet (offline viewer): L.geoJSON groups.
 *
 * Advanced capabilities
 * ---------------------
 *   1. Scale-tiered basemap: world zoom uses the 1:110m tier, mid-zoom the
 *      1:50m tier, detailed views the 1:10m tier — falling back to the
 *      finest *available* tier when a tier has not been provisioned.
 *   2. Choropleth: colour the admin-0 countries layer by any property
 *      (setChoropleth) with a sequential scale and legend.
 *   3. Click-to-country: map clicks resolve to the country feature under
 *      the cursor and invoke a callback with its properties (ISO codes,
 *      name, continent, population, …).
 *   4. Full cultural + physical layer set: ocean, land, lakes, boundaries,
 *      state/province lines, rivers, populated places (labels included).
 *
 * Data is fetched from
 *   /api/method/siraj_research.api.natural_earth_vector.layer?layer=<name>
 * which serves the bundled 1:110m tier out of the box and any provisioned
 * 50m/10m pack tiers from private storage.
 *
 * 5. Country intelligence + data-driven choropleth: country facts (capital,
 *    population, GDP, area, Arabic name) and site-data choropleths that
 *    aggregate Siraj records onto Natural Earth countries — so the map is
 *    driven by the application's own data rather than caller-supplied values.
 */
(() => {
	'use strict';

	const LAYER_API = '/api/method/siraj_research.api.natural_earth_vector.layer';
	const MANIFEST_API = '/api/method/siraj_research.api.natural_earth_vector.manifest';
	const COUNTRY_PROFILE_API = '/api/method/siraj_research.api.natural_earth_vector.country_profile';
	const CHOROPLETH_API = '/api/method/siraj_research.api.natural_earth_vector.country_choropleth';

	/* The admin-0 countries layer exposes ADM0_A3 as a feature property for
	 * every country (ISO_A3 is '-99' for 5, e.g. France), so it is the
	 * reliable join key for the data-driven choropleth. */
	const COUNTRY_JOIN_FIELD = 'ADM0_A3';

	/* Which catalog file fills each basemap role, per scale tier. The first
	 * candidate that is available on the server wins; missing roles are
	 * skipped gracefully. */
	const LAYER_PLAN = {
		ocean:     ['ne_{s}_ocean'],
		land:      ['ne_{s}_land'],
		lakes:     ['ne_{s}_lakes'],
		countries: ['ne_{s}_admin_0_countries'],
		boundaries:['ne_{s}_admin_0_boundary_lines_land', 'ne_{s}_coastline'],
		admin1:    ['ne_{s}_admin_1_states_provinces_lines'],
		rivers:    ['ne_{s}_rivers_lake_centerlines'],
		places:    ['ne_{s}_populated_places_simple', 'ne_{s}_populated_places'],
	};

	/* Sequential choropleth palette (light → dark). */
	const CHOROPLETH_COLORS = [
		'#ffffcc', '#fed976', '#feb24c', '#fd8d3c',
		'#fc4e2a', '#e31a1c', '#b10026',
	];

	let _manifestPromise = null;
	let _layerCache = new Map();    // name -> parsed GeoJSON
	let _layerPromises = new Map(); // name -> in-flight fetch

	function _fetchManifest() {
		if (_manifestPromise) return _manifestPromise;
		_manifestPromise = fetch(MANIFEST_API)
			.then(r => { if (!r.ok) throw new Error('manifest HTTP ' + r.status); return r.json(); })
			.then(m => ({
				available: new Set(m.available_scales || []),
				tiers: m.zoom_tiers || [],
			}))
			.catch(e => { console.warn('[SirajNeVector] manifest unavailable:', e.message);
				return { available: new Set(['110m']), tiers: [] }; });
		return _manifestPromise;
	}

	function _fetchLayer(name) {
		if (_layerCache.has(name)) return Promise.resolve(_layerCache.get(name));
		if (_layerPromises.has(name)) return _layerPromises.get(name);
		const p = fetch(`${LAYER_API}?layer=${encodeURIComponent(name)}`)
			.then(r => { if (!r.ok) throw new Error('layer ' + name + ' HTTP ' + r.status); return r.text(); })
			.then(text => {
				const gj = JSON.parse(text);
				_layerCache.set(name, gj);
				return gj;
			})
			.catch(e => { _layerPromises.delete(name); throw e; });
		_layerPromises.set(name, p);
		return p;
	}

	/* Generic JSON GET for the country-intelligence endpoints. Returns null
	 * on any failure so callers can degrade gracefully (e.g. no API). */
	function _fetchJSON(url) {
		return fetch(url)
			.then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
			.catch(e => { console.warn('[SirajNeVector] request failed:', url, e.message); return null; });
	}

	/**
	 * Fetch normalized country facts from the bundled Natural Earth pack.
	 * Pass an ISO_A3 `code`, or a `longitude` + `latitude` coordinate pair.
	 * Returns null when the code/coordinate matches no country (e.g. ocean).
	 */
	function fetchCountryProfile(opts) {
		opts = opts || {};
		const params = new URLSearchParams();
		if (opts.code) params.set('code', opts.code);
		if (opts.longitude != null) params.set('longitude', opts.longitude);
		if (opts.latitude != null) params.set('latitude', opts.latitude);
		const qs = params.toString();
		return _fetchJSON(COUNTRY_PROFILE_API + (qs ? '?' + qs : ''));
	}

	/**
	 * Fetch a data-driven choropleth: aggregates Siraj site records of
	 * `doctype` onto Natural Earth countries. Returns
	 * {method, classes, breaks, min, max, empty, valueByKey, classByKey,
	 *  matchedCount, unmatchedCount, recordCount} or null on failure.
	 */
	function fetchSiteChoropleth(doctype, opts) {
		opts = opts || {};
		const params = new URLSearchParams();
		params.set('doctype', doctype);
		if (opts.agg) params.set('agg', opts.agg);
		if (opts.value_field) params.set('value_field', opts.value_field);
		if (opts.method) params.set('method', opts.method);
		if (opts.classes) params.set('classes', opts.classes);
		return _fetchJSON(CHOROPLETH_API + '?' + params.toString());
	}

	function _selectScale(zoom, available, tiers) {
		const wanted = (tiers.find(t => zoom <= t.max_zoom) || { scale: '10m' }).scale;
		if (available.has(wanted)) return wanted;
		for (const cand of ['10m', '50m', '110m']) {
			if (available.has(cand)) return cand;
		}
		return wanted;
	}

	function _roleFiles(scale) {
		const files = {};
		for (const [role, candidates] of Object.entries(LAYER_PLAN)) {
			files[role] = candidates.map(c => c.replace('{s}', scale));
		}
		return files;
	}

	/* ---------------- Choropleth helpers ---------------- */

	function _colorFor(value, min, max) {
		if (value == null || Number.isNaN(value)) return '#cccccc';
		const t = max === min ? 0.5 : (value - min) / (max - min);
		const idx = Math.min(CHOROPLETH_COLORS.length - 1,
			Math.max(0, Math.round(t * (CHOROPLETH_COLORS.length - 1))));
		return CHOROPLETH_COLORS[idx];
	}

	function choroplethLegend(min, max) {
		const rows = CHOROPLETH_COLORS.map((c, i) => {
			const t = CHOROPLETH_COLORS.length === 1 ? 0.5 : i / (CHOROPLETH_COLORS.length - 1);
			const v = (min + t * (max - min)).toFixed(2);
			return `<div class="ne-legend-row"><span class="ne-legend-swatch" style="background:${c}"></span>${v}</div>`;
		}).join('');
		return `<div class="ne-legend"><div class="ne-legend-title">${min} → ${max}</div>${rows}</div>`;
	}

	/* Layer definitions per role. Each references only its own source so a
	 * role that failed to load never leaves a dangling layer. */
	function _mlDefs(role, colorExpr) {
		const defs = {
			ocean: [{
				id: 'ne-ocean', type: 'fill', source: 'ne-ocean',
				paint: { 'fill-color': '#d4e4f0', 'fill-opacity': 0.9 },
			}],
			land: [{
				id: 'ne-land', type: 'fill', source: 'ne-land',
				paint: { 'fill-color': '#e8e4cf' },
			}],
			lakes: [{
				id: 'ne-lakes', type: 'fill', source: 'ne-lakes',
				paint: { 'fill-color': '#5b8db8', 'fill-opacity': 0.8 },
			}],
			countries: [{
				id: 'ne-countries', type: 'fill', source: 'ne-countries',
				paint: { 'fill-color': colorExpr || '#d9d0b8', 'fill-opacity': 0.6 },
			}],
			boundaries: [{
				id: 'ne-boundaries', type: 'line', source: 'ne-boundaries',
				paint: { 'line-color': '#7a6a4f', 'line-width': 0.6 },
			}],
			admin1: [{
				id: 'ne-admin1', type: 'line', source: 'ne-admin1',
				paint: { 'line-color': '#9a8b6e', 'line-width': 0.35, 'line-dasharray': [2, 1] },
			}],
			rivers: [{
				id: 'ne-rivers', type: 'line', source: 'ne-rivers',
				paint: { 'line-color': '#5b8db8', 'line-width': 0.4 },
			}],
			places: [
				{
					id: 'ne-places', type: 'circle', source: 'ne-places',
					paint: { 'circle-radius': 1.4, 'circle-color': '#555', 'circle-stroke-width': 0 },
				},
				{
					id: 'ne-place-labels', type: 'symbol', source: 'ne-places',
					layout: { 'text-field': ['get', 'name'], 'text-size': 8, 'text-optional': true },
					paint: { 'text-color': '#333' },
				},
			],
		};
		return defs[role] || [];
	}

	/* ---------------- MapLibre controller ---------------- */

	function attachMapLibre(map, opts) {
		opts = opts || {};
		const state = {
			map, scale: null, visible: true,
			choropleth: null, countryCb: null,
			_clickHandler: null,
		};

		function _removeLayer(id) {
			try { if (map.getLayer(id)) map.removeLayer(id); } catch (_) {}
		}

		function _addDefs(defs) {
			for (const def of defs) {
				_removeLayer(def.id);
				try { map.addLayer(def); } catch (_) { /* unknown paint prop, skip */ }
			}
		}

		function _ensureSource(sid) {
			if (!map.getSource(sid)) {
				map.addSource(sid, {
					type: 'geojson',
					data: { type: 'FeatureCollection', features: [] },
				});
			}
			return map.getSource(sid);
		}

		async function _build(scale) {
			const files = _roleFiles(scale);
			const loaded = {};
			for (const [role, candidates] of Object.entries(files)) {
				for (const cand of candidates) {
					try { await _fetchLayer(cand); loaded[role] = cand; break; }
					catch (_) { /* try next candidate */ }
				}
			}
			state.scale = scale;
			if (!state.visible) return loaded;

			// Remove old vector layers before rebuilding.
			['ne-ocean', 'ne-land', 'ne-lakes', 'ne-countries', 'ne-boundaries',
			 'ne-admin1', 'ne-rivers', 'ne-places', 'ne-place-labels'].forEach(_removeLayer);

			const colorExpr = state.choropleth ? state.choropleth.paintExpr : null;
			for (const [role, file] of Object.entries(loaded)) {
				const geojson = await _fetchLayer(file);
				const sid = 'ne-' + role;
				_ensureSource(sid).setData(geojson);
				_addDefs(_mlDefs(role, role === 'countries' ? colorExpr : null));
			}
			return loaded;
		}

		// Choropleth: valueByKey maps feature.<field> → numeric value.
		function setChoropleth(field, valueByKey, opts2) {
			opts2 = opts2 || {};
			const values = Object.values(valueByKey || {}).filter(v => typeof v === 'number');
			const min = values.length ? Math.min(...values) : 0;
			const max = values.length ? Math.max(...values) : 1;
			state.choropleth = {
				field, valueByKey, min, max,
				legend: opts2.legend !== false,
				paintExpr: ['match',
					['get', field],
					...Object.entries(valueByKey || {}).flatMap(([k, v]) => [k, _colorFor(v, min, max)]),
					'#cccccc'],
			};
			if (map.getLayer('ne-countries')) {
				map.setPaintProperty('ne-countries', 'fill-color', state.choropleth.paintExpr);
			}
			return {
				min, max,
				legendHtml: state.choropleth.legend ? choroplethLegend(min, max) : null,
			};
		}

		function clearChoropleth() {
			state.choropleth = null;
			if (map.getLayer('ne-countries')) {
				map.setPaintProperty('ne-countries', 'fill-color', '#d9d0b8');
			}
		}

		function onCountryClick(fn) {
			if (state._clickHandler) map.off('click', state._clickHandler);
			state.countryCb = fn;
			state._clickHandler = (e) => {
				if (!state.countryCb) return;
				const features = map.queryRenderedFeatures(e.point, { layers: ['ne-countries'] });
				if (features.length && features[0]) state.countryCb(features[0], e);
			};
			map.on('click', state._clickHandler);
		}

		/* Data-driven choropleth: aggregate Siraj site records of `doctype`
		 * onto countries server-side, then colour the countries layer. The
		 * values arrive already keyed by ADM0_A3 so every country matches. */
		async function setChoroplethFromSite(doctype, opts2) {
			opts2 = opts2 || {};
			const payload = await fetchSiteChoropleth(doctype, opts2);
			if (!payload || payload.empty || !payload.valueByKey) {
				return null;
			}
			const painted = setChoropleth(COUNTRY_JOIN_FIELD, payload.valueByKey, opts2);
			return { payload, painted };
		}

		/* Fetch normalized country facts for a clicked country feature. */
		function countryProfile(feature) {
			if (!feature || !feature.properties) return Promise.resolve(null);
			const code = feature.properties.ADM0_A3 || feature.properties.ISO_A3;
			if (!code) return Promise.resolve(null);
			return fetchCountryProfile({ code });
		}

		async function setScale(scale) {
			return _build(scale || state.scale);
		}

		function setVisible(v) {
			state.visible = !!v;
			['ne-ocean', 'ne-land', 'ne-lakes', 'ne-countries', 'ne-boundaries',
			 'ne-admin1', 'ne-rivers', 'ne-places', 'ne-place-labels'].forEach(id => {
				const layer = map.getLayer(id);
				if (layer) layer.setVisible(state.visible);
			});
		}

		function currentScale() { return state.scale; }

		function destroy() {
			if (state._clickHandler) map.off('click', state._clickHandler);
			['ne-ocean', 'ne-land', 'ne-lakes', 'ne-countries', 'ne-boundaries',
			 'ne-admin1', 'ne-rivers', 'ne-places'].forEach(sid => {
				try { if (map.getSource(sid)) map.removeSource(sid); } catch (_) {}
			});
			['ne-ocean', 'ne-land', 'ne-lakes', 'ne-countries', 'ne-boundaries',
			 'ne-admin1', 'ne-rivers', 'ne-places', 'ne-place-labels'].forEach(_removeLayer);
		}

			return _fetchManifest().then(m => {
				const initialZoom = opts.zoom != null ? opts.zoom :
					(map.getZoom ? map.getZoom() : 4);
				return _build(_selectScale(initialZoom, m.available, m.tiers));
			}).then(loaded => ({
				engine: 'maplibre',
				setScale, setVisible, currentScale,
				setChoropleth, clearChoropleth,
				setChoroplethFromSite, countryProfile,
				onCountryClick, destroy,
				_loaded: loaded,
			}));
	}

	/* ---------------- Leaflet controller (offline viewer) ---------------- */

	function attachLeaflet(map, opts) {
		opts = opts || {};
		const L = window.L;
		const state = {
			map, scale: null, visible: true,
			groups: {}, countryCb: null, choropleth: null,
		};

		function _clearGroups() {
			Object.values(state.groups).forEach(g => {
				if (g && map.hasLayer(g)) map.removeLayer(g);
			});
			state.groups = {};
		}

		async function _build(scale) {
			_clearGroups();
			const files = _roleFiles(scale);
			const loaded = {};
			for (const [role, candidates] of Object.entries(files)) {
				for (const cand of candidates) {
					try { await _fetchLayer(cand); loaded[role] = cand; break; }
					catch (_) { /* next candidate */ }
				}
			}
			state.scale = scale;
			if (!state.visible) return loaded;

			const styleFor = (role) => {
				switch (role) {
					case 'ocean': return { style: { color: '#d4e4f0', fillColor: '#d4e4f0', fillOpacity: 0.9 } };
					case 'land': return { style: { color: '#7a6a4f', fillColor: '#e8e4cf', fillOpacity: 1 } };
					case 'lakes': return { style: { color: '#5b8db8', fillColor: '#5b8db8', fillOpacity: 0.8 } };
					case 'rivers': return { style: { color: '#5b8db8', weight: 0.6 } };
					case 'admin1': return { style: { color: '#9a8b6e', weight: 0.4, dashArray: '2 1' } };
					case 'boundaries': return { style: { color: '#7a6a4f', weight: 0.6 } };
					default: return { style: { color: '#888', weight: 0.5 } };
				}
			};

			for (const [role, file] of Object.entries(loaded)) {
				const geojson = await _fetchLayer(file);
				const cfg = {
					onEachFeature(feature, layer) {
						layer.on('click', (e) => {
							L.DomEvent.stopPropagation(e);
							if (state.countryCb && role === 'countries') {
								state.countryCb({ properties: feature.properties, geometry: feature.geometry }, e);
							}
						});
					},
				};
				if (role === 'countries') {
					if (state.choropleth) {
						cfg.style = (feature) => {
							const v = state.choropleth.valueByKey[feature.properties[state.choropleth.field]];
							return {
								color: '#7a6a4f',
								fillColor: _colorFor(v, state.choropleth.min, state.choropleth.max),
								fillOpacity: 0.6,
							};
						};
					} else {
						cfg.style = { color: '#7a6a4f', fillColor: '#d9d0b8', fillOpacity: 0.6 };
					}
				} else if (role === 'places') {
					cfg.pointToLayer = (feature, latlng) =>
						L.circleMarker(latlng, { radius: 2, color: '#555', fillColor: '#555', fillOpacity: 1 });
					cfg.onEachFeature = (feature, layer) => {
						if (feature.properties && feature.properties.name) {
							layer.bindPopup('<b>' + feature.properties.name + '</b>');
						}
					};
				} else {
					Object.assign(cfg, styleFor(role));
				}
				const group = L.geoJSON(geojson, cfg);
				state.groups[role] = group;
				group.addTo(map);
			}
			return loaded;
		}

		function setChoropleth(field, valueByKey, opts2) {
			opts2 = opts2 || {};
			const values = Object.values(valueByKey || {}).filter(v => typeof v === 'number');
			const min = values.length ? Math.min(...values) : 0;
			const max = values.length ? Math.max(...values) : 1;
			state.choropleth = { field, valueByKey, min, max };
			return {
				min, max,
				legendHtml: opts2.legend !== false ? choroplethLegend(min, max) : null,
			};
		}

		function clearChoropleth() {
			state.choropleth = null;
			if (state.groups.countries) state.groups.countries.setStyle({
				color: '#7a6a4f', fillColor: '#d9d0b8', fillOpacity: 0.6,
			});
		}

		function onCountryClick(fn) {
			state.countryCb = fn;
		}

		/* Data-driven choropleth (Leaflet offline viewer): recolour the
		 * countries group from a server-side Siraj site-data aggregation. */
		async function setChoroplethFromSite(doctype, opts2) {
			opts2 = opts2 || {};
			const payload = await fetchSiteChoropleth(doctype, opts2);
			if (!payload || payload.empty || !payload.valueByKey) {
				return null;
			}
			const painted = setChoropleth(COUNTRY_JOIN_FIELD, payload.valueByKey, opts2);
			if (state.groups.countries) {
				state.groups.countries.setStyle(feature => {
					const code = feature.properties && (feature.properties.ADM0_A3 || feature.properties.ISO_A3);
					const value = payload.valueByKey[code];
					const t = (painted.max === painted.min) ? 0.5
						: (value - painted.min) / (painted.max - painted.min);
					const idx = Math.min(CHOROPLETH_COLORS.length - 1,
						Math.max(0, Math.round(t * (CHOROPLETH_COLORS.length - 1))));
					return { color: '#7a6a4f', fillColor: CHOROPLETH_COLORS[idx], fillOpacity: 0.6 };
				});
			}
			return { payload, painted };
		}

		function countryProfile(feature) {
			if (!feature || !feature.properties) return Promise.resolve(null);
			const code = feature.properties.ADM0_A3 || feature.properties.ISO_A3;
			if (!code) return Promise.resolve(null);
			return fetchCountryProfile({ code });
		}

		async function setScale(scale) {
			return _build(scale || state.scale);
		}

		function setVisible(v) {
			state.visible = !!v;
			Object.values(state.groups).forEach(g => {
				if (state.visible) g.addTo(map); else if (map.hasLayer(g)) map.removeLayer(g);
			});
		}

		function currentScale() { return state.scale; }

		function destroy() { _clearGroups(); }

			return _fetchManifest().then(m => {
				const initialZoom = opts.zoom != null ? opts.zoom :
					(map.getZoom ? map.getZoom() : 4);
				return _build(_selectScale(initialZoom, m.available, m.tiers));
			}).then(loaded => ({
				engine: 'leaflet',
				setScale, setVisible, currentScale,
				setChoropleth, clearChoropleth,
				setChoroplethFromSite, countryProfile,
				onCountryClick, destroy,
				_loaded: loaded,
			}));
	}

	/* ---------------- Public API ---------------- */

	window.SirajNeVector = {
		CHOROPLETH_COLORS,
		CHOROPLETH_JOIN_FIELD: COUNTRY_JOIN_FIELD,
		choroplethLegend,
		/** Fetch normalized country facts (capital, pop, GDP, area, Arabic name). */
		fetchCountryProfile,
		/** Fetch a data-driven Siraj site-data choropleth payload. */
		fetchSiteChoropleth,
		/** Attach a Natural Earth Vector basemap controller to a map instance. */
		attach(map, opts) {
			opts = opts || {};
			const engine = opts.engine ||
				(map && map.getStyle ? 'maplibre' : 'leaflet');
			if (engine === 'maplibre') return attachMapLibre(map, opts);
			if (engine === 'leaflet') return attachLeaflet(map, opts);
			return Promise.reject(new Error('SirajNeVector: unknown engine ' + engine));
		},
	};
})();
