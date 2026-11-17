/* SIRAJ map toolbar — an embeddable Leaflet control that hosts every map tool
 * directly inside the canvas (as opposed to a toolbar strip above it).
 *
 * Usage:
 *   const toolbar = new L.Control.SirajToolbar({ position: 'topright', ... })
 *       .addTo(map);
 *   toolbar
 *     .group(__('Basemap'))
 *       .add({ icon: 'layers',  label: __('Basemap'),  action: ..., menu: [...] })
 *       .add(...)
 *     .group(__('Navigate'))
 *       .add({ icon: 'zoom_in', label: __('Zoom in'),  action: () => map.zoomIn() })
 *       .add({ icon: 'fit',     label: __('Fit data'), action: () => {...} });
 *
 * The toolbar renders as a single vertical strip of iconic buttons docked in a
 * map corner. Clicking a button with a `menu` expands a popover panel; buttons
 * without a menu fire their action immediately. One group ends with a thin
 * separator, giving visual structure without stealing space from the map.
 */
(() => {
	'use strict';
	if (!window.L) { console.warn('L.Control.SirajToolbar requires Leaflet'); return; }

	const TOOL_MISSING = '<svg class="siraj-ico-missing" viewBox="0 0 24 24" width="18" height="18" role="img" aria-hidden="true" fill="none" stroke="#c0392b" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" stroke-dasharray="3 2"/><path d="M8 8l8 8M16 8l-8 8"/></svg>';

	function toolIcon(name, label) {
		const si = window.sirajIcons;
		if (!si || !si.tools) { console.error('[SIRAJ toolbar] sirajIcons.tools not ready when rendering', name); return TOOL_MISSING; }
		if (!si.tools[name]) {
			console.error('[SIRAJ toolbar] missing tool icon:', name);
			return TOOL_MISSING;
		}
		const cls = 'siraj-ico siraj-ico-' + name;
		return si.toolSvg(name, { size: 18, cls, ariaLabel: label });
	}

	L.Control.SirajToolbar = L.Control.extend({
		options: { position: 'topright' },
		initialize(options) {
			L.Util.setOptions(this, options || {});
			this._groups = [];
			this._current = null;   // currently open group/popover
			this._buttons = new Map();
		},
		onAdd(map) {
			this._map = map;
			this._container = L.DomUtil.create('div', 'siraj-toolbar leaflet-bar');
			this._container.setAttribute('role', 'toolbar');
			this._container.setAttribute('aria-label', __('Map tools'));
			L.DomEvent.disableClickPropagation(this._container);
			L.DomEvent.disableScrollPropagation(this._container);
			map.on('click', () => this._closeAll(), this);
			return this._container;
		},
		onRemove() {
			if (this._map) this._map.off('click', this._closeAll, this);
		},

		/* ------- Public API ------- */
		group(label) {
			const g = { label, items: [] };
			this._groups.push(g);
			this._renderGroup(g);
			return this._groupApi(g);
		},
		separator() {
			L.DomUtil.create('div', 'siraj-toolbar-sep', this._container);
			return this;
		},
		status(text, cls) {
			if (!this._statusLine) {
				this._statusLine = L.DomUtil.create('div', 'siraj-toolbar-status', this._container);
			}
			this._statusLine.textContent = text || '';
			this._statusLine.classList.toggle('siraj-toolbar-warning', cls === 'warning');
			return this;
		},
		/* Attach any DOM node (e.g. cluster toggle, fit button) that already
		 * exists as a jQuery element — used when migrating existing tools. */
		attachNode(node) {
			const wrap = L.DomUtil.create('div', 'siraj-toolbar-custom', this._container);
			wrap.appendChild(node[0] || node);
			return this;
		},

		/* ------- Internals ------- */
		_groupApi(g) {
			const self = this;
			return {
				add(spec) { self._addButton(g, spec); return this; },
				end: () => self,
			};
		},
		_renderGroup(/*g*/) {},
		_addButton(g, spec) {
			const btn = L.DomUtil.create('button', 'siraj-toolbar-btn', this._container);
			btn.type = 'button';
			const label = spec.tooltip || spec.label || '';
			const hotkey = spec.hotkey ? ' (' + spec.hotkey + ')' : '';
			btn.title = label + hotkey;
			btn.setAttribute('aria-label', label);
			if (spec.mode === 'toggle' || spec.active) btn.setAttribute('aria-pressed', spec.active ? 'true' : 'false');
			if (spec.key) btn.setAttribute('data-siraj-key', spec.key);
			btn.innerHTML = toolIcon(spec.icon, label) +
				(label ? `<span class="siraj-toolbar-label">${__(label)}</span>` : '');
			if (spec.active) btn.classList.add('is-active');
			g.items.push({ spec, btn });
			L.DomEvent.on(btn, 'click', e => {
				L.DomEvent.stopPropagation(e);
				if (spec.menu) {
					this._togglePopover(btn, spec);
				} else if (typeof spec.action === 'function') {
					this._closeAll();
					const pressed = !btn.classList.contains('is-active');
					if (spec.mode === 'toggle') { btn.classList.toggle('is-active', pressed); btn.setAttribute('aria-pressed', pressed ? 'true' : 'false'); }
					spec.action.call(spec, e);
				}
			});
			this._buttons.set(spec.key || spec.label || spec.icon, btn);
			return btn;
		},
		_togglePopover(anchor, spec) {
			if (this._current && this._current.anchor === anchor) {
				this._closeAll(); return;
			}
			this._closeAll();
			const pop = L.DomUtil.create('div', 'siraj-toolbar-pop', this._container);
			pop.setAttribute('role', 'dialog');
			pop.setAttribute('aria-label', spec.label);
			if (spec.menuTitle) {
				const h = L.DomUtil.create('div', 'siraj-toolbar-pop-title', pop);
				h.textContent = __(spec.menuTitle);
			}
			if (typeof spec.menu === 'function') {
				spec.menu(pop, () => this._closeAll());
			} else if (Array.isArray(spec.menu)) {
				spec.menu.forEach(item => {
					if (item === '-') { L.DomUtil.create('hr', '', pop); return; }
					const opt = L.DomUtil.create('button', 'siraj-toolbar-opt' + (item.active ? ' is-active' : ''), pop);
					opt.type = 'button';
					opt.innerHTML = (item.icon ? toolIcon(item.icon, item.label) : '') +
						`<span>${__(item.label)}</span>`;
					L.DomEvent.on(opt, 'click', ev => {
						L.DomEvent.stopPropagation(ev);
						if (item.action) item.action(ev);
						if (!item.sticky) this._closeAll();
					});
				});
			}
			// Position: Leaflet places .leaflet-top right after the zoom control.
			// The popover opens to the LEFT of the strip (since strip is top-right).
			pop.style.right = (this._container.offsetWidth + 8) + 'px';
			pop.style.top = anchor.offsetTop + 'px';
			this._container.appendChild(pop);
			anchor.classList.add('is-open');
			this._current = { anchor, pop };
			// click-outside handled by map 'click' handler (we stopProp on toolbar).
			L.DomEvent.on(pop, 'click', L.DomEvent.stopPropagation);
		},
		_closeAll() {
			if (this._current) {
				L.DomEvent.off(this._current.pop, 'click', L.DomEvent.stopPropagation);
				this._current.pop.remove();
				this._current.anchor.classList.remove('is-open');
				this._current = null;
			}
			this._container.querySelectorAll('.siraj-toolbar-btn.is-toggled').forEach(b => b.classList.remove('is-toggled'));
		},
		setActive(key, on) {
			const btn = this._buttons.get(key);
			if (btn) { btn.classList.toggle('is-active', !!on); btn.setAttribute('aria-pressed', on ? 'true' : 'false'); }
		},
		show()  { if (this._container) this._container.style.display = ''; this._hidden = false; },
		hide()  { if (this._container) this._container.style.display = 'none'; this._hidden = true; this._closeAll(); },
		toggle(){ this._hidden ? this.show() : this.hide(); return !this._hidden; },
		isVisible() { return !this._hidden; },
	});
	L.control.sirajToolbar = options => new L.Control.SirajToolbar(options);
})();
