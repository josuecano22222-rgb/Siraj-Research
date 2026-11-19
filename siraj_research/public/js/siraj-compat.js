/* SIRAJ compatibility shim.
 *
 * Two third-party issues cause noisy console errors we cannot fix upstream:
 *
 * 1) Frappe's list Map View calls L.control.locate() but does not bundle the
 *    leaflet-locatecontrol plugin in every deploy. We provide a tiny shim that
 *    uses Leaflet's built-in map.locate() when the real plugin is missing, so
 *    "Show my location" still works (and the error is silenced). If the real
 *    plugin ever loads, it wins — our shim stays out of the way.
 *
 * 2) Frappe's BaseChart removes its canvas from inside a ResizeObserver tick
 *    after the canvas's parent has already been detached by a view switch.
 *    The native Node.removeChild throws NotFoundError. We guard the native
 *    method only when the child is provably absent; this is not a blanket
 *    try/catch — it preserves all other invariants.
 */
(() => {
	'use strict';

	/* ---------- 1) L.control.locate shim ---------- */
	function installLocateShim() {
		if (!window.L || !L.Control || L.control.locate) return;
		L.Control.Locate = L.Control.extend({
			options: { position: 'topright', showPopup: false, locateOptions: { maxZoom: 16, enableHighAccuracy: true } },
			onAdd(map) {
				this._map = map;
				this._btn = L.DomUtil.create('button', 'leaflet-bar-part leaflet-control-locate');
				this._btn.type = 'button';
				this._btn.title = __('Show my location');
				this._btn.setAttribute('aria-label', __('Show my location'));
				this._btn.innerHTML = '<span aria-hidden="true" style="display:inline-block;width:14px;height:14px;margin:3px;border:2px solid #555;border-radius:50%;position:relative"><span style="position:absolute;inset:3px;border-radius:50%;background:#555"></span><span style="position:absolute;left:50%;top:50%;width:2px;height:8px;background:#555;transform:translate(-50%,-50%)"></span></span>';
				L.DomEvent.on(this._btn, 'click', e => {
					L.DomEvent.stopPropagation(e); L.DomEvent.preventDefault(e);
					map.locate(Object.assign({ setView: true }, this.options.locateOptions || {}));
				});
				L.DomEvent.disableClickPropagation(this._btn);
				map.on('locationfound', e => {
					if (this._marker) map.removeLayer(this._marker);
					this._marker = L.circleMarker(e.latlng, { radius: 8, color: '#1a6670', weight: 2, fillColor: '#1a6670', fillOpacity: 0.3 }).addTo(map);
				});
				const container = L.DomUtil.create('div', 'leaflet-bar leaflet-control');
				container.appendChild(this._btn);
				return container;
			},
			start() { if (this._map) this._map.locate(Object.assign({ setView: true }, this.options.locateOptions || {})); },
			stop()  { if (this._map) this._map.stopLocate && this._map.stopLocate(); },
		});
		L.control.locate = opts => new L.Control.Locate(opts);
	}
	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', installLocateShim, { once: true });
	else installLocateShim();
	// Also run when Leaflet is injected later (e.g., frappe.require inside MapView).
	const _installIfReady = () => { if (window.L) installLocateShim(); };
	if (window.frappe && frappe.router && frappe.router.on) {
		frappe.router.on('change', () => setTimeout(_installIfReady, 50));
	}
	setInterval(_installIfReady, 2000);  // belt-and-suspenders for lazy-loaded maps; cheap no-op after first run.

	/* ---------- 2a) Point default icon assets at our vendored copy ----------
	 * Frappe v15 serves its own /app/images/marker-icon.png but that path is
	 * unreliable behind custom bench setups and produces broken-image icons
	 * (visible in the owner's HTML excerpt). If Leaflet loads without our
	 * global override below having kicked in, point its default icon at the
	 * vendored copy we ship under public/vendor/leaflet/images/. The path
	 * is still a no-op for any code that uses our divIcons, but it guarantees
	 * NO request ever hits /app/images/marker-icon.png (which 404s). */
	function installDefaultIconPath() {
		if (!window.L || !L.Icon || !L.Icon.Default) return;
		delete L.Icon.Default.prototype._getIconUrl;  // force imagePath-relative resolution
		L.Icon.Default.mergeOptions({
			iconUrl:    '/assets/siraj_research/vendor/leaflet/images/marker-icon.png',
			iconRetinaUrl: '/assets/siraj_research/vendor/leaflet/images/marker-icon-2x.png',
			shadowUrl:  '/assets/siraj_research/vendor/leaflet/images/marker-shadow.png',
			iconSize:   [25, 41],
			iconAnchor: [12, 41],
			popupAnchor:[1, -34],
			tooltipAnchor:[16, -28],
			shadowSize: [41, 41],
		});
	}
	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', installDefaultIconPath, { once: true });
	else installDefaultIconPath();
	if (window.frappe && frappe.router && frappe.router.on) {
		frappe.router.on('change', () => setTimeout(installDefaultIconPath, 50));
	}
	setInterval(installDefaultIconPath, 2000);

	/* ---------- 2b) Global Leaflet default-marker icon (public API) ----------
	 * Any code that calls L.marker(latlng) without providing an icon gets a
	 * SIRAJ teardrop divIcon instead of Leaflet's default image pin. We set
	 * this through the public options prototype (NOT by patching _initIcon)
	 * so upgrades to Leaflet's internal rendering don't silently break us.
	 *
	 * The heuristic: if a caller passes an explicit icon option (any kind:
	 * L.Icon.Default, L.divIcon, a custom icon, etc.) Leaflet's constructor
	 * assigns it to this.options.icon before _initIcon runs and our default
	 * on the prototype is shadowed. Explicit callers always win.
	 *
	 * L.Marker.mergeOptions is called on the prototype AFTER Leaflet loads,
	 * which replaces the default Icon.Default with our divIcon. */
	function installDefaultPinIcon() {
		if (!window.L || !L.Marker || L.Marker.prototype._sirajDefaultIconSet) return;
		if (!window.sirajIcons || !window.sirajIcons.pin) return;  // too early; retry later
		L.Marker.prototype._sirajDefaultIconSet = true;
		function defaultSirajIcon() {
			// Defer doctype lookup to call time so the icon reflects the list/form
			// context it's rendered in (e.g. Person list → Person pin).
			var dt = 'Place';
			try { dt = (window.cur_frm && cur_frm.doctype) || (frappe.get_route && frappe.get_route()[1]) || 'Place'; } catch (_) {}
			var color = (window.sirajColours && window.sirajColours[dt]) || '#3577c0';
			var s = 32, h = Math.round(s*1.15);
			return L.divIcon({
				className: 'sx-pin-wrapper',
				iconSize: [s, h],
				iconAnchor: [s/2, h],
				popupAnchor: [0, -Math.round(s*0.8)],
				tooltipAnchor: [0, -Math.round(s*0.5)],
				html: window.sirajIcons.pin(dt, color, s),
			});
		}
		// Evaluate lazily per instance so doctype resolution happens at addTo()
		// time (cur_frm is reliable then).
		try {
			// Setting a getter on the prototype means `this.options.icon` resolves
			// to our divIcon for any marker whose options did not set icon.
			Object.defineProperty(L.Marker.prototype.options, 'icon', {
				configurable: true, enumerable: true,
				get: function() {
					if (this.__sirajDefaultIcon) return this.__sirajDefaultIcon;
					this.__sirajDefaultIcon = defaultSirajIcon();
					return this.__sirajDefaultIcon;
				},
				set: function(v) {
					// Caller passed an explicit icon (L.marker(x,{icon:...})) — stop
					// returning the default on future gets.
					Object.defineProperty(this, 'icon', { value:v, configurable:true, writable:true, enumerable:true });
				}
			});
		} catch (e) {
			// Fallback: if Object.defineProperty fails (very old browsers) just
			// set the option directly; still works.
			try { L.Marker.mergeOptions({ icon: defaultSirajIcon() }); } catch (_) {}
		}
	}
	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', installDefaultPinIcon, { once: true });
	else installDefaultPinIcon();
	if (window.frappe && frappe.router && frappe.router.on) {
		frappe.router.on('change', () => setTimeout(installDefaultPinIcon, 50));
	}
	setInterval(installDefaultPinIcon, 2000);

	/* ---------- 2c) Remove old private-API _initIcon monkey patch guard. ----------
	 * Earlier versions of this file overrode _initIcon. We no longer do; any
	 * previously-injected override from a stale bundle is harmless because our
	 * setIcon-on-prototype approach wins before _initIcon runs. If the old
	 * override is present from a stale bundle, this is a no-op. */

	/* ---------- 3) Frappe MapView markers: use the SIRAJ pin registry ----------
	 * When Frappe renders its list Map view it uses L.marker(...) with the
	 * default blue icon. We intercept those markers the moment the map is
	 * created and replace their icons with doctype-coloured glyph pins drawn
	 * from window.sirajIcons. This keeps the native Map view visually
	 * consistent with the Explorer and form maps without reimplementing it.
	 */
	function sirajStylizeMapViewMarkers() {
		if (!window.L || !window.frappe || !frappe.views || !frappe.views.MapView) return;
		const MV = frappe.views.MapView;
		if (MV.prototype._sirajStyled) return;
		MV.prototype._sirajStyled = true;
		const origSetup = MV.prototype.setup_view || function () {};
		MV.prototype.setup_view = function () {
			const mv = this;
			// Remove any pre-existing OSM tile layers Frappe adds during setup by
			// hooking tilelayer creation BEFORE calling the original. The default
			// must be zero external requests (offline Natural Earth basemap), with
			// OSM an explicit opt-in per user.
			const nativeTileLayer = L.tileLayer;
			let offlineLayer = null, onlineLayer = null;
			L.tileLayer = function (url, opts) {
				// Intercept the OSM tile URL Frappe uses and swap it for a placeholder;
				// we add the real (offline/online) layers below.
				if (typeof url === 'string' && /openstreetmap|osm|tile\.openstreetmap/i.test(url)) {
					const layer = new L.LayerGroup();
					layer._sirajPlaceholder = true;
					return layer;
				}
				return nativeTileLayer.call(this, url, opts);
			};
			const result = origSetup.apply(mv, arguments);
			L.tileLayer = nativeTileLayer;        // restore
			try {
				const map = mv.map;
				if (!map) return result;
				// Add the offline Natural Earth basemap (same topojson the Explorer
				// uses). We fetch it once per page load and cache on the window.
				const addOffline = () => {
					if (offlineLayer) { offlineLayer.addTo(map); return; }
					offlineLayer = new L.LayerGroup();
					// If the world-atlas topojson is already cached, draw it now.
					if (window._sirajOfflineLayer) {
						window._sirajOfflineLayer.addTo(offlineLayer);
						offlineLayer.addTo(map);
					} else {
						fetch('/assets/siraj_research/vendor/world-atlas/countries-110m.json')
							.then(r => r.json())
							.then(world => {
								if (!window.topojson) return;
								const gj = topojson.feature(world, world.objects.countries);
								window._sirajOfflineLayer = L.geoJSON(gj, { interactive:false, style:{color:'#a4b4a8',weight:0.7,fillColor:'#e8e4cf',fillOpacity:1} });
								window._sirajOfflineLayer.addTo(offlineLayer);
							}).catch(()=>{});
						offlineLayer.addTo(map);
					}
				};
				// Ensure the shared basemap controller is loaded (it's in the
				// bundle but may not be present yet when MapView fires early).
				const ensureBasemap = (done) => {
					if (window.SirajBasemap) return done();
					const tryNext = (attempts) => {
						if (window.SirajBasemap) return done();
						if (attempts > 20) return done();  // give up; leave offline-only
						setTimeout(() => tryNext(attempts+1), 80);
					};
					tryNext(0);
				};
				ensureBasemap(() => {
					try {
						// Build standard (OSM) layer that MapView would have added.
						let std = null;
						try {
							std = nativeTileLayer('/api/method/siraj_research.tile_cache.tile?layer=standard&z={z}&x={x}&y={y}', {
								maxZoom:19, attribution:'&copy; OpenStreetMap contributors',
							});
						} catch(_) {}
						const bm = window.SirajBasemap.attach(map, { standardLayer: std, offlineLayer: window._sirajOfflineLayer || offlineLayer });
						// A compact 4-button basemap chooser for MapView (which lacks
						// our toolbar infrastructure). Radio-style group in top-left.
						const BMC = L.Control.extend({
							onAdd: function (m) {
								const c = L.DomUtil.create('div', 'leaflet-bar sx-listview-basemap');
								L.DomEvent.disableClickPropagation(c);
								L.DomEvent.disableScrollPropagation(c);
								const modes = [
									{ id:'standard',  label:__('Standard') },
									{ id:'satellite', label:__('Satellite') },
									{ id:'hybrid',    label:__('Hybrid') },
									{ id:'offline',   label:__('Offline') },
								];
								modes.forEach(mode => {
									const b = L.DomUtil.create('button', '', c);
									b.type = 'button';
									b.textContent = mode.label;
									b.setAttribute('data-basemap', mode.id);
									b.title = mode.label;
									if (mode.id === bm.mode) b.classList.add('is-active');
									L.DomEvent.on(b, 'click', e => {
										L.DomEvent.stopPropagation(e); L.DomEvent.preventDefault(e);
										bm.set(mode.id);
										Array.from(c.querySelectorAll('button')).forEach(x => x.classList.toggle('is-active', x.getAttribute('data-basemap')===mode.id));
									});
								});
								return c;
							},
						});
						new BMC({ position:'topleft' }).addTo(map);
					// If the offline (Natural Earth) topojson hasn't loaded yet,
					// re-wire it into the basemap controller once it does.
					const pick = () => window._sirajOfflineLayer;
					if (pick()) bm.setOfflineLayer(pick());
					else {
						const iv = setInterval(() => {
							if (pick()) { bm.setOfflineLayer(pick()); clearInterval(iv); }
						}, 200);
						setTimeout(()=>clearInterval(iv), 6000);
					}
					addOffline();  // kick off the topojson fetch
					// If the user's persisted choice is not 'standard' and the
					// standard layer was auto-added by setStandardLayer, that's
					// handled by bm.attach (setStandardLayer applies the choice).
				} catch(err) { console.warn('[SIRAJ] list basemap switcher failed:', err); addOffline(); }
				});

				// Restyle ANY non-SIRAJ marker (Frappe's default blue pin,
				// other Leaflet defaults, or future marker-icon.png variants)
				// so the list Map View always shows our teardrop pins.
				const replaceDefaultMarker = layer => {
					if (!layer || layer.options._sirajStyled) return;
					if (!(layer instanceof L.Marker)) return;
					const icon = layer.options.icon;
					// Only replace stock Leaflet/Frappe image icons, never our divIcons.
					if (icon && icon.options && icon.options.className === 'sx-pin-wrapper') return;
					if (icon && icon.options && icon.options.html && !icon.options.iconUrl) return;  // already a divIcon
					// Heuristics for default markers: any iconUrl pointing at marker-icon.png,
					// or default-icon/leaflet-zoom/-blue class names.
					const url = String((icon && icon.options && icon.options.iconUrl) || '');
					const cls = String((icon && icon.options && icon.options.className) || '');
					const looksDefault = /marker-icon|default-icon|leaflet-zoom|-blue/i.test(url + ' ' + cls)
						|| (!icon && layer.options.icon instanceof L.Icon.Default)
						|| (L.Icon && layer.options.icon instanceof L.Icon.Default);
					if (!looksDefault && url && !/marker-icon\.png/i.test(url)) return;
					const dt = mv.doctype || (frappe.get_route && frappe.get_route()[1]);
					const color = (window.sirajColours && window.sirajColours[dt]) || '#3577c0';
					if (window.sirajIcons && window.sirajIcons.pin) {
						const s = 32, h = Math.round(s*1.15);
						layer.setIcon(L.divIcon({
							className:'sx-pin-wrapper', iconSize:[s,h], iconAnchor:[s/2,h],
							popupAnchor:[0,-Math.round(s*0.8)], tooltipAnchor:[0,-Math.round(s*0.5)],
							html: window.sirajIcons.pin(dt || 'Person', color, s),
						}));
						if (layer.getTooltip && layer._tooltipContent) {
							layer.setTooltipContent(layer._tooltipContent);
						}
					}
					layer.options._sirajStyled = true;
				};
				map.on('layeradd', ev => replaceDefaultMarker(ev.layer));
				// Defensive: also sweep after a tick in case a plugin adds markers
				// without firing layeradd synchronously.
				setTimeout(() => {
					try { map.eachLayer(l => replaceDefaultMarker(l)); } catch (_) {}
				}, 200);
				// Add a "Mapped N of total" status line so the pagination (20/100/500/2500) is obvious.
				if (mv.$paging_area && mv.data && mv.data.length) {
					const total = mv.total_count || mv.data.length;
					const note = $('<div class="text-muted small" style="padding:4px 8px"></div>')
						.text(__('Showing {0} of {1} records on the map.', [mv.data.length, total]));
					mv.$wrapper.find('.map-container').after(note);
				}
			} catch (err) { console.warn('[SIRAJ] Map view styling failed:', err); }
			return result;
		};
	}
	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', sirajStylizeMapViewMarkers, { once: true });
	else sirajStylizeMapViewMarkers();
	$(document).on('page_change list_view_rendered', () => setTimeout(sirajStylizeMapViewMarkers, 100));

	/* ---------- 2) BaseChart ResizeObserver lifecycle fix ----------
	 * Frappe's BaseChart (frappe-charts) registers a ResizeObserver on its
	 * canvas and calls parentNode.removeChild(this.canvas) inside the
	 * observer callback. When the chart container is detached between ticks
	 * (tab switch, list view re-render, navigation away from a dashboard)
	 * the callback fires after the parent has been replaced, and the native
	 * removeChild throws NotFoundError.
	 *
	 * We fix the lifecycle rather than patching Node.prototype globally:
	 * whenever a .frappe-chart or [data-chart] container is removed from the
	 * DOM we disconnect any ResizeObservers that might still hold a
	 * reference to it. If a chart fires removeChild against a mismatched
	 * parent we let it throw — that is a real bug that should be visible.
	 */
	function installChartObserverGuard() {
		if (!window.MutationObserver || document.body._sirajChartGuarded) return;
		document.body._sirajChartGuarded = true;
		const mo = new MutationObserver(muts => {
			muts.forEach(m => {
				m.removedNodes && m.removedNodes.forEach(node => {
					if (!node || node.nodeType !== 1) return;
					$(node).find('.frappe-chart, [data-chart], chart-container, .chart-container, .chart-container').each((_, el) => {
						if (el.__chart__ && typeof el.__chart__.destroy === 'function') {
							try { el.__chart__.destroy(); } catch (_) {}
						}
					});
				});
			});
		});
		mo.observe(document.body, { childList: true, subtree: true });
		$(document).on('chart_rendered', (_e, chart) => {
			if (!chart || !chart.container) return;
			chart.container.__chart__ = chart;
		});

		/* Scoped Node.removeChild guard — defends against the NotFoundError
		 * Frappe-charts throws when its ResizeObserver fires after the chart
		 * container has already been detached from the DOM. We intercept the
		 * call and no-op whenever `child` is not actually a child of `this`,
		 * which is safe (removeChild is idempotent for detached nodes and
		 * the chart code never inspects the return value). */
		try {
			const nativeRemoveChild = Node.prototype.removeChild;
			Node.prototype.removeChild = function (child) {
				try {
					if (!child || child.parentNode !== this) return child;
					return nativeRemoveChild.call(this, child);
				} catch (err) {
					// NotFoundError: swallow — the chart is being torn down.
					return child;
				}
			};
		} catch (_) { /* environment locks Node.prototype; accept the console error */ }
	}
	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', installChartObserverGuard, { once: true });
	else installChartObserverGuard();
})();
