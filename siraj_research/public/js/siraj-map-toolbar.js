/* SIRAJ map toolbar — an embeddable Leaflet control with:
 *   • Grouped buttons (Navigate / Basemap / Measure / Pick / Overlays / Selection / …)
 *   • Collapsible group headers (click the header to collapse a section)
 *   • Three display modes: 'icons' (compact, icon-only), 'labels' (icon + text label),
 *     'auto' (icon + label on wide viewports, collapses to icons when the viewport is
 *     short or the user has many tools) — persisted in localStorage.
 *   • Internal scroll when total height exceeds the viewport, so every tool remains
 *     reachable even with dozens of buttons.
 *   • A footer with a display-mode switcher (icons/labels/auto) and a "collapse all"
 *     shortcut.
 *   • Full RTL support, keyboard navigation, aria-expanded / aria-pressed on every
 *     toggle, and every label pulled through __() for translation.
 *   • Popover menus open toward the map interior (left for right-docked bars) with
 *     proper z-index and scroll containment.
 *
 * Usage:
 *   const toolbar = L.control.sirajToolbar({ position:'topright' }).addTo(map);
 *   toolbar.group('Navigate')
 *     .add({ icon:'zoom_in', label:'Zoom in', key:'nav_in', hotkey:'+', action:()=>map.zoomIn() })
 *     .add({ icon:'fit', label:'Fit to data', key:'nav_fit', hotkey:'F', action:... });
 *   toolbar.separator(); // thin divider between groups
 *   toolbar.group('Basemap')
 *     .add({ icon:'layers', label:'Basemap', key:'basemap', mode:'popover', menuTitle:'Basemap', menu:(pop)=>{...} });
 */
