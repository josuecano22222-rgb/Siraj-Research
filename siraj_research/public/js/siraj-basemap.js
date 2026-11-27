/* SIRAJ Leaflet basemap switcher — shared across Explorer and form coordinate maps.
 *
 * Provides SirajBasemap.attach(map, opts) which returns a small controller
 * that can swap between four basemaps:
 *   - standard: OpenStreetMap tiles (or whatever tile_cache returns as default)
 *   - satellite: Esri World Imagery
 *   - hybrid: Esri World Imagery + Esri World Reference Overlay (labels/borders)
 *   - offline: Natural Earth polygons (already in the map as offlineLayer)
 *   - nevector: full Natural Earth Vector basemap (cultural + physical,
 *     scale-tiered; built lazily by SirajNeVector)
 *
 * Persists the last choice per-browser so reloads keep the user's preference.
 * Includes a toolbar group builder (.toolbarGroup(toolbar)) that adds a
 * "Basemap" section with four toggle buttons (Standard/Satellite/Hybrid/Offline)
 * matching the user's spec.
 */
(() => {
	'use strict';

	const STORAGE_KEY = 'siraj.basemap.mode';
	const BASEMAPS = {
		standard: {
			label: () => __('Standard'),
			icon: 'basemap_standard',
			tooltip: () => __('Standard OpenStreetMap basemap'),
		},
		satellite: {
			label: () => __('Satellite'),
			icon: 'basemap_satellite',
			tooltip: () => __('Satellite imagery (Esri World Imagery)'),
			// Every raster request goes through the SIRAJ server proxy so the
			// tile is written to the shared on-disk cache on first view.
			tileUrl: '/api/method/siraj_research.tile_cache.tile?layer=aerial&z={z}&x={x}&y={y}',
			attribution: 'Tiles © Esri — Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
			maxZoom: 19,
		},
		hybrid: {
			label: () => __('Hybrid'),
			icon: 'basemap_hybrid',
			tooltip: () => __('Satellite imagery with labels and borders'),
			tileUrl: '/api/method/siraj_research.tile_cache.tile?layer=hybrid&z={z}&x={x}&y={y}',
			overlayUrl: '/api/method/siraj_research.tile_cache.tile?layer=hybrid_labels&z={z}&x={x}&y={y}',
			attribution: 'Imagery © Esri; labels © Esri, HERE, Garmin, OpenStreetMap contributors',
			maxZoom: 19,
		},
		offline: {
			label: () => __('Offline'),
			icon: 'basemap_offline',
			tooltip: () => __('Offline (Natural Earth, low detail)'),
		},
		nevector: {
			label: () => __('Natural Earth Vector'),
			icon: 'basemap_nevector',
			tooltip: () => __('Natural Earth Vector basemap (cultural + physical)'),
		},
	};

	function loadMode() {
		try { const v = localStorage.getItem(STORAGE_KEY); return (v && BASEMAPS[v]) ? v : 'standard'; }
		catch (_) { return 'standard'; }
	}
	function saveMode(mode) {
		try { localStorage.setItem(STORAGE_KEY, mode); } catch (_) {}
	}

	function attach(map, opts) {
		opts = opts || {};
		const state = {
			map,
			mode: loadMode(),
			// Layers injected by caller or created lazily.
			standardLayer: opts.standardLayer || null,  // server-cached tile layer (OSM by default)
			standardOverlay: opts.standardOverlay || null,
			satelliteLayer: null,
			hybridLayer: null,
			hybridOverlay: null,
			offlineLayer: opts.offlineLayer || null,    // Natural Earth GeoJSON
			nevectorCtrl: null,                          // SirajNeVector controller
			onChange: opts.onChange || (() => {}),
			_buttons: new Map(),
		};

		function _setVisible(which) {
			// Standard layer may already be on the map (added by caller). Remove all online layers first.
			[state.standardLayer, state.satelliteLayer, state.hybridLayer].forEach(layer => {
				if (layer && map.hasLayer(layer)) map.removeLayer(layer);
			});
			[state.standardOverlay, state.hybridOverlay].forEach(layer => {
				if (layer && map.hasLayer(layer)) map.removeLayer(layer);
			});
			if (state.offlineLayer && map.hasLayer(state.offlineLayer)) map.removeLayer(state.offlineLayer);
			// Hide the Natural Earth Vector basemap when switching to another mode.
			if (which !== 'nevector' && state.nevectorCtrl) {
				try { state.nevectorCtrl.setVisible(false); } catch (_) {}
			}

			if (which === 'standard') {
				if (state.standardLayer) state.standardLayer.addTo(map);
				if (state.standardOverlay) state.standardOverlay.addTo(map);
			} else if (which === 'satellite') {
				if (!state.satelliteLayer) {
					const cfg = BASEMAPS.satellite;
					state.satelliteLayer = L.tileLayer(cfg.tileUrl, {
						maxZoom: cfg.maxZoom, maxNativeZoom: cfg.maxZoom, attribution: cfg.attribution,
					});
				}
				state.satelliteLayer.addTo(map);
			} else if (which === 'hybrid') {
				if (!state.hybridLayer) {
					const cfg = BASEMAPS.hybrid;
					state.hybridLayer = L.tileLayer(cfg.tileUrl, {
						maxZoom: cfg.maxZoom, maxNativeZoom: cfg.maxZoom, attribution: cfg.attribution,
					});
					state.hybridOverlay = L.tileLayer(cfg.overlayUrl, {
						maxZoom: cfg.maxZoom, maxNativeZoom: cfg.maxZoom, pane: 'overlayPane',
					});
				}
				state.hybridLayer.addTo(map);
				if (state.hybridOverlay) state.hybridOverlay.addTo(map);
			} else if (which === 'offline') {
				if (state.offlineLayer) state.offlineLayer.addTo(map);
			} else if (which === 'nevector') {
				// Build the vector basemap lazily; reuse the controller afterwards.
				if (!state.nevectorCtrl && window.SirajNeVector) {
					const engine = opts.engine || (map.getStyle ? 'maplibre' : 'leaflet');
					window.SirajNeVector.attach(map, { engine }).then(ctrl => {
						state.nevectorCtrl = ctrl;
						ctrl.setVisible(true);
					}).catch(e => console.warn('[SirajBasemap] nevector build failed:', e));
				} else if (state.nevectorCtrl) {
					state.nevectorCtrl.setVisible(true);
				}
			}
		}

		function _updateButtons(active) {
			for (const [mode, btn] of state._buttons) {
				if (!btn || !btn.classList) continue;
				btn.classList.toggle('is-active', mode === active);
				btn.setAttribute('aria-pressed', mode === active ? 'true' : 'false');
			}
		}

		const ctrl = {
			get mode() { return state.mode; },
			set(mode) {
				if (!BASEMAPS[mode]) return;
				state.mode = mode;
				saveMode(mode);
				_setVisible(mode);
				_updateButtons(mode);
				try { state.onChange(mode, BASEMAPS[mode]); } catch (_) {}
			},
			/** Register the standard (default/cached) tile layer after it's added to the map. */
			setStandardLayer(layer, overlay) {
				state.standardLayer = layer || null;
				state.standardOverlay = overlay || null;
				// Apply currently selected mode now that the standard layer is known.
				_setVisible(state.mode);
				_updateButtons(state.mode);
			},
			/** Register the offline/Natural Earth layer. */
			setOfflineLayer(layer) { state.offlineLayer = layer; },
			/** Register a pre-built SirajNeVector controller (optional). */
			setNeVectorCtrl(ctrl) { state.nevectorCtrl = ctrl || null; },
		/** Append a Basemap group to a sirajToolbar instance.
		 * toolbar.group(label) returns a chain API; toolbar._buttons stores the
		 * DOM button keyed by spec.key after add() runs, so we fetch the button
		 * from there (add() returns the group, not the button element). */
			toolbarGroup(toolbar) {
				const g = toolbar.group(__('Basemap'));
				Object.keys(BASEMAPS).forEach(mode => {
					const spec = BASEMAPS[mode];
					const key = 'basemap_' + mode;
					g.add({
						icon: spec.icon,
						label: spec.label(),
						key,
						tooltip: spec.tooltip(),
						mode: 'toggle',
						active: (mode === state.mode),
						action: () => ctrl.set(mode),
					});
					const btn = toolbar._buttons && toolbar._buttons.get(key);
					if (btn) state._buttons.set(mode, btn);
				});
				_updateButtons(state.mode);
			},
		};

		// If standard layer is provided up-front, render initial mode.
		if (state.standardLayer) _setVisible(state.mode);
		return ctrl;
	}

	window.SirajBasemap = { attach, BASEMAPS };
})();
