/* SIRAJ map kit — shared geometry, measurement, picking and relationship
 * overlays used by both the Explorer geographic map and the per-DocType form
 * coordinate editor. Pure enough to unit-test; Leaflet-aware where required.
 *
 * Exports:
 *   window.SirajMapKit = {
 *     Geodesic: { distance, area, bearing, destination, fmtLength, fmtArea },
 *     MeasureTool: state-machine constructor for distance/area/radius/bearing,
 *     RelLayer:    relationship overlay layer with ego-highlight + styling,
 *     PickTool:    "click-to-link-entity" tool,
 *     TOOL_SPEC:   declarative registry of map-tools vs app-functions,
 *   }
 */
(() => {
	'use strict';

	/* ---------- Geodesic helpers (WGS-84, mean radius) ---------- */
	const R = 6371008.8; // metres, IUGG mean Earth radius
	const toRad = d => d * Math.PI / 180;
	const toDeg = r => r * 180 / Math.PI;

	function distance(a, b) {
		// Haversine distance, metres.
		const φ1 = toRad(a.lat), φ2 = toRad(b.lat), Δφ = toRad(b.lat - a.lat), Δλ = toRad(b.lng - a.lng);
		const s = Math.sin(Δφ/2) ** 2 + Math.cos(φ1) * Math.cos(φ2) * Math.sin(Δλ/2) ** 2;
		return 2 * R * Math.asin(Math.min(1, Math.sqrt(s)));
	}
	function bearing(a, b) {
		// Initial bearing, degrees 0..360 (clockwise from north).
		const φ1 = toRad(a.lat), φ2 = toRad(b.lat), Δλ = toRad(b.lng - a.lng);
		const y = Math.sin(Δλ) * Math.cos(φ2);
		const x = Math.cos(φ1)*Math.sin(φ2) - Math.sin(φ1)*Math.cos(φ2)*Math.cos(Δλ);
		return (toDeg(Math.atan2(y, x)) + 360) % 360;
	}
	function destination(from, brngDeg, distM) {
		// Destination point given start, bearing (deg) and distance (m).
		const φ1 = toRad(from.lat), λ1 = toRad(from.lng), θ = toRad(brngDeg), δ = distM / R;
		const φ2 = Math.asin(Math.sin(φ1)*Math.cos(δ) + Math.cos(φ1)*Math.sin(δ)*Math.cos(θ));
		const λ2 = λ1 + Math.atan2(Math.sin(θ)*Math.sin(δ)*Math.cos(φ1), Math.cos(δ) - Math.sin(φ1)*Math.sin(φ2));
		return { lat: toDeg(φ2), lng: ((toDeg(λ2) + 540) % 360) - 180 };
	}
	function ringArea(points) {
		// Spherical excess (Tobler/Chamberlain & Dickinson), m². Clamped to the smaller cap.
		if (points.length < 3) return 0;
		let sum = 0;
		for (let i = 0; i < points.length; i++) {
			const p = points[i], n = points[(i + 1) % points.length];
			let dλ = toRad(n.lng - p.lng);
			if (dλ > Math.PI) dλ -= 2 * Math.PI;
			if (dλ < -Math.PI) dλ += 2 * Math.PI;
			sum += dλ * (2 + Math.sin(toRad(p.lat)) + Math.sin(toRad(n.lat)));
		}
		const raw = Math.abs(sum * R * R / 2);
		const sphere = 4 * Math.PI * R * R;
		return Math.min(raw, sphere - raw);
	}
	function compass(deg) {
		const names = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW'];
		return names[Math.round(((deg % 360) / 22.5)) % 16];
	}
	function fmtLength(m, unit) {
		if (!Number.isFinite(m)) return '';
		switch (unit) {
			case 'mi':  return (m / 1609.344).toFixed(m > 1609 ? 2 : 3) + ' mi';
			case 'nm':  return (m / 1852).toFixed(m > 1852 ? 2 : 3) + ' NM';
			default:    return m >= 1000 ? (m/1000).toFixed(2) + ' km' : Math.round(m) + ' m';
		}
	}
	function fmtArea(m2, unit) {
		if (!Number.isFinite(m2)) return '';
		switch (unit) {
			case 'mi²': return (m2 / 2589988.11).toFixed(2) + ' mi²';
			case 'ha':  return (m2 / 10000).toFixed(2) + ' ha';
			default:    return m2 >= 1e6 ? (m2/1e6).toFixed(2) + ' km²' : Math.round(m2) + ' m²';
		}
	}

	/* ---------- Measurement state machine ----------
	 * States: idle → armed (tool selected, 0 clicks) → drawing (≥1 click) → complete
	 * Interaction model: selecting the tool arms it; the FIRST click begins drawing
	 * with a live preview that follows the cursor; subsequent clicks add vertices;
	 * double-click or Enter completes; Esc cancels to idle. For distance, the 2nd
	 * click immediately reports the segment and the chain continues (no "stop"
	 * button required), and the running total accumulates.
	 */
	class MeasureTool {
		constructor(map, opts = {}) {
			this.map = map;
			this.onStatus = opts.onStatus || (() => {});
			this.onPick = opts.onPick || null;     // used by radius/pick tools too
			this.unit = opts.unit || 'km';
			this.layer = L.layerGroup().addTo(map);
			this.preview = null;
			this.labels = [];
			this.vertices = [];
			this.mode = null;         // 'distance' | 'area' | 'radius' | 'bearing' | 'pick' | null
			this.state = 'idle';
			this._onClick = this._onClick.bind(this);
			this._onMove  = this._onMove.bind(this);
			this._onDbl   = this._onDbl.bind(this);
			this._onKey   = this._onKey.bind(this);
			this._cursor  = null;
		}
		_unitLen() { return this.unit === 'mi' ? 'mi' : this.unit === 'nm' ? 'nm' : (this.totalM() >= 1000 ? 'km' : 'm'); }
		totalM() {
			if (this.mode === 'distance') {
				let t = 0; for (let i=1; i<this.vertices.length; i++) t += distance(this.vertices[i-1], this.vertices[i]); return t;
			}
			if (this.mode === 'area') return Math.sqrt(ringArea(this.vertices));
			if (this.mode === 'radius' && this.vertices.length === 2) return distance(this.vertices[0], this.vertices[1]);
			return 0;
		}
		activate(mode) {
			this.deactivate();
			this.mode = mode; this.state = 'armed';
			this.map.getContainer().style.cursor = 'crosshair';
			this.map.on('click', this._onClick);
			this.map.on('mousemove', this._onMove);
			this.map.on('dblclick', this._onDbl);
			L.DomEvent.on(document, 'keydown', this._onKey);
			const tips = {
				distance: __('Click two points to measure; click more to chain. Double-click or Esc to finish.'),
				area:     __('Click to place vertices; the polygon follows your cursor. Double-click, Enter or click the start point to close.'),
				radius:   __('Click once for the centre, then again to set the radius.'),
				bearing:  __('Click two points to read bearing and distance.'),
				pick:     __('Click a point to link it to a record.'),
			};
			this.onStatus(tips[mode] || '', false, mode);
		}
		deactivate() {
			this.map.off('click', this._onClick);
			this.map.off('mousemove', this._onMove);
			this.map.off('dblclick', this._onDbl);
			L.DomEvent.off(document, 'keydown', this._onKey);
			this.map.getContainer().style.cursor = '';
			this._clearPreview();
			this.layer.clearLayers();
			this.labels = []; this.vertices = [];
			this.mode = null; this.state = 'idle';
			this.onStatus('', false, null);
		}
		isActive() { return this.state !== 'idle'; }
		clear() { this._clearPreview(); this.layer.clearLayers(); this.labels = []; this.vertices = []; if (this.mode) this.state = 'armed'; this.onStatus('', false, this.mode); }
		_onKey(e) {
			if (e.key === 'Escape') { this.deactivate(); return; }
			if (e.key === 'Enter' && this.state === 'drawing' && this.vertices.length >= (this.mode === 'distance' ? 2 : this.mode === 'area' ? 3 : 2)) {
				this._finish();
			}
		}
		_onDbl(e) {
			L.DomEvent.stopPropagation(e);
			if (this.state === 'drawing') this._finish();
		}
		_clearPreview() { if (this.preview) { this.map.removeLayer(this.preview); this.preview = null; } }
		_vertexIcon() {
			return L.divIcon({ className: 'siraj-vertex', iconSize: [10,10], iconAnchor:[5,5], html:'<span></span>' });
		}
		_labelAt(text, latlng, cls) {
			const icon = L.divIcon({ className: 'siraj-measure-label ' + (cls||''), iconSize:null, iconAnchor:[-8,14], html:'<span>' + text.replace(/</g,'&lt;') + '</span>' });
			const m = L.marker(latlng, { icon, interactive: false, keyboard: false });
			this.layer.addLayer(m);
			this.labels.push(m);
			return m;
		}
		_redraw(cursor) {
			this._clearPreview();
			if (!this.vertices.length) return;
			const pts = this.vertices.slice();
			if (cursor) pts.push(cursor);
			if (this.mode === 'distance') {
				if (pts.length >= 2) {
					const line = L.polyline(pts, { color:'#1a6670', weight:3, opacity:0.9, dashArray: cursor ? '6 5' : null, interactive:false });
					this.preview = line.addTo(this.map);
					if (!cursor) {
						let total = 0;
						for (let i = 1; i < pts.length; i++) {
							const seg = distance(pts[i-1], pts[i]); total += seg;
							this._labelAt(fmtLength(seg, this._unitLen()), L.latLngBounds([pts[i-1], pts[i]]).getCenter());
						}
						if (pts.length > 2) this._labelAt(__('Total: {0}', [fmtLength(total, this._unitLen())]), pts[pts.length-1], 'is-total');
					}
				}
			} else if (this.mode === 'area') {
				if (pts.length >= 2) {
					const poly = L.polygon(pts, { color:'#1a6670', weight:2.5, fillColor:'#1a6670', fillOpacity: cursor ? 0.08 : 0.18, dashArray: cursor ? '5 4' : null, interactive:false });
					this.preview = poly.addTo(this.map);
					if (!cursor && pts.length >= 3) {
						const a = ringArea(pts);
						this._labelAt(fmtArea(a, 'km²') + ' · ' + __('perimeter {0}', [fmtLength(pts.reduce((s,p,i)=>s+(i?distance(pts[i-1],p):0),0), 'km')]), pts[0], 'is-total');
					}
				}
			} else if (this.mode === 'radius') {
				if (pts.length >= 1) {
					const centre = pts[0], edge = pts[1] || cursor;
					if (edge) {
						const r = distance(centre, edge);
						const circ = L.circle(centre, { radius:r, color:'#1a6670', weight:2.5, fillColor:'#1a6670', fillOpacity: cursor ? 0.08 : 0.18, dashArray: cursor ? '5 4' : null, interactive:false });
						this.preview = circ.addTo(this.map);
						if (!cursor) this._labelAt(__('radius {0}', [fmtLength(r, this._unitLen())]) + ' · ' + __('area {0}', [fmtArea(Math.PI * r * r, 'km²')]), edge, 'is-total');
					}
				}
			} else if (this.mode === 'bearing' && pts.length >= 2) {
				const line = L.polyline(pts, { color:'#1a6670', weight:3, opacity:0.9, interactive:false });
				this.preview = line.addTo(this.map);
				const br = bearing(pts[0], pts[1]), d = distance(pts[0], pts[1]);
				this._labelAt(Math.round(br) + '° ' + compass(br) + ' · ' + fmtLength(d, this._unitLen()), L.latLngBounds(pts).getCenter(), 'is-total');
			}
			// Vertex handles (only the "pinned" ones, not the live cursor).
			this.layer.clearLayers(); this.labels = [];
			this.vertices.forEach((v, i) => L.marker(v, { icon: this._vertexIcon(), interactive: false, keyboard:false }).addTo(this.layer));
			if (this.preview) this.layer.addLayer(this.preview);
		}
		_onMove(e) { if (this.state === 'drawing') this._redraw(e.latlng); }
		_onClick(e) {
			if (this.mode === 'pick') {
				if (this.onPick) this.onPick(e.latlng);
				this.deactivate();
				return;
			}
			// Finish area when clicking first vertex.
			if (this.mode === 'area' && this.vertices.length >= 3 && this._near(e.latlng, this.vertices[0])) { this._finish(); return; }
			this.vertices.push(e.latlng);
			this.state = 'drawing';
			// Distance: immediately report the first segment; radius/bearing complete on second click.
			if ((this.mode === 'radius' || this.mode === 'bearing') && this.vertices.length === 2) { this._finish(true); return; }
			if (this.mode === 'distance' && this.vertices.length >= 2) this._redraw(); else this._redraw();
		}
		_near(a, b) { return distance(a, b) < Math.max(8, this.layer._map ? 8 / Math.pow(2, this.layer._map.getZoom()) * 111319 : 20); }
		_finish(keep) {
			this._redraw();
			const total = this.totalM();
			let text = '';
			if (this.mode === 'distance') text = __('Total: {0}', [fmtLength(total, this._unitLen())]);
			if (this.mode === 'area')     text = __('Area: {0}', [fmtArea(ringArea(this.vertices), 'km²')]);
			if (this.mode === 'radius')   text = __('Radius: {0}', [fmtLength(total, this._unitLen())]);
			if (this.mode === 'bearing') { const br = bearing(this.vertices[0], this.vertices[1]); text = Math.round(br) + '° ' + compass(br) + ' · ' + fmtLength(distance(this.vertices[0], this.vertices[1]), this._unitLen()); }
			this.onStatus(text, false, null);
			this.state = 'complete';
			this.map.getContainer().style.cursor = '';
			if (keep && (this.mode === 'radius' || this.mode === 'bearing')) { /* leave graphic */ this.map.off('mousemove', this._onMove); return; }
			this.map.off('click', this._onClick); this.map.off('mousemove', this._onMove); this.map.off('dblclick', this._onDbl);
			L.DomEvent.off(document, 'keydown', this._onKey);
		}
	}

	/* ---------- Relationship overlay layer ---------- */
	class RelLayer {
		constructor(map, opts) {
			this.map = map;
			this.pointsById = opts.pointsById; // Map("['DocType','Name']" -> {lat,lng,label,doctype})
			this.edges = [];
			this.types = new Map();          // type -> {color, dash}
			this.layer = L.layerGroup().addTo(map);
			this.egoId = null;
			this.enabledTypes = null;        // Set or null = all
			this.dateRange = null;
			this._curves = new Map();
			// Default palette; callers can extend with registerType().
			this.registerType(__('Command'),        '#c3564b', null);
			this.registerType(__('Membership'),     '#3577c0', '6 4');
			this.registerType(__('Deployment'),     '#867e45', null);
			this.registerType(__('Participation'),  '#d08733', null);
			this.registerType(__('Family'),         '#b56d2c', '3 4');
			this.registerType(__('Source'),         '#aa6b85', '2 3');
			this.registerType(__('Location'),       '#188c7e', null);
		}
		registerType(label, color, dash) { this.types.set(label, {color, dash}); }
		setEdges(edges) { this.edges = edges; this.redraw(); }
		setEgo(id) { this.egoId = id; this.redraw(); }
		setTypeFilter(types) { this.enabledTypes = types && types.size ? types : null; this.redraw(); }
		clearEgo() { this.egoId = null; this.redraw(); }
		redraw() {
			this.layer.clearLayers();
			const ids = this.pointsById;
			let edges = this.edges.filter(e => {
				const a = ids.get(JSON.stringify(e.source)), b = ids.get(JSON.stringify(e.target));
				if (!a || !b) return false;
				if (this.enabledTypes && !this.enabledTypes.has(e.type)) return false;
				if (this.egoId) {
					const mine = JSON.stringify(e.source) === this.egoId || JSON.stringify(e.target) === this.egoId;
					if (!mine && !e._showWithEgo) return false;
				}
				return true;
			});
			// Count parallel edges per (undirected) pair for offsetting.
			const pairCount = new Map(), pairIndex = new Map();
			edges.forEach(e => {
				const key = [JSON.stringify(e.source), JSON.stringify(e.target)].sort().join('|');
				pairCount.set(key, (pairCount.get(key) || 0) + 1);
			});
			edges.forEach(e => {
				const a = ids.get(JSON.stringify(e.source)), b = ids.get(JSON.stringify(e.target));
				const key = [JSON.stringify(e.source), JSON.stringify(e.target)].sort().join('|');
				const idx = pairIndex.get(key) || 0; pairIndex.set(key, idx + 1);
				const total = pairCount.get(key);
				const offset = total === 1 ? 0 : (idx - (total - 1) / 2) * 14;
				const style = this.types.get(e.type) || {color:'#536b78', dash:null};
				const dimmed = this.egoId && !(JSON.stringify(e.source) === this.egoId || JSON.stringify(e.target) === this.egoId);
				// Geodesic-ish great-circle preview: sample the straight midpoint offset perpendicular to AB.
				const A = L.latLng(+a.latitude, +a.longitude), B = L.latLng(+b.latitude, +b.longitude);
				const mid = L.latLngBounds([A,B]).getCenter();
				const dx = B.lng - A.lng, dy = B.lat - A.lat, len = Math.hypot(dx,dy) || 1;
				const curve = offset ? L.polyline([A, [mid.lat + (-dx/len)*offset/110, mid.lng + (dy/len)*offset/110/Math.cos(toRad(mid.lat))], B], {
					color:style.color, weight: dimmed ? 1.5 : 2.5, opacity: dimmed ? 0.25 : 0.75,
					dashArray: style.dash || null, smoothFactor:1.2, interactive:!dimmed
				}) : L.polyline([A,B], {
					color:style.color, weight: dimmed ? 1.5 : 2.5, opacity: dimmed ? 0.25 : 0.7,
					dashArray: style.dash || null, interactive:!dimmed
				});
				// Direction arrow on directed edges.
				if (/directed|one.way/i.test(e.direction)) {
					const tip = B, tail = A;
					const head = destination({lat:tip.lat - 0.0001,lng:tip.lng - 0.0001}, bearing({lat:(tip.lat*7+tail.lat)/8,lng:(tip.lng*7+tail.lng)/8}, tip)-180, Math.max(8, distance(A,B)*0.03));
					L.polygon([tip, destination(tip, bearing(A,B)+150, Math.max(10, distance(A,B)*0.04)), destination(tip, bearing(A,B)-150, Math.max(10, distance(A,B)*0.04))], { color:style.color, fillColor:style.color, fillOpacity: dimmed?0.2:0.9, weight:0, interactive:false }).addTo(this.layer);
				}
				curve.on('click', () => {
					if (this.onEdgeClick) this.onEdgeClick(e);
				});
				if (!dimmed) {
					const tt = (e.type || __('Relationship')) + (e.start_date ? ' · ' + e.start_date.substr(0,4) : '') + (e.end_date ? '–' + e.end_date.substr(0,4) : '');
					curve.bindTooltip(tt, { sticky:true, direction:'top', className:'siraj-edge-tooltip' });
				}
				curve.addTo(this.layer);
			});
		}
	}

	/* ---------- Declarative tool registry ---------- */
	// id, group, kind ('map-tool'|'app-fn'), icon, mode ('toggle'|'momentary'|'popover'|'draw'), hotkey
	const TOOL_SPEC = [
		// Map tools — live in the in-canvas dock.
		{ id:'nav_in',       group:__('Navigate'), kind:'map-tool', icon:'zoom_in',  mode:'momentary', hotkey:'+', tooltip:__('Zoom in') },
		{ id:'nav_out',      group:__('Navigate'), kind:'map-tool', icon:'zoom_out', mode:'momentary', hotkey:'-', tooltip:__('Zoom out') },
		{ id:'nav_home',     group:__('Navigate'), kind:'map-tool', icon:'home',     mode:'momentary', hotkey:'H', tooltip:__('Home view') },
		{ id:'nav_fit',      group:__('Navigate'), kind:'map-tool', icon:'fit',      mode:'momentary', hotkey:'F', tooltip:__('Fit data to view') },
		{ id:'nav_goto',     group:__('Navigate'), kind:'map-tool', icon:'locate',   mode:'popover',   hotkey:'G', tooltip:__('Go to coordinates') },
		{ id:'nav_me',       group:__('Navigate'), kind:'map-tool', icon:'locate_me',mode:'momentary', hotkey:'M', tooltip:__('My location') },
		{ id:'basemap',      group:__('Basemap'),  kind:'map-tool', icon:'layers',   mode:'popover',   hotkey:'B', tooltip:__('Basemap') },
		{ id:'measure_dist', group:__('Measure'),  kind:'map-tool', icon:'ruler',    mode:'draw',      hotkey:'D', tooltip:__('Distance') },
		{ id:'measure_area', group:__('Measure'),  kind:'map-tool', icon:'area',     mode:'draw',      hotkey:'A', tooltip:__('Area') },
		{ id:'measure_rad',  group:__('Measure'),  kind:'map-tool', icon:'radius',   mode:'draw',      hotkey:'R', tooltip:__('Radius') },
		{ id:'measure_brg',  group:__('Measure'),  kind:'map-tool', icon:'bearing',  mode:'draw',      hotkey:'Y', tooltip:__('Bearing') },
		{ id:'measure_clear',group:__('Measure'),  kind:'map-tool', icon:'clear',    mode:'momentary', hotkey:'C', tooltip:__('Clear measurement') },
		{ id:'pick',         group:__('Pick'),     kind:'map-tool', icon:'pick',     mode:'draw',      hotkey:'P', tooltip:__('Pick a point to link a record') },
		{ id:'overlay_rel',  group:__('Overlays'), kind:'map-tool', icon:'lines',    mode:'toggle',    hotkey:'L', tooltip:__('Relationship lines') },
		{ id:'overlay_clust',group:__('Overlays'), kind:'map-tool', icon:'cluster',  mode:'toggle',    hotkey:'K', tooltip:__('Cluster markers') },
		// Application functions — live in the side panel, not the dock.
		{ id:'panel_records',group:__('Panels'),   kind:'app-fn',   icon:'panel_left', mode:'toggle',  tooltip:__('Records panel') },
		{ id:'panel_details',group:__('Panels'),   kind:'app-fn',   icon:'panel_right',mode:'toggle',  tooltip:__('Details panel') },
		{ id:'filter_type',  group:__('Filters'),  kind:'app-fn',   icon:'search',    mode:'popover', tooltip:__('Filter by type') },
		{ id:'export',       group:__('Data'),     kind:'app-fn',   icon:'export',    mode:'momentary', tooltip:__('Export GeoJSON') },
		{ id:'download',     group:__('Data'),     kind:'app-fn',   icon:'download',  mode:'popover',   tooltip:__('Download offline tiles') },
		{ id:'legend',       group:__('Data'),     kind:'app-fn',   icon:'info',      mode:'toggle',    tooltip:__('Legend') },
		{ id:'about',        group:__('Data'),     kind:'app-fn',   icon:'help',      mode:'popover',   tooltip:__('About & hotkeys') },
		// Selection / relationship tools (activate only when something is selected).
		{ id:'sel_ego',      group:__('Selection'),kind:'map-tool', icon:'ego',       mode:'momentary', hotkey:'S', tooltip:__('Show connections of selected') },
		{ id:'sel_depth1',   group:__('Selection'),kind:'map-tool', icon:'hop1',      mode:'momentary', hotkey:'1', tooltip:__('Direct connections') },
		{ id:'sel_depth2',   group:__('Selection'),kind:'map-tool', icon:'hop2',      mode:'momentary', hotkey:'2', tooltip:__('Two hops') },
		{ id:'sel_depth3',   group:__('Selection'),kind:'map-tool', icon:'hop3',      mode:'momentary', hotkey:'3', tooltip:__('Three hops') },
		{ id:'sel_isolate',  group:__('Selection'),kind:'map-tool', icon:'isolate',   mode:'toggle',    hotkey:'I', tooltip:__('Isolate selection') },
		{ id:'sel_path',     group:__('Selection'),kind:'map-tool', icon:'path',      mode:'momentary', hotkey:'T', tooltip:__('Path to another entity') },
		{ id:'sel_back',     group:__('Selection'),kind:'map-tool', icon:'back',      mode:'momentary', hotkey:'Backspace', tooltip:__('Back to previous selection') },
		{ id:'sel_clear',    group:__('Selection'),kind:'map-tool', icon:'eraser',    mode:'momentary', hotkey:'Esc', tooltip:__('Clear selection') },
		{ id:'link_add',     group:__('Selection'),kind:'map-tool', icon:'link_add',  mode:'momentary', hotkey:'N', tooltip:__('Add relationship to selected') },
		{ id:'sel_open',     group:__('Selection'),kind:'app-fn',   icon:'card',      mode:'momentary', hotkey:'Enter', tooltip:__('Open selected record') },
		{ id:'edge_filter',  group:__('Selection'),kind:'map-tool', icon:'edge_filter',mode:'popover',   tooltip:__('Filter relationship types') },
	];

	/* Generated help overlay (single source of truth for hotkey map). */
	function helpOverlay() {
		const groups = {};
		TOOL_SPEC.forEach(t => { (groups[t.group] = groups[t.group] || []).push(t); });
		const root = document.createElement('div');
		root.className = 'siraj-help-overlay';
		Object.keys(groups).forEach(g => {
			const sec = document.createElement('section');
			const h = document.createElement('h6'); h.textContent = g; sec.appendChild(h);
			const ul = document.createElement('ul');
			groups[g].forEach(t => {
				const li = document.createElement('li');
				const glyph = (window.sirajIcons && window.sirajIcons.toolSvg) ? window.sirajIcons.toolSvg(t.icon, {size:14}) : '';
				const kbd = t.hotkey ? '<kbd>' + t.hotkey + '</kbd>' : '';
				li.innerHTML = '<span class="siraj-help-glyph">' + glyph + '</span><span class="siraj-help-label">' + t.tooltip + '</span>' + kbd;
				ul.appendChild(li);
			});
			sec.appendChild(ul); root.appendChild(sec);
		});
		return root;
	}

	window.SirajMapKit = { Geodesic: { distance, area: ringArea, bearing, destination, fmtLength, fmtArea, compass }, MeasureTool, RelLayer, TOOL_SPEC, helpOverlay };
})();