(() => {
	'use strict';
	if (!window.L) { console.warn('L.Control.SirajToolbar requires Leaflet'); return; }

	const TOOL_MISSING = '<svg class="siraj-ico-missing" viewBox="0 0 24 24" width="18" height="18" role="img" aria-hidden="true" fill="none" stroke="#c0392b" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" stroke-dasharray="3 2"/><path d="M8 8l8 8M16 8l-8 8"/></svg>';

	const STORE_KEY = 'siraj.toolbar.labelMode';
	const GROUP_KEY = 'siraj.toolbar.groups';

	function toolIcon(name, label) {
		const si = window.sirajIcons;
		if (!si || !si.tools) { return TOOL_MISSING; }
		if (!si.tools[name]) { return TOOL_MISSING; }
		return si.toolSvg(name, { size: 18, cls: 'siraj-ico siraj-ico-' + name, ariaLabel: label });
	}

	function loadPref(key, fallback) {
		try { const v = window.localStorage && localStorage.getItem(key); return v == null ? fallback : v; }
		catch { return fallback; }
	}
	function savePref(key, val) {
		try { if (window.localStorage) localStorage.setItem(key, String(val)); } catch {}
	}
	function loadGroupState() {
		try {
			const raw = window.localStorage && localStorage.getItem(GROUP_KEY);
			if (!raw) return {};
			return JSON.parse(raw) || {};
		} catch { return {}; }
	}
	function saveGroupState(state) {
		try { if (window.localStorage) localStorage.setItem(GROUP_KEY, JSON.stringify(state)); } catch {}
	}

	L.Control.SirajToolbar = L.Control.extend({
		options: { position: 'topright' },
		initialize(options) {
			L.Util.setOptions(this, options || {});
			this._groups = [];
			this._current = null;
			this._buttons = new Map();
			this._labelMode = loadPref(STORE_KEY, 'auto'); // 'auto' | 'icons' | 'labels'
			this._groupState = loadGroupState(); // {groupLabel: collapsed-boolean}
		},
		onAdd(map) {
			this._map = map;
			this._container = L.DomUtil.create('div', 'siraj-toolbar leaflet-bar');
			this._container.setAttribute('role', 'toolbar');
			this._container.setAttribute('aria-label', __('Map tools'));
			L.DomEvent.disableClickPropagation(this._container);
			L.DomEvent.disableScrollPropagation(this._container);

			// Header (title + collapse-all)
			this._header = L.DomUtil.create('div', 'siraj-toolbar-head', this._container);
			const title = L.DomUtil.create('div', 'siraj-toolbar-title', this._header);
			title.textContent = __('Map tools');
			const headBtns = L.DomUtil.create('div', 'siraj-toolbar-head-btns', this._header);
			this._collapseAllBtn = this._makeIconButton('chevrons_up', __('Collapse all sections'), () => this._setAllGroups(false), headBtns);
			this._expandAllBtn   = this._makeIconButton('chevrons_down', __('Expand all sections'), () => this._setAllGroups(true), headBtns);

			// Scrollable body where groups live.
			this._body = L.DomUtil.create('div', 'siraj-toolbar-body', this._container);
			this._body.setAttribute('role', 'group');
			this._body.setAttribute('aria-label', __('Toolbar sections'));

			// Footer with display-mode switcher.
			this._footer = L.DomUtil.create('div', 'siraj-toolbar-foot', this._container);
			this._buildModeSwitcher();

			map.on('click', () => this._closeAll(), this);
			map.on('resize', () => this._layout(), this);
			// Apply initial label mode.
			this._applyMode();
			// Defer initial layout so buttons are in DOM first.
			setTimeout(() => this._layout(), 0);
			return this._container;
		},
		onRemove() {
			if (this._map) {
				this._map.off('click', this._closeAll, this);
				this._map.off('resize', this._layout, this);
			}
		},

		/* ---------- Public API ---------- */
		group(label) {
			const g = { label, items: [], collapsed: !!this._groupState[label], headerEl: null, bodyEl: null };
			this._groups.push(g);
			this._renderGroup(g);
			this._layout();
			return this._groupApi(g);
		},
		separator() {
			const sep = L.DomUtil.create('div', 'siraj-toolbar-rule', this._body);
			sep.setAttribute('aria-hidden', 'true');
			// Separator is tracked but doesn't hold items.
			this._groups.push({ isSeparator: true, el: sep });
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
		attachNode(node) {
			const wrap = L.DomUtil.create('div', 'siraj-toolbar-custom', this._body);
			wrap.appendChild(node[0] || node);
			return this;
		},
		setActive(key, on) {
			const btn = this._buttons.get(key);
			if (btn) { btn.classList.toggle('is-active', !!on); btn.setAttribute('aria-pressed', on ? 'true' : 'false'); }
		},
		show() { if (this._container) this._container.style.display = ''; this._hidden = false; },
		hide() { if (this._container) this._container.style.display = 'none'; this._hidden = true; this._closeAll(); },
		toggle() { this._hidden ? this.show() : this.hide(); return !this._hidden; },
		isVisible() { return !this._hidden; },

		/* Return the current display mode ('icons' | 'labels' | 'auto'). */
		getLabelMode() { return this._labelMode; },
		setLabelMode(mode) {
			if (!['icons', 'labels', 'auto'].includes(mode)) return;
			this._labelMode = mode;
			savePref(STORE_KEY, mode);
			this._applyMode();
			this._updateModeButtons();
		},

		/* ---------- Group internals ---------- */
		_groupApi(g) {
			const self = this;
			return {
				add(spec) { self._addButton(g, spec); return this; },
				end: () => self,
			};
		},
		_renderGroup(g) {
			if (g.isSeparator) return;
			const wrap = L.DomUtil.create('div', 'siraj-tbgrp' + (g.collapsed ? ' is-collapsed' : ''), this._body);
			g.wrapEl = wrap;

			const head = L.DomUtil.create('button', 'siraj-tbgrp-head', wrap);
			head.type = 'button';
			head.setAttribute('aria-expanded', g.collapsed ? 'false' : 'true');
			head.setAttribute('aria-label', g.label);
			g.headerEl = head;
			const caret = L.DomUtil.create('span', 'siraj-tbgrp-caret', head);
			caret.innerHTML = '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';
			const lbl = L.DomUtil.create('span', 'siraj-tbgrp-label', head);
			lbl.textContent = __(g.label);
			L.DomEvent.on(head, 'click', e => {
				L.DomEvent.stopPropagation(e);
				g.collapsed = !g.collapsed;
				wrap.classList.toggle('is-collapsed', g.collapsed);
				head.setAttribute('aria-expanded', g.collapsed ? 'false' : 'true');
				this._groupState[g.label] = g.collapsed;
				saveGroupState(this._groupState);
				this._layout();
			});

			g.bodyEl = L.DomUtil.create('div', 'siraj-tbgrp-body', wrap);
		},
		_setAllGroups(expanded) {
			this._groups.forEach(g => {
				if (g.isSeparator) return;
				g.collapsed = !expanded;
				if (g.wrapEl) g.wrapEl.classList.toggle('is-collapsed', g.collapsed);
				if (g.headerEl) g.headerEl.setAttribute('aria-expanded', expanded ? 'true' : 'false');
				this._groupState[g.label] = g.collapsed;
			});
			saveGroupState(this._groupState);
			this._layout();
		},
		_addButton(g, spec) {
			if (!g || g.isSeparator || !g.bodyEl) return null;
			const btn = L.DomUtil.create('button', 'siraj-toolbar-btn', g.bodyEl);
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
				if (spec.menu || spec.mode === 'popover') {
					this._togglePopover(btn, spec);
				} else if (typeof spec.action === 'function') {
					this._closeAll();
					const pressed = !btn.classList.contains('is-active');
					if (spec.mode === 'toggle') {
						btn.classList.toggle('is-active', pressed);
						btn.setAttribute('aria-pressed', pressed ? 'true' : 'false');
					}
					spec.action.call(spec, e);
				}
			});
			this._buttons.set(spec.key || spec.label || spec.icon, btn);
			return btn;
		},

		/* ---------- Popover ---------- */
		_togglePopover(anchor, spec) {
			if (this._current && this._current.anchor === anchor) { this._closeAll(); return; }
			this._closeAll();
			const pop = L.DomUtil.create('div', 'siraj-toolbar-pop', this._container);
			pop.setAttribute('role', 'dialog');
			pop.setAttribute('aria-label', spec.label || '');
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
			// Place popover to the LEFT of the strip when docked right, to the RIGHT when docked left.
			const isRight = this._container.parentElement && this._container.parentElement.classList.contains('leaflet-right');
			pop.style.top = Math.max(8, anchor.offsetTop - this._body.scrollTop + this._header.offsetHeight) + 'px';
			if (isRight) {
				pop.style.right = (this._container.offsetWidth + 6) + 'px';
				pop.style.left = 'auto';
			} else {
				pop.style.left = (this._container.offsetWidth + 6) + 'px';
				pop.style.right = 'auto';
			}
			this._container.appendChild(pop);
			anchor.classList.add('is-open');
			this._current = { anchor, pop };
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

		/* ---------- Header / footer helpers ---------- */
		_makeIconButton(iconName, label, onClick, host) {
			const b = L.DomUtil.create('button', 'siraj-toolbar-head-btn', host || this._header);
			b.type = 'button';
			b.setAttribute('aria-label', label);
			b.title = label;
			b.innerHTML = toolIcon(iconName, label);
			L.DomEvent.on(b, 'click', e => { L.DomEvent.stopPropagation(e); onClick && onClick(e); });
			return b;
		},
		_buildModeSwitcher() {
			const wrap = L.DomUtil.create('div', 'siraj-toolbar-modes', this._footer);
			const groupLabel = L.DomUtil.create('span', 'siraj-toolbar-modes-label', wrap);
			groupLabel.textContent = __('Labels');
			const modes = [
				{ id: 'icons',  icon: 'icon_only', label: __('Icons only') },
				{ id: 'auto',   icon: 'icon_auto', label: __('Auto') },
				{ id: 'labels', icon: 'icon_text', label: __('Icons + text') },
			];
			this._modeBtns = {};
			modes.forEach(m => {
				const b = L.DomUtil.create('button', 'siraj-toolbar-mode-btn', wrap);
				b.type = 'button';
				b.setAttribute('aria-label', m.label);
				b.title = m.label;
				b.dataset.mode = m.id;
				b.innerHTML = toolIcon(m.icon, m.label);
				L.DomEvent.on(b, 'click', e => { L.DomEvent.stopPropagation(e); this.setLabelMode(m.id); });
				this._modeBtns[m.id] = b;
			});
			this._updateModeButtons();
		},
		_updateModeButtons() {
			if (!this._modeBtns) return;
			Object.entries(this._modeBtns).forEach(([id, b]) => b.classList.toggle('is-active', id === this._labelMode));
		},
		_applyMode() {
			if (!this._container) return;
			this._container.classList.remove('siraj-mode-icons', 'siraj-mode-labels', 'siraj-mode-auto');
			this._container.classList.add('siraj-mode-' + this._labelMode);
		},

		/* ---------- Layout (scroll / viewport fit / auto-dense) ---------- */
		_layout() {
			if (!this._container || !this._map) return;
			const mapH = this._map.getSize().y;
			const headH = this._header ? this._header.offsetHeight : 0;
			const footH = this._footer ? this._footer.offsetHeight : 0;
			const statusH = this._statusLine ? this._statusLine.offsetHeight : 0;
			const avail = Math.max(200, mapH - headH - footH - statusH - 24);
			this._body.style.maxHeight = avail + 'px';

			// In 'auto' mode, collapse to icon-only when body's natural content
			// would overflow the available height (i.e. many tools / short map).
			if (this._labelMode === 'auto' && this._body) {
				// Measure: temporarily remove max-height to read natural height.
				const prev = this._body.style.maxHeight;
				this._body.style.maxHeight = 'none';
				const natural = this._body.scrollHeight;
				this._body.style.maxHeight = prev;
				const dense = natural > avail + 2;
				this._container.classList.toggle('siraj-dense', dense);
			} else {
				this._container.classList.remove('siraj-dense');
			}
		},
	});

	L.control.sirajToolbar = options => new L.Control.SirajToolbar(options);
})();
