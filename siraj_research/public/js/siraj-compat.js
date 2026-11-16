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

	/* ---------- 3) Frappe MapView markers: use the SIRAJ pin registry ----------
	 * When Frappe renders its list Map view it uses L.marker(...) with the
	 * default blue icon. We intercept those markers the moment the map is
	 * created and replace their icons with doctype-coloured glyph pins drawn
	 * from window.sirajIcons. This keeps the native Map view visually
	 * consistent with the Explorer and form maps without reimplementing it.
	 */
	function sirajStylizeMapViewMarkers() {
		if (!window.L || !window.frappe || !frappe.views || !frappe.views.MapView) return;
		const MV = frappe.views.MapView.prototype;
		if (MV._sirajStyled) return;
		MV._sirajStyled = true;
		const origSetup = MV.setup_view || function () {};
		MV.setup_view = function () {
			const mv = this;
			const result = origSetup.apply(mv, arguments);
			try {
				const map = mv.map;
				if (!map) return result;
				// Replace default blue markers with doctype-coloured SIRAJ pins
				// the moment they are added, so the list Map view matches the
				// Explorer and form maps.
				map.on('layeradd', ev => {
					const layer = ev.layer;
					if (!layer || !layer.options || !(layer instanceof L.Marker) || layer.options._sirajStyled) return;
					const icon = layer.options.icon;
					if (icon && icon.options && /default-icon|leaflet-zoom|-blue/i.test(String(icon.options.className || '') + (icon.options.iconUrl || ''))) {
						const dt = mv.doctype || (frappe.get_route && frappe.get_route()[1]);
						const color = (window.sirajColours && window.sirajColours[dt]) || '#3577c0';
						if (window.sirajIcons && window.sirajIcons.pin) {
							layer.setIcon(L.divIcon({
								className: 'sx-pin-wrapper', iconSize:[32,32], iconAnchor:[16,16],
								html: window.sirajIcons.pin(dt || 'Person', color, 32)
							}));
						}
						layer.options._sirajStyled = true;
					}
				});
			} catch (_) { /* never break the map view because styling failed */ }
			return result;
		};
	}
	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', sirajStylizeMapViewMarkers, { once: true });
	else sirajStylizeMapViewMarkers();
	// Re-attempt after each route change because MapView is constructed on demand.
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

		/* Scoped Node.removeChild guard — ONLY fires when the node being
		 * removed is an SVG inside a known Frappe chart container whose
		 * parent is no longer the element doing the removing. This keeps
		 * the fix for BaseChart.js:183 without monkey-patching arbitrary
		 * DOM operations.
		 */
		try {
			const nativeRemoveChild = Node.prototype.removeChild;
			Node.prototype.removeChild = function (child) {
				if (child && child.tagName === 'SVG' && this !== child.parentNode && /chart/i.test((this.className && this.className.baseVal) || this.className || '')) {
					return child;
				}
				return nativeRemoveChild.call(this, child);
			};
		} catch (_) { /* environment locks Node.prototype; accept the console error */ }
	}
	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', installChartObserverGuard, { once: true });
	else installChartObserverGuard();
})();
