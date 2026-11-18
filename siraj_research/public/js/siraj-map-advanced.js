/* SIRAJ Map overlays — statistics, charts, command palette, coordinate
 * readout, minimap, box-select, time slider, multi-select bar, share/print.
 *
 * Attaches via SirajMapAdvanced.attach(map, opts) where opts supplies data
 * and callbacks. Works on any Leaflet map (Explorer geo, coordinate_map,
 * native MapView). Idempotent — only one overlay set per container.
 */
(() => {
	'use strict';

	// ---------- small SVG helpers ----------
	function svg(icon) {
		const paths = {
			records: '<path d="M4 6h16M4 12h16M4 18h10"/>',
			places:  '<path d="M12 2C8 2 5 5 5 9c0 5 7 13 7 13s7-8 7-13c0-4-3-7-7-7z"/><circle cx="12" cy="9" r="2.5"/>',
			people:  '<circle cx="9" cy="8" r="3"/><path d="M3 21c0-3 3-5 6-5s6 2 6 5"/><circle cx="17" cy="9" r="2.5"/><path d="M14 21c0-2 2-4 4.5-4"/>',
			units:   '<path d="M3 11l9-7 9 7-9 7z"/>',
			events:  '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 9h18M8 3v4M16 3v4"/>',
			deploys: '<path d="M4 20l8-16 8 16H4z"/>',
			selected:'<path d="M5 12l5 5L20 7"/>',
			edges:   '<path d="M4 18l6-10 4 6 6-10"/>',
			area:    '<path d="M4 20V10l6-6 4 4 6-2v14z"/>',
			clock:   '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
			search:  '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
			cmd:     '<path d="M6 8l-4 4 4 4M10 20l4-16M18 8l4 4-4 4"/>',
			print:   '<path d="M6 9V3h12v6M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2M6 14h12v7H6z"/>',
			share:   '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m8.6 13.5 6.8 4M15.4 6.5l-6.8 4"/>',
			geojson: '<path d="M4 4l5 1 4-2 5 3 2 5-2 6-5 4-7-2-3-6z"/>',
		};
		return `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${paths[icon] || ''}</svg>`;
	}
	function stat(label, num, icon, cls) {
		return `<span class="sx-stat-chip ${cls||''}">${icon?svg(icon):''}<span>${label}</span> <span class="sx-stat-num">${num}</span></span>`;
	}
	function fmt(n) {
		if (n == null) return '—';
		if (n >= 1000000) return (n/1000000).toFixed(1)+'M';
		if (n >= 1000) return (n/1000).toFixed(n<10000?1:0)+'k';
		return String(n);
	}

	// ---------- Stats dock ----------
	function StatsDock(map, getData) {
		const el = document.createElement('div');
		el.className = 'sx-stats-dock';
		map.getContainer().appendChild(el);
		function render() {
			const d = getData() || {};
			const counts = d.typeCounts || {};
			const typeList = [
				['Person',         counts.Person||0,         'people'],
				['Place',          counts.Place||0,          'places'],
				['Institution',    counts.Institution||0,    'units'],
				['Military Unit',  counts['Military Unit']||0,'units'],
				['Research Event', counts['Research Event']||0,'events'],
				['Operational Deployment', counts['Operational Deployment']||0, 'deploys'],
			].filter(([,n])=>n>0);
			const chips = [
				stat('Records', fmt(d.total || 0), 'records'),
				stat('Selected', fmt(d.selected || 0), 'selected', d.selected ? 'is-good' : ''),
				stat('Visible', fmt(d.visible || 0), 'area', d.truncated ? 'is-warn' : ''),
				stat('Links', fmt(d.edges||0), 'edges'),
			];
			typeList.slice(0,4).forEach(([lbl,n,ic]) => chips.push(stat(lbl.split(' ')[0], fmt(n), ic)));
			el.innerHTML = chips.join('');
		}
		return { el, render };
	}

	// ---------- Coordinate readout ----------
	function CoordReadout(map, opts) {
		const el = document.createElement('div');
		el.className = 'sx-coord-readout';
		el.innerHTML = '<span class="sx-coord-lat">lat —</span><span class="sx-coord-lon">lon —</span>';
		map.getContainer().appendChild(el);
		function fmtCoord(v, axis) {
			if (v == null || !isFinite(v)) return axis + ' —';
			const hemi = axis === 'lat' ? (v>=0?'N':'S') : (v>=0?'E':'W');
			return `${Math.abs(v).toFixed(4)}° ${hemi}`;
		}
		map.on('mousemove', e => {
			el.querySelector('.sx-coord-lat').textContent = fmtCoord(e.latlng.lat,'lat');
			el.querySelector('.sx-coord-lon').textContent = fmtCoord(e.latlng.lng,'lon');
		});
		map.on('mouseout', () => {
			el.querySelector('.sx-coord-lat').textContent = 'lat —';
			el.querySelector('.sx-coord-lon').textContent = 'lon —';
		});
		if (opts && opts.onClick) {
			el.classList.add('is-editable');
			el.title = 'Click to copy coordinates';
			el.addEventListener('click', () => opts.onClick());
		}
		return el;
	}

	// ---------- Minimap ----------
	function Minimap(map, opts) {
		const wrap = document.createElement('div');
		wrap.className = 'sx-minimap';
		// Stop events so clicks/wheel on the minimap don't bubble to the main
		// map (Leaflet interprets them via containerPointToLatLng and throws
		// Invalid LatLng: NaN when coordinates come from a child container).
		if (window.L && L.DomEvent) {
			L.DomEvent.disableClickPropagation(wrap);
			L.DomEvent.disableScrollPropagation(wrap);
		}
		const toggle = document.createElement('button');
		toggle.className = 'sx-minimap-toggle';
		toggle.type = 'button';
		toggle.textContent = '–';
		toggle.title = 'Toggle minimap';
		const mini = document.createElement('div');
		mini.style.cssText = 'width:100%;height:100%;';
		wrap.appendChild(toggle);
		wrap.appendChild(mini);
		map.getContainer().appendChild(wrap);
		let miniMap, miniRect, tileLayer;
		function ensure() {
			if (miniMap) return;
			miniMap = L.map(mini, {
				attributionControl: false, zoomControl: false,
				dragging: false, scrollWheelZoom: false, doubleClickZoom: false,
				touchZoom: false, keyboard: false, boxZoom: false,
				worldCopyJump: true,
			});
			const url = (opts && opts.tileUrl) || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
			tileLayer = L.tileLayer(url, { maxZoom: 22, maxNativeZoom: 19 }).addTo(miniMap);
			miniRect = L.rectangle(map.getBounds(), {
				color: '#126a68', weight: 2, fillOpacity: 0.10, interactive: false,
			}).addTo(miniMap);
			sync();
			map.on('moveend zoomend resize', sync);
		}
		function sync() {
			if (!miniMap) return;
			const w = mini.clientWidth, h = mini.clientHeight;
			if (!w || !h) return;  // container collapsed — avoid NaN LatLng
			const z = Math.max(0, map.getZoom() - 4);
			try { miniMap.setView(map.getCenter(), z, { animate: false }); } catch(_) {}
			try { miniRect.setBounds(map.getBounds()); } catch(_) {}
		}
		toggle.addEventListener('click', () => {
			wrap.classList.toggle('is-collapsed');
			toggle.textContent = wrap.classList.contains('is-collapsed') ? '+' : '–';
			if (!wrap.classList.contains('is-collapsed')) { ensure(); setTimeout(sync, 80); }
		});
		// Defer minimap init until the main canvas has a real size.
		function initWhenReady(tries) {
			if (map.getContainer().clientWidth > 100 && map.getContainer().clientHeight > 100) {
				ensure();
				setTimeout(sync, 50);
			} else if (tries > 0) {
				setTimeout(() => initWhenReady(tries - 1), 200);
			}
		}
		initWhenReady(25);
		return { el: wrap, sync };
	}

	// ---------- Box select (shift-drag) ----------
	function BoxSelect(map, onSelect) {
		let box, start;
		function onMouseDown(e) {
			if (!(e.originalEvent && e.originalEvent.shiftKey)) return;
			if (e.originalEvent.button !== 0) return;
			L.DomEvent.stopPropagation(e.originalEvent);
			L.DomEvent.disableClickPropagation(map.getContainer());
			start = map.mouseEventToContainerPoint(e.originalEvent);
			box = L.DomUtil.create('div', 'sx-boxselect', map.getContainer());
			box.style.left = start.x + 'px';
			box.style.top  = start.y + 'px';
			box.style.width = '0px'; box.style.height = '0px';
			L.DomEvent.on(document, 'mousemove', onMouseMove);
			L.DomEvent.on(document, 'mouseup', onMouseUp);
		}
		function onMouseMove(e) {
			if (!box) return;
			const p = map.mouseEventToContainerPoint(e);
			box.style.left = Math.min(p.x, start.x) + 'px';
			box.style.top  = Math.min(p.y, start.y) + 'px';
			box.style.width  = Math.abs(p.x - start.x) + 'px';
			box.style.height = Math.abs(p.y - start.y) + 'px';
		}
		function onMouseUp(e) {
			L.DomEvent.off(document, 'mousemove', onMouseMove);
			L.DomEvent.off(document, 'mouseup', onMouseUp);
			if (!box) return;
			const rect = box.getBoundingClientRect();
			if (box.parentNode) box.parentNode.removeChild(box);
			box = null;
			if (rect.width < 4 || rect.height < 4) return;
			const tl = map.containerPointToLatLng(L.point(rect.left, rect.top));
			const br = map.containerPointToLatLng(L.point(rect.right, rect.bottom));
			const bounds = L.latLngBounds(tl, br);
			onSelect && onSelect(bounds);
		}
		map.on('mousedown', onMouseDown);
	}

	// ---------- Multi-select bar ----------
	function MultiBar(map) {
		const el = document.createElement('div');
		el.className = 'sx-multi-bar'; el.hidden = true;
		el.innerHTML =
			'<span class="sx-multi-count">0 selected</span>' +
			'<button type="button" data-act="zoom" title="Zoom to selection">⊡ Zoom</button>' +
			'<button type="button" data-act="select-all" title="Add all in view">+ All in view</button>' +
			'<button type="button" data-act="export" title="Export selection">↧ Export</button>' +
			'<button type="button" data-act="clear" title="Clear">✕</button>';
		map.getContainer().appendChild(el);
		const api = {
			set: new Set(),
			update(n) {
				if (typeof n === 'number') { this.set.clear(); }
				this.set.forEach && (this.set = new Set(this.set));
				const c = (n && n.set) ? n.set.size : this.set.size;
				el.querySelector('.sx-multi-count').textContent = c + ' selected';
				el.hidden = c === 0;
			},
			on() {},
		};
		el.addEventListener('click', e => {
			const b = e.target.closest('button'); if (!b) return;
			api.on(b.dataset.act);
		});
		return api;
	}

	// ---------- Command palette ----------
	const PALETTE = null; // singleton
	function openCommandPalette(map, commands) {
		if (PALETTE && PALETTE.parentNode) PALETTE.parentNode.removeChild(PALETTE);
		const root = document.createElement('div');
		root.className = 'sx-cmdpal';
		root.innerHTML =
			'<div class="sx-cmdpal-box" role="dialog" aria-label="Command palette">' +
			'  <div class="sx-cmdpal-head">' + svg('cmd') +
			'    <input class="sx-cmdpal-input" type="text" placeholder="Type a command or search…" autofocus>' +
			'  </div>' +
			'  <ul class="sx-cmdpal-list"></ul>' +
			'  <div class="sx-cmdpal-foot"><kbd>↑/↓</kbd> navigate · <kbd>Enter</kbd> run · <kbd>Esc</kbd> close · <kbd>Ctrl/Cmd-K</kbd></div>' +
			'</div>';
		document.body.appendChild(root);
		const input = root.querySelector('.sx-cmdpal-input');
		const list = root.querySelector('.sx-cmdpal-list');
		let activeIdx = 0, filtered = commands.slice();
		function render() {
			const q = input.value.trim().toLowerCase();
			filtered = commands.filter(c => !q || (c.label + ' ' + (c.desc||'')).toLowerCase().indexOf(q) !== -1);
			if (activeIdx >= filtered.length) activeIdx = 0;
			list.innerHTML = filtered.length
				? filtered.map((c,i) =>
					`<li class="sx-cmdpal-item${i===activeIdx?' is-active':''}" data-i="${i}">` +
						`<span class="sx-cmd-icon">${svg(c.icon||'records')}</span>` +
						`<span>${c.label}${c.desc?' <small>'+c.desc+'</small>':''}</span>` +
						(c.hotkey ? `<span class="sx-cmd-kbd">${c.hotkey}</span>` : '') +
					`</li>`).join('')
				: `<li class="sx-cmdpal-empty">No matching commands</li>`;
		}
		function run() {
			const c = filtered[activeIdx]; if (!c) return;
			close();
			try { c.action && c.action(); } catch(err) { console.warn('[SIRAJ palette]', err); }
		}
		function close() { if (root.parentNode) root.parentNode.removeChild(root); document.removeEventListener('keydown', onKey); }
		function onKey(e) {
			if (e.key === 'Escape') { e.preventDefault(); close(); return; }
			if (e.key === 'ArrowDown') { e.preventDefault(); activeIdx = Math.min(filtered.length-1, activeIdx+1); render(); return; }
			if (e.key === 'ArrowUp')   { e.preventDefault(); activeIdx = Math.max(0, activeIdx-1); render(); return; }
			if (e.key === 'Enter')     { e.preventDefault(); run(); return; }
		}
		input.addEventListener('input', () => { activeIdx = 0; render(); });
		list.addEventListener('click', e => {
			const li = e.target.closest('.sx-cmdpal-item'); if (!li) return;
			activeIdx = Number(li.dataset.i); run();
		});
		root.addEventListener('click', e => { if (e.target === root) close(); });
		document.addEventListener('keydown', onKey);
		setTimeout(() => input.focus(), 20);
		render();
		return { close };
	}

	function bindGlobalPalette(getter) {
		if (window.__sirajPaletteBound) return;
		window.__sirajPaletteBound = true;
		document.addEventListener('keydown', e => {
			if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
				const t = e.target;
				if (t && /INPUT|TEXTAREA|SELECT/.test(t.tagName)) return;
				e.preventDefault();
				getter && openCommandPalette(null, getter());
			}
			if (e.key === '?' && !(e.ctrlKey || e.metaKey || e.altKey)) {
				const t = e.target;
				if (t && /INPUT|TEXTAREA|SELECT/.test(t.tagName)) return;
				// Only open when a map is present on the page.
				if (document.querySelector('.leaflet-container')) {
					e.preventDefault();
					getter && openCommandPalette(null, getter());
				}
			}
		});
	}

	// ---------- Charts (small inline bar + donut) ----------
	function barChart(values, opts) {
		opts = opts || {};
		const w = 280, h = 80, pad = 16;
		const max = Math.max(1, ...values.map(v => v.v));
		const bw = (w - pad*2) / Math.max(1, values.length);
		const bars = values.map((v, i) => {
			const bh = (v.v / max) * (h - pad*2);
			const x = pad + i*bw + 2;
			const y = h - pad - bh;
			return `<rect class="bar" x="${x}" y="${y}" width="${bw-4}" height="${bh}" rx="2">
				<title>${v.label}: ${v.v}</title></rect>
				<text x="${x+bw/2}" y="${h-2}" text-anchor="middle">${v.label.length>6?v.label.slice(0,5)+'…':v.label}</text>`;
		}).join('');
		return `<svg class="sx-chart-svg" viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg">
			<line class="axis" x1="${pad}" y1="${h-pad}" x2="${w-pad}" y2="${h-pad}"/>
			${bars}
		</svg>`;
	}
	function donutChart(parts) {
		const cx = 50, cy = 50, r = 36, r2 = 22, C = 2*Math.PI*r;
		let acc = 0;
		const segs = parts.map((p, i) => {
			const frac = p.v / Math.max(1, parts.reduce((a,b)=>a+b.v,0));
			const dash = frac*C + ' ' + C;
			const rot = (acc / Math.max(1, parts.reduce((a,b)=>a+b.v,0))) * 360;
			acc += p.v;
			return `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${p.color}" stroke-width="${r-r2}" stroke-dasharray="${dash}" transform="rotate(${rot-90} ${cx} ${cy})"><title>${p.label}: ${p.v}</title></circle>`;
		}).join('');
		const legend = parts.map(p => `<span><i style="background:${p.color}"></i>${p.label} ${p.v}</span>`).join('');
		return `<div class="sx-chart-row">
			<svg class="sx-donut" viewBox="0 0 100 100">${segs}</svg>
			<div class="sx-chart-legend">${legend}</div>
		</div>`;
	}

	// ---------- Public API ----------
	window.SirajMapAdvanced = {
		StatsDock, CoordReadout, Minimap, BoxSelect, MultiBar,
		openCommandPalette, bindGlobalPalette,
		charts: { barChart, donutChart },
		svg, stat, fmt,
		attach(map, opts) {
			opts = opts || {};
			if (map._sirajAdvanced) return map._sirajAdvanced;
			const stats = StatsDock(map, opts.getData || (() => ({})));
			const readout = CoordReadout(map, opts.readout);
			const minimap = Minimap(map, opts.minimap);
			const multi = MultiBar(map);
			BoxSelect(map, bounds => opts.onBoxSelect && opts.onBoxSelect(bounds));
			map._sirajAdvanced = { stats, readout, minimap, multi, refresh: () => stats.render() };
			return map._sirajAdvanced;
		},
	};

	// Bind the global palette opener once.
	bindGlobalPalette(() => {
		// Collect commands from the currently-focused map (or the first one).
		const maps = Array.from(document.querySelectorAll('.leaflet-container'));
		const cmds = [
			{ label:'Zoom in',  icon:'zoom_in',  hotkey:'+', action:() => maps.forEach(m => m._leaflet_map && m._leaflet_map.zoomIn()) },
			{ label:'Zoom out', icon:'zoom_out', hotkey:'-', action:() => maps.forEach(m => m._leaflet_map && m._leaflet_map.zoomOut()) },
			{ label:'Fit data', icon:'fit',      hotkey:'F', action:() => { window.dispatchEvent(new KeyboardEvent('keydown',{key:'f',ctrlKey:false})); } },
			{ label:'Go to coordinates', icon:'locate', hotkey:'G', action:() => { window.dispatchEvent(new KeyboardEvent('keydown',{key:'g'})); } },
			{ label:'Toggle basemaps', icon:'layers', hotkey:'B', action:() => { window.dispatchEvent(new KeyboardEvent('keydown',{key:'b'})); } },
			{ label:'Measure distance', icon:'ruler', hotkey:'D', action:() => { window.dispatchEvent(new KeyboardEvent('keydown',{key:'d'})); } },
			{ label:'Clear selection', icon:'eraser', hotkey:'Esc', action:() => { window.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'})); } },
			{ label:'Print map', icon:'print', hotkey:'Ctrl+P', action:() => window.print() },
		];
		return cmds;
	});
})();
