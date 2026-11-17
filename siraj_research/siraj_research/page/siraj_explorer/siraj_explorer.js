frappe.pages['siraj-explorer'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __('SIRAJ Explorer'), single_column: true });
	new SirajExplorer(page);
};

class SirajExplorer {
	constructor(page) {
		this.page = page;
		this.root = $('<div class="siraj-explorer"></div>').appendTo(page.main);
		this.kind = 'geography';
		this.map = null;
		this.network = null;
		// All type colours/glyphs come from the global registry so every
		// surface (map, graph, deck, lists) stays consistent.
		this.colors = window.sirajColours || {};
		this.render();
	}

	escape(value) { return $('<div>').text(value == null ? '' : String(value)).html(); }
	id(node) { return JSON.stringify([node.doctype, node.name]); }
	t(label) { return this.escape(__(label)); }
	button(text, handler, primary = false) {
		const b = $('<button type="button" class="btn btn-sm"></button>').addClass(primary ? 'btn-primary' : 'btn-default').text(text);
		b.on('click', handler);
		return b;
	}
	async render() {
		if (this.downloadController) { this.downloadController.abort(); this.downloadController = null; }
		if (this.map) { this.map.remove(); this.map = null; }
		if (this.network) { this.network.destroy(); this.network = null; }
		const renderId = this.renderId = (this.renderId || 0) + 1;
		this.root.empty();
		const tabs = $('<div class="sx-tabs"></div>').appendTo(this.root);
		[['geography', __('Geographic map')], ['relationships', __('Relationship map')], ['structures', __('Structures')]].forEach(([key, title]) => {
			this.button(title, () => { this.kind = key; this.render(); }).toggleClass('active', this.kind === key).appendTo(tabs);
		});
		this.tools = $('<div class="sx-tools"></div>').appendTo(this.root);
		this.note = $('<div class="sx-note" role="status"></div>').text(__('Loading…')).appendTo(this.root);
		this.legend = $('<div class="sx-legend"></div>').appendTo(this.root);
		const layout = $('<div class="sx-layout"></div>').toggleClass('sx-layout-geo', this.kind === 'geography').toggleClass('sx-layout-relationships', this.kind === 'relationships').appendTo(this.root);
		this.rail = this.kind === 'relationships' ? $('<aside class="sx-atlas-rail"></aside>').appendTo(layout) : null;
		this.records = this.kind === 'geography' ? $('<aside class="sx-records"></aside>').appendTo(layout) : null;
		this.canvas = $('<div class="sx-canvas"></div>').appendTo(layout);
		this.aside = $('<aside class="sx-aside"></aside>').appendTo(layout);
		try {
			if (this.kind === 'structures') {
				await this.structures(renderId);
			} else if (this.kind === 'geography') {
				// A failing data endpoint must not prevent the local base map loading.
				let data = { points: [], edges: [], truncated: [], unavailable: false };
				try {
					const res = await frappe.call({ method: 'siraj_research.visualization.geographic_data' });
					if (res && res.message && typeof res.message === 'object') {
						data = Object.assign(data, res.message);
					}
					if (!Array.isArray(data.points)) data.points = [];
					if (!Array.isArray(data.edges))  data.edges  = [];
				} catch (error) {
					console.error('[SIRAJ Explorer] geographic_data failed:', error);
					data = { points: [], edges: [], truncated: [], unavailable: true, error: (error && error.exception) || (error && error.message) || String(error) };
				}
				if (renderId === this.renderId) await this.geography(data, renderId);
			} else {
				const res = await frappe.call({ method: 'siraj_research.visualization.relationship_data' });
				if (renderId === this.renderId) await this.relationships(res.message, renderId);
			}
		} catch (error) {
			if (renderId !== this.renderId) return;
			console.error('[SIRAJ Explorer] render failed:', error);
			this.note.addClass('sx-warning')
				.html(
					$('<div></div>').text(__('Unable to load the explorer.')).append(' ')
						.append($('<code style="font-size:11px;opacity:0.8"></code>').text(String((error && error.exception) || (error && error.message) || error)))
				);
			// Keep the layout skeleton intact so the user can retry rather than
			// seeing a crushed column.
			if (this.canvas && !this.canvas.children().length) {
				$('<div class="sx-empty-state"></div>')
					.css({padding:'48px', textAlign:'center', color:'var(--text-muted)'})
					.text(__('Map shell is ready but data failed to load.'))
					.appendTo(this.canvas);
			}
		}
	}
	warning(data) {
		if (data.truncated && (Array.isArray(data.truncated) ? data.truncated.length : data.truncated)) {
			return __('Results are limited to {0} visible records per type; the view is incomplete.', [data.limit]);
		}
		return '';
	}
	showDetails(title, rows, target) {
		this.aside.removeClass('sx-panel-hidden').empty();
		const head = $('<div class="sx-panel-head"></div>').appendTo(this.aside);
		$('<h4 style="margin:0"></h4>').text(title).appendTo(head);
		const actions = $('<div class="sx-panel-actions"></div>').appendTo(head);
		$('<button type="button" class="sx-panel-close"></button>').attr('aria-label', __('Close panel')).html('&times;')
			.on('click', () => { this.aside.addClass('sx-panel-hidden'); })
			.appendTo(actions);
		const body = $('<div class="sx-panel-body"></div>').appendTo(this.aside);
		const sec = $('<details class="sx-section" open="open"></details>').appendTo(body);
		const sum = $('<summary></summary>').appendTo(sec);
		sum.append('<span class="sx-section-caret"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 6 6 6-6 6"/></svg></span>');
		sum.append($('<span class="sx-section-label"></span>').text(title));
		const sbody = $('<div class="sx-section-body"></div>').appendTo(sec);
		const dl = $('<dl></dl>').appendTo(sbody);
		rows.forEach(([label, value]) => {
			if (value === null || value === undefined || value === '') return;
			$('<dt></dt>').text(label).appendTo(dl);
			$('<dd></dd>').text(value).appendTo(dl);
		});
		if (target) $('<div style="margin-top:10px"></div>')
			.append(this.button(__('Open record'), () => frappe.set_route('Form', target.doctype, target.name), true).addClass('btn-primary btn-sm'))
			.appendTo(sbody);
		// Collapsible toggle
		sum.on('click', (ev) => { ev.preventDefault(); sec.attr('open') ? sec.removeAttr('open') : sec.attr('open','open'); });
	}
	showLegend(types, icons = null) {
		types.forEach(type => {
			const item = $('<span class="sx-legend-item"></span>').appendTo(this.legend);
			if (window.sirajIcons && window.sirajIcons.svg) {
				const pin = $('<span class="sx-map-pin sx-legend-pin"></span>').css('background', this.colors[type]).appendTo(item);
				pin.html(window.sirajIcons.svg(type, {size:14}));
			} else if (icons && icons[type]) {
				$('<span class="sx-map-pin sx-legend-pin"></span>').css('background', this.colors[type]).html(icons[type]).appendTo(item);
			} else $('<i class="sx-pin-key"></i>').css('background', this.colors[type]).appendTo(item);
			item.append(document.createTextNode(__(type)));
		});
	}
	filterControls(types, onChange, host = this.tools) {
		const search = $('<input class="form-control input-sm" type="search">').attr('placeholder', __('Search records')).appendTo(host);
		const select = $('<select class="form-control input-sm"></select>').appendTo(host);
		$('<option value=""></option>').text(__('All types')).appendTo(select);
		types.forEach(type => $('<option></option>').val(type).text(__(type)).appendTo(select));
		search.on('input', () => onChange(search.val(), select.val()));
		select.on('change', () => onChange(search.val(), select.val()));
		return {search, select};
	}

	/**
	 * Open a polished "Add relationship" dialog that works from ANY surface
	 * (map, network graph, record panel). Pre-fills subject/object when
	 * supplied so drag-link and right-click flows can jump straight to the
	 * type + direction step. Supports all relatable DocTypes (not just the
	 * original Person/Institution/Place/Event/Source pentad).
	 */
	openAddRelationshipDialog(subject, object, opts = {}) {
		const ENDPOINT_TYPES = ['Person','Institution','Place','Research Event','Source','Military Unit','Operational Deployment'];
		const makeNode = (ref) => ref && ref.doctype && ref.name ? ref : null;
		const subj = makeNode(subject);
		const obj  = makeNode(object);
		const prefType = opts.prefillType || '';

		const fields = [
			{ fieldname:'subject_type', label:__('From type'), fieldtype:'Select',
				options: ENDPOINT_TYPES.join('\n'), reqd:1, default: subj && subj.doctype, read_only: !!subj },
			{ fieldname:'subject', label:__('From'), fieldtype:'Link',
				options: (subj && subj.doctype) || 'Person', reqd:1, default: subj && subj.name, read_only: !!subj },
			{ fieldname:'relationship_type', label:__('Relationship type'), fieldtype:'Link', options:'Relationship Type', reqd:1, default: prefType },
			{ fieldname:'direction', label:__('Direction'), fieldtype:'Select',
				options:'Directed\nSymmetric', default:'Directed' },
			{ fieldname:'object_type', label:__('To type'), fieldtype:'Select',
				options: ENDPOINT_TYPES.join('\n'), reqd:1, default: obj && obj.doctype, read_only: !!obj },
			{ fieldname:'object', label:__('To'), fieldtype:'Link',
				options: (obj && obj.doctype) || 'Person', reqd:1, default: obj && obj.name, read_only: !!obj },
			{ fieldname:'is_current', label:__('Ongoing'), fieldtype:'Check', default:1 },
			{ fieldname:'start_date', label:__('Start date'), fieldtype:'Date' },
			{ fieldname:'end_date', label:__('End date'), fieldtype:'Date' },
			{ fieldname:'description', label:__('Note'), fieldtype:'Small Text' },
		];
		const dlg = new frappe.ui.Dialog({
			title: subj && obj
				? __('Add relationship: {0} → {1}', [subj.label || subj.name, obj.label || obj.name])
				: (subj ? __('Add relationship from {0}', [subj.label || subj.name]) : __('Add relationship')),
			fields,
			primary_action_label: __('Save relationship'),
			primary_action: async vals => {
				try {
					if (!ENDPOINT_TYPES.includes(vals.subject_type) || !ENDPOINT_TYPES.includes(vals.object_type)) {
						frappe.msgprint(__('Invalid endpoint type')); return;
					}
					if (vals.subject === vals.object && vals.subject_type === vals.object_type) {
						frappe.msgprint(__('A record cannot relate to itself.')); return;
					}
					const doc = frappe.model.get_new_doc('Relationship');
					doc.subject_type = vals.subject_type; doc.subject = vals.subject;
					doc.object_type  = vals.object_type;  doc.object  = vals.object;
					doc.relationship_type = vals.relationship_type;
					doc.direction = vals.direction;
					doc.is_current = vals.is_current ? 1 : 0;
					doc.start_date = vals.start_date; doc.end_date = vals.end_date;
					doc.description = vals.description;
					await frappe.call({ method:'frappe.client.insert', args:{doc} });
					frappe.show_alert({ message:__('Relationship created'), indicator:'green' });
					dlg.hide();
					if (typeof opts.onSaved === 'function') opts.onSaved(doc);
				} catch(e) {
					frappe.msgprint(__('Could not save: {0}', [e.message || String(e)]));
				}
			}
		});
		// Wire Link→Options refresh when the type Select changes.
		const wireType = (typeField, linkField) => {
			const tf = dlg.get_field(typeField);
			if (tf && tf.$input) tf.$input.on('change', () => {
				const dt = dlg.get_value(typeField);
				if (dt && dlg.fields_dict[linkField]) {
					dlg.fields_dict[linkField].df.options = dt;
					dlg.fields_dict[linkField].refresh();
				}
			});
		};
		wireType('subject_type','subject');
		wireType('object_type','object');
		dlg.show();
		return dlg;
	}

	/**
	 * Build a searchable multi-select "center on records" combobox.
	 *
	 * Drop-in replacement for the plain <select> that used to list only
	 * Person/Institution. Supports:
	 *   - type-ahead search across label, name, and doctype
	 *   - grouped rendering by DocType with coloured glyphs per item
	 *   - multi-selection (multiple centers = BFS from the union)
	 *   - keyboard nav (arrows / Enter to select / Backspace to remove / Esc)
	 *   - accessible: proper role=combobox/listbox/option, aria-activedescendant,
	 *     translated placeholder/labels, focus management
	 *
	 * items: [{ id, label, sub, doctype }] where id is the stable string id used
	 * in the graph (JSON.stringify([doctype,name])).
	 *
	 * onChange(ids: string[]) called whenever the selection changes.
	 */
	centerPicker(items, onChange, host = this.tools) {
		const PLACEHOLDER = __('Center on a person, place or unit…');
		const I18N = {
			clear: __('Clear centers'),
			count: n => __('{0} selected', [n]),
			noMatches: __('No matches'),
			nMore: n => __('+{0} more', [n]),
		};
		const groupOrder = ['Person', 'Institution', 'Place', 'Military Unit', 'Operational Deployment', 'Research Event', 'Source'];
		const glyph = (doctype, size) => {
			const c = this.colors && this.colors[doctype] ? this.colors[doctype] : '#6a7a7e';
			const s = size || 14;
			const g = (window.sirajIcons && window.sirajIcons.svg)
				? window.sirajIcons.svg(doctype, {size: Math.round(s * 0.7)})
				: '';
			return `<span class="sx-pick-glyph" style="background:${c}">${g}</span>`;
		};

		const wrap = $('<div class="sx-center-picker" role="group" aria-label="' + __('Center on records') + '"></div>').appendTo(host);
		const control = $('<div class="sx-pick-control" tabindex="0"></div>').attr({'aria-haspopup':'listbox','aria-expanded':'false','aria-label': PLACEHOLDER}).appendTo(wrap);
		const tags = $('<span class="sx-pick-tags"></span>').appendTo(control);
		const input = $('<input type="text" class="sx-pick-input" autocomplete="off">').attr('placeholder', PLACEHOLDER).appendTo(control);
		const clearBtn = $('<button type="button" class="sx-pick-clear" aria-label="' + __('Clear centers') + '">&times;</button>').hide().appendTo(control);
		const menu = $('<div class="sx-pick-menu" role="listbox" aria-multiselectable="true" hidden></div>').appendTo(wrap);
		const status = $('<span class="sx-pick-status" aria-live="polite"></span>').appendTo(wrap);

		const selected = new Set();
		let term = '', activeIndex = -1, visibleItems = [];

		const itemById = new Map(items.map(it => [it.id, it]));

		const close = () => {
			menu.attr('hidden', 'hidden');
			control.attr('aria-expanded', 'false');
			activeIndex = -1;
		};
		const open = () => {
			menu.removeAttr('hidden');
			control.attr('aria-expanded', 'true');
			renderMenu();
		};
		const renderTags = () => {
			tags.empty();
			[...selected].slice(0, 4).forEach(id => {
				const it = itemById.get(id);
				if (!it) return;
				const tag = $('<span class="sx-pick-tag"></span>')
					.attr('data-id', id)
					.append(glyph(it.doctype, 12))
					.append($('<span class="sx-pick-tag-label"></span>').text(it.label))
					.appendTo(tags);
				$('<button type="button" class="sx-pick-tag-x" aria-label="' + __('Remove {0}', [it.label]) + '">&times;</button>')
					.on('click', e => { e.stopPropagation(); selected.delete(id); renderTags(); fire(); input.focus(); })
					.appendTo(tag);
			});
			if (selected.size > 4) {
				$('<span class="sx-pick-more"></span>').text(I18N.nMore(selected.size - 4)).appendTo(tags);
			}
			clearBtn.toggle(selected.size > 0);
			input.attr('placeholder', selected.size ? '' : PLACEHOLDER);
			status.text(selected.size ? I18N.count(selected.size) : '');
		};
		const fire = () => {
			renderTags();
			onChange([...selected]);
		};

		const renderMenu = () => {
			const q = term.trim().toLocaleLowerCase();
			const filtered = q
				? items.filter(it => (it.label + ' ' + (it.sub || '') + ' ' + it.doctype).toLocaleLowerCase().includes(q))
				: items;
			// Group filtered items by doctype, stable order.
			const groups = new Map();
			filtered.forEach(it => {
				if (!groups.has(it.doctype)) groups.set(it.doctype, []);
				groups.get(it.doctype).push(it);
			});
			menu.empty();
			visibleItems = [];
			const order = [...groupOrder.filter(t => groups.has(t)), ...[...groups.keys()].filter(t => !groupOrder.includes(t))];
			order.forEach(dt => {
				const grp = $('<div class="sx-pick-group" role="group"></div>').attr('aria-label', __(dt)).appendTo(menu);
				$('<div class="sx-pick-group-label"></div>').html(glyph(dt, 12) + '<span>' + __(dt) + '</span>').appendTo(grp);
				const list = $('<div class="sx-pick-list"></div>').appendTo(grp);
				groups.get(dt).slice(0, 50).forEach(it => {
					visibleItems.push(it.id);
					const opt = $('<div class="sx-pick-option" role="option"></div>')
						.attr({
							'data-id': it.id,
							'aria-selected': selected.has(it.id) ? 'true' : 'false',
							'id': 'sx-pick-opt-' + visibleItems.length,
							tabindex: '-1',
						})
						.append(glyph(it.doctype, 16))
						.append($('<span class="sx-pick-opt-main"></span>')
							.append($('<span class="sx-pick-opt-label"></span>').text(it.label))
							.append(it.sub ? $('<span class="sx-pick-opt-sub"></span>').text(it.sub) : [])
						)
						.append($('<span class="sx-pick-opt-check" aria-hidden="true"></span>').html(selected.has(it.id) ? '&#10003;' : ''))
						.on('click', e => {
							e.stopPropagation();
							toggle(it.id);
							input.focus();
						})
						.on('mouseenter', () => setActive(visibleItems.indexOf(it.id)))
						.appendTo(list);
				});
			});
			if (!visibleItems.length) {
				$('<div class="sx-pick-empty"></div>').text(I18N.noMatches).appendTo(menu);
			}
			if (activeIndex < 0 || activeIndex >= visibleItems.length) activeIndex = visibleItems.length ? 0 : -1;
			highlight();
		};
		const highlight = () => {
			menu.find('.sx-pick-option').removeClass('is-active').removeAttr('aria-selected');
			menu.find('.sx-pick-option').each(function () {
				const id = $(this).attr('data-id');
				$(this).attr('aria-selected', selected.has(id) ? 'true' : 'false');
			});
			if (activeIndex >= 0 && visibleItems[activeIndex]) {
				const el = menu.find('.sx-pick-option[data-id="' + cssEscape(visibleItems[activeIndex]) + '"]');
				el.addClass('is-active');
				control.attr('aria-activedescendant', el.attr('id'));
				// scroll into view if needed
				const top = el.position().top - menu.position().top;
				if (top < 0 || top + el.outerHeight() > menu.innerHeight()) {
					menu.scrollTop(menu.scrollTop() + top - (menu.innerHeight() - el.outerHeight()) / 2);
				}
			} else {
				control.removeAttr('aria-activedescendant');
			}
		};
		const cssEscape = s => String(s).replace(/([ #;?&,.+*~':"!^$[\]()=>|/@])/g, '\\$1');
		const setActive = idx => { activeIndex = idx; highlight(); };
		const toggle = id => {
			if (selected.has(id)) selected.delete(id); else selected.add(id);
			fire();
			renderMenu();
		};

		input.on('input', () => { term = input.val(); open(); activeIndex = 0; });
		input.on('focus', () => { if (menu.attr('hidden')) open(); });
		input.on('keydown', e => {
			if (e.key === 'ArrowDown') { e.preventDefault(); open(); if (activeIndex < visibleItems.length - 1) setActive(activeIndex + 1); }
			else if (e.key === 'ArrowUp') { e.preventDefault(); if (activeIndex > 0) setActive(activeIndex - 1); }
			else if (e.key === 'Enter') {
				e.preventDefault();
				if (activeIndex >= 0 && visibleItems[activeIndex]) toggle(visibleItems[activeIndex]);
			} else if (e.key === 'Backspace' && term === '' && selected.size) {
				const last = [...selected].pop();
				selected.delete(last); fire(); renderMenu();
			} else if (e.key === 'Escape') { e.preventDefault(); close(); }
		});
		control.on('click', () => input.focus());
		clearBtn.on('click', e => { e.stopPropagation(); selected.clear(); fire(); renderMenu(); input.focus(); });
		$(document).on('mousedown.sxPick' + (window.__sxPickSeq = (window.__sxPickSeq||0)+1), e => {
			if (!wrap[0].contains(e.target)) close();
		});

		// Public API
		return {
			wrap,
			get: () => [...selected],
			set: ids => {
				selected.clear();
				(ids || []).filter(id => itemById.has(id)).forEach(id => selected.add(id));
				fire();
				if (menu.is(':visible')) renderMenu();
			},
			addItem: it => { if (!itemById.has(it.id)) { items.push(it); itemById.set(it.id, it); if (menu.is(':visible')) renderMenu(); } },
		};
	}
	async geography(data, renderId) {
		// Explicitly require shared map assets here. In page contexts (like
		// /app/siraj-explorer) app_include_js load order is not guaranteed to
		// have completed by the time page JS runs, so we list them explicitly.
		await frappe.require([
			'/assets/siraj_research/vendor/leaflet/leaflet.css',
			'/assets/siraj_research/vendor/leaflet/leaflet.js',
			'/assets/siraj_research/vendor/leaflet-markercluster/leaflet.markercluster.js',
			'/assets/siraj_research/vendor/topojson/topojson-client.min.js',
			'/assets/siraj_research/js/siraj-map-kit.js',
			'/assets/siraj_research/js/siraj-map-toolbar.js',
			'/assets/siraj_research/css/siraj-map-toolbar.css',
			'/assets/siraj_research/css/siraj-icons.css',
			'/assets/siraj_research/css/siraj_explorer.css',
		]);
		if (renderId !== this.renderId) return;
		const Kit = window.SirajMapKit;
		const map = this.map = L.map(this.canvas[0], { worldCopyJump: true, preferCanvas: true, minZoom: 0, maxZoom: 22, zoomAnimation: false, zoomControl: false }).setView([33.3152, 44.3661], 4);
		L.control.scale({ imperial: false, position: 'bottomleft' }).addTo(map);
		const dms = (value, latitude) => {
			const n = Number(value), tenths = Math.round(Math.abs(n) * 36000);
			const d = Math.floor(tenths/36000), m = Math.floor((tenths%36000)/600), s = ((tenths%600)/10).toFixed(1);
			return d + '° ' + m + '′ ' + s + '″ ' + (latitude ? (n<0?'S':'N') : (n<0?'W':'E'));
		};
		const mapStatus = (text, warn) => {
			if (this.toolbar) this.toolbar.status(text, warn ? 'warning' : null);
			if (this.note) this.note.text(text).toggleClass('sx-warning', !!warn);
		};
		let offlineLayer = null, onlineLayer = null, localPackLayer = null, selectedCircle = null;
		// Basemap
		try {
			const response = await fetch('/assets/siraj_research/vendor/world-atlas/countries-110m.json');
			if (!response.ok) throw new Error('offline basemap HTTP ' + response.status);
			const world = await response.json();
			if (renderId !== this.renderId) return;
			offlineLayer = L.geoJSON(topojson.feature(world, world.objects.countries), {
				interactive: false, style: { color:'#a4b4a8', weight:0.7, fillColor:'#e8e4cf', fillOpacity:1 }
			}).addTo(map);
			map.attributionControl.addAttribution('Natural Earth / world-atlas');
			mapStatus(__('Offline basemap: Natural Earth, low detail.'));
		} catch (err) {
			console.error(err);
			if (renderId !== this.renderId) return;
			mapStatus(__('Local basemap could not be loaded. You can still use the markers or enable online tiles.'), true);
		}
		// Icons
		const pointIcon = p => L.divIcon({
			className: 'sx-pin-wrapper', iconSize:[36,36], iconAnchor:[18,18],
			html: window.sirajIcons.pin(p.doctype, this.colors[p.doctype], 36)
		});
		const itemGlyph = (doctype, size) => {
			const c = this.colors[doctype] || '#6a7a7e';
			const s = size || 12;
			const pad = Math.ceil(s/3);
			const g = (window.sirajIcons && window.sirajIcons.svg) ? window.sirajIcons.svg(doctype, {size: Math.round(s*0.7)}) : '';
			return `<span class="sx-item-glyph" style="background:${c};width:${s+pad}px;height:${s+pad}px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;color:#fff">${g}</span>`;
		};
		const types = [...new Set(data.points.map(p => p.doctype))];
		this.showLegend(types, window.sirajIcons ? window.sirajIcons.types : null);
		let clustered = true, overlayEnabled = false, currentPoints = [], listLimit = 100;
		const pointsById = new Map();
		data.points.forEach(p => pointsById.set(this.id(p), p));

		// Geography uses a two-column grid (full-width canvas + details aside),
		// hiding the legacy sx-records left column since records now live in the
		// in-map app panel. The previous 3-column grid with a hidden column was
		// leaving a 220px crushed gap (S4).
		this.root.find('.sx-layout').addClass('sx-no-records').removeClass('sx-no-details');
		if (this.records) this.records.hide();
		// ------ App panel (records + filters + export) — overlay over the map canvas ------
		const appPanel = $('<div class="sx-app-panel"></div>');

		// --- Shared filter state (SirajFilters) ---
		const Filters = window.SirajFilters;
		// One-time migration: strip any stale "#sf=..." hash left by the earlier
		// buggy build so the page loads instead of "Page not found".
		if (Filters.migrateLegacyHash) Filters.migrateLegacyHash();
		const FILTER_PAGE = 'siraj-explorer.geography';
		let filterState = Filters.initialState(types, FILTER_PAGE);
		const filterStore = Filters.createStore(filterState);
		const recSection = $('<div class="sx-app-section"></div>').appendTo(appPanel);
		const recordHeading = $('<h5></h5>').text(__('Mapped records')).appendTo(recSection);
		const activeFilterBar = $('<div class="siraj-filter-bar" style="font-size:11px;color:var(--text-muted);margin-bottom:4px"></div>').appendTo(recSection);
		const searchBox = $('<input type="search" class="form-control input-sm" style="width:100%;box-sizing:border-box;margin-bottom:6px" placeholder="' + __('Search records') + '" aria-label="' + __('Search records') + '">').appendTo(recSection);
		const presetRow = $('<div class="siraj-preset-row" style="display:flex;gap:4px;flex-wrap:wrap;margin-bottom:6px"></div>').appendTo(recSection);
		const chipRow = $('<div class="siraj-chip-row" style="display:flex;gap:4px;flex-wrap:wrap;margin-bottom:6px"></div>').appendTo(recSection);
		const chipActions = $('<div style="display:flex;gap:4px;margin-bottom:6px;font-size:11px"></div>').appendTo(recSection);
		const recordList = $('<div></div>').css({maxHeight:'30vh',overflow:'auto'}).appendTo(recSection);
		const listMore = this.button(__('Show more'), () => { listLimit += 100; renderList(); }).appendTo(recSection);

		const renderFilters = () => {
			const st = filterStore.get();
			presetRow.empty();
			Filters.BUILTIN_PRESETS.forEach(p => {
				const btn = $('<button type="button" class="btn btn-xs"></button>')
					.addClass(st.activePreset === p.id ? 'btn-primary' : 'btn-default')
					.text(__(p.label)).on('click', () => filterStore.dispatch({type:'APPLY_PRESET', id:p.id}));
				presetRow.append(btn);
			});
			chipRow.empty();
			const counts = Filters.countByType(data.points);
			types.forEach(t => {
				const on = Filters.isTypeVisible(st, t);
				const color = this.colors[t] || '#6a7a7e';
				const chip = $('<button type="button" class="siraj-chip"></button>')
					.toggleClass('is-on', on).attr('aria-pressed', on?'true':'false')
					.css({'--chip-color': color}).attr('title', __(t) + ' · ' + (counts[t]||0))
					.html('<span class="siraj-chip-swatch" style="background:'+color+'"></span>'
						+ '<span class="siraj-chip-glyph">'+(window.sirajIcons?window.sirajIcons.svg(t,{size:12}):'')+'</span>'
						+ '<span class="siraj-chip-label">'+__(t)+'</span>'
						+ '<span class="siraj-chip-count">'+(counts[t]||0)+'</span>')
					.on('click', () => filterStore.dispatch({type:'TOGGLE_TYPE', doctype:t}));
				chipRow.append(chip);
			});
			chipActions.empty();
			$('<button type="button" class="btn btn-link btn-xs"></button>').text(__('All')).on('click',()=>filterStore.dispatch({type:'SELECT_ALL_TYPES'})).appendTo(chipActions);
			$('<button type="button" class="btn btn-link btn-xs"></button>').text(__('None')).on('click',()=>filterStore.dispatch({type:'SELECT_NONE_TYPES'})).appendTo(chipActions);
			$('<button type="button" class="btn btn-link btn-xs"></button>').text(__('Invert')).on('click',()=>filterStore.dispatch({type:'INVERT_TYPES'})).appendTo(chipActions);
			const connectors = $('<label style="margin-inline-start:auto;display:flex;align-items:center;gap:4px"><input type="checkbox">' + __('Keep connectors') + '</label>').appendTo(chipActions);
			connectors.find('input').prop('checked', !!st.includeHiddenConnectors).on('change', e => filterStore.dispatch({type:'TOGGLE_HIDDEN_CONNECTORS'}));
			const vt = Filters.visibleTypeCount(st);
			const tot = Filters.typeCount(st);
			const visibleCount = currentPoints.length;
			activeFilterBar.text(
				vt === tot
					? __('Showing all {0} types · {1} records', [tot, visibleCount])
					: __('Showing {0} of {1} types · {2} records', [vt, tot, visibleCount])
			);
			// Persist to localStorage only (never to location.hash — Frappe router owns it).
			try { Filters.saveState(st, FILTER_PAGE); } catch(_) {}
		};
		searchBox.on('input', () => { filterStore.dispatch({type:'SET_SEARCH', value: searchBox.val()}); });

		const dataSection = $('<div class="sx-app-section"></div>').appendTo(appPanel);
		$('<h5></h5>').text(__('Data')).appendTo(dataSection);
		const exportBtn = this.button(__('Export GeoJSON'), () => {
			const visible = currentPoints;
			const geojson = { type:'FeatureCollection', features: visible.map(p => ({
				type:'Feature', geometry:{ type:'Point', coordinates:[Number(p.longitude),Number(p.latitude)] },
				properties:{ doctype:p.doctype, name:p.name, label:p.label, precision:p.geo_precision, method:p.geocoding_method, uncertainty_m:p.geo_uncertainty_m, source:p.geometry_source }
			})) };
			const url = URL.createObjectURL(new Blob([JSON.stringify(geojson)],{type:'application/geo+json'}));
			const a = document.createElement('a'); a.href=url; a.download='siraj-visible-points.geojson'; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
		}).appendTo(dataSection);
		appPanel.appendTo(this.canvas);
		// Close button so the panel can be dismissed.
		$('<button type="button" class="close" style="position:absolute;top:6px;right:8px" aria-label="' + __('Close panel') + '">×</button>').prependTo(appPanel).on('click', () => appPanel.hide());

		// --- Selection + ego network state ---
		let selectedNode = null;        // currently selected record {doctype,name,label,...}
		const selectionTrail = [];      // back-breadcrumb trail
		let egoDepth = 1;
		let egoData = null;             // last network response
		let egoEdgesLayer = L.featureGroup().addTo(map);
		let egoNodesLayer = L.featureGroup().addTo(map);
		let egoLoading = false, egoRequestSeq = 0;
		let isolateSelected = false;
		const clearSelectionVisuals = () => {
			egoEdgesLayer.clearLayers(); egoNodesLayer.clearLayers();
			if (selectedCircle) { map.removeLayer(selectedCircle); selectedCircle=null; }
		};
		const egoMarker = (node, extra) => {
			const dt = node.doctype, color = this.colors[dt] || '#6a7a7e';
			const inferred = node.location_source && String(node.location_source).startsWith('inferred');
			const size = node.hops === 0 ? 38 : (node.hops === 1 ? 32 : 26);
			const ring = inferred ? `<span class="siraj-pin-halo-ring" style="position:absolute;inset:-4px;border:2px dashed ${color};border-radius:50%;opacity:.7"></span>` : '';
			const halo = node.hops === 0 ? `<span class="siraj-pin-pulse" style="position:absolute;inset:-8px;border:2px solid ${color};border-radius:50%;opacity:.6;animation:siraj-pulse 1.6s ease-out infinite"></span>` : '';
			const glyphHTML = (window.sirajIcons && window.sirajIcons.svg) ? window.sirajIcons.svg(dt, {size:Math.round(size*0.58)}) : '';
			const html = `<span class="sx-map-pin siraj-pin" data-doctype="${dt}" style="position:relative;background:${color};width:${size}px;height:${size}px;${node.hops===0?'box-shadow:0 0 0 4px '+color+'33, 0 2px 8px #263c4066':''}">${glyphHTML}${ring}${halo}</span>`;
			const icon = L.divIcon({ className:'sx-pin-wrapper', iconSize:[size,size], iconAnchor:[size/2,size/2], html });
			const m = L.marker([Number(node.latitude),Number(node.longitude)],{icon,interactive:true});
			if (extra && extra.restricted) m.setOpacity(0.4);
			return m;
		};
		const styleDim = on => { markers.eachLayer(l => { const el = l.getElement && l.getElement(); if (el) el.style.opacity = (on && selectedNode && isolateSelected) ? '0.25' : ''; }); };
		const renderEgo = () => {
			egoEdgesLayer.clearLayers(); egoNodesLayer.clearLayers();
			if (!selectedNode || !egoData) return;
			const nodeMap = new Map(egoData.nodes.map(n => [this.id(n), n]));
			egoData.edges.forEach(e => {
				const a = nodeMap.get(this.id({doctype:e.source[0],name:e.source[1]})),
					  b = nodeMap.get(this.id({doctype:e.target[0],name:e.target[1]}));
				if (!a || !b || a.latitude == null || b.latitude == null) return;
				const meta = (egoData.types && egoData.types[e.type]) || {};
				const isDirected = meta.is_symmetric === false;
				const A = [Number(a.latitude),Number(a.longitude)], B = [Number(b.latitude),Number(b.longitude)];
				const pairKey = [this.id(a),this.id(b)].sort().join('|');
				// Parallel edge offset — count duplicates of this pair
				const parallels = egoData.edges.filter(x => [this.id({doctype:x.source[0],name:x.source[1]}),this.id({doctype:x.target[0],name:x.target[1]})].sort().join('|') === pairKey);
				const idx = parallels.indexOf(e);
				const ctrl = parallels.length > 1 ? (window.SirajGraph ? window.SirajGraph.offsetEdge({lat:A[0],lng:A[1]},{lat:B[0],lng:B[1]},idx,parallels.length) : null) : null;
				const latlngs = ctrl ? [A, [ctrl.lat, ctrl.lng], B] : [A,B];
				const line = L.polyline(latlngs,{
					color: meta.color || '#536b78',
					weight: e.type ? 2.5 : 1.8,
					opacity: a.restricted || b.restricted ? 0.4 : 0.8,
					dashArray: isDirected ? null : '6 5',
					interactive:true,
				});
				line.bindTooltip(
					(e.type || __('Relationship')) + (meta.is_symmetric===false ? ' ' + __('(directed)') : '') + (a.label?' · '+a.label+' → '+b.label:''),
					{sticky:true,direction:'top',className:'siraj-edge-tooltip'});
				line.on('click', () => {
					this.showDetails(e.type || __('Relationship'),[
						[__('Subject'), a.restricted ? __('Restricted') : (a.label||'')],
						[__('Object'),  b.restricted ? __('Restricted') : (b.label||'')],
						[__('Direction'), e.direction],[__('Start'),e.start_date],[__('End'),e.end_date],[__('Description'),e.description],
					], {doctype:'Relationship', name:e.name});
				});
				egoEdgesLayer.addLayer(line);
				// Arrowhead for directed edges.
				if (isDirected) {
					const tip = B, tail = ctrl ? [ctrl.lat,ctrl.lng] : A;
					const arrow = L.polygon([tip,
						window.SirajMapKit.Geodesic.destination({lat:tip[0],lng:tip[1]}, window.SirajMapKit.Geodesic.bearing({lat:tail[0],lng:tail[1]},{lat:tip[0],lng:tip[1]})+150, Math.max(8, 40)),
						window.SirajMapKit.Geodesic.destination({lat:tip[0],lng:tip[1]}, window.SirajMapKit.Geodesic.bearing({lat:tail[0],lng:tail[1]},{lat:tip[0],lng:tip[1]})-150, Math.max(8, 40)),
					],{color:meta.color||'#536b78',fillColor:meta.color||'#536b78',fillOpacity:0.9,weight:0,interactive:false});
					egoEdgesLayer.addLayer(arrow);
				}
			});
			// Add inferred/unmapped node markers (distinct from the main cluster markers).
			egoData.nodes.forEach(n => {
				if (n.restricted) return;
				if (n.latitude == null || n.longitude == null) return;
				// Skip the selected node itself (already has a marker in the cluster layer).
				if (selectedNode && n.doctype === selectedNode.doctype && n.name === selectedNode.name) return;
				const m = egoMarker(n).addTo(egoNodesLayer);
				m.on('click', () => selectNode(n));
			});
			// Uncertainty circle on center.
			if (selectedNode) {
				const r = Number(selectedNode.geo_uncertainty_m);
				if (Number.isFinite(r) && r>0 && r<=1000000) {
					selectedCircle = L.circle([Number(selectedNode.latitude),Number(selectedNode.longitude)],{radius:r,color:this.colors[selectedNode.doctype],fillOpacity:0.1,interactive:false}).addTo(map);
				}
				styleDim(true);
			}
		};
		// Thin wrapper around the Explorer-level dialog; busts the local map caches
		// after a successful save so the new edge appears on the map.
		const addRelationship = (counterpart) => {
			this.openAddRelationshipDialog(selectedNode, counterpart, {
				onSaved: () => { relData = null; egoData = null; loadEgo(egoDepth); }
			});
		};
		const loadEgo = async (depth) => {
			if (!selectedNode) return;
			egoDepth = depth;
			egoLoading = true;
			const seq = ++egoRequestSeq;
			const statusText = {1:__('Direct connections'),2:__('Two hops'),3:__('Three hops')}[depth] || '';
			mapStatus(__('Loading {0}…',[statusText]));
			try {
				const res = await frappe.call({ method:'siraj_research.api.map_relations.get_entity_network',
					args:{ doctype:selectedNode.doctype, name:selectedNode.name, depth, limit_nodes:400, limit_edges:600 } });
				if (seq !== egoRequestSeq) return;
				egoData = res.message || {nodes:[],edges:[],unmapped:[],truncated:false,types:{}};
				// Register type colours with RelLayer.
				Object.entries(egoData.types || {}).forEach(([t,meta]) => this.relLayer.registerType(t, meta.color || '#53706b', meta.is_symmetric ? null : '6 4'));
				// Also merge any unmapped nodes into the details panel listing.
				renderEgo();
				renderDetails();
				// Fit bounds to union of selected + visible ego nodes.
				const pts = [[Number(selectedNode.latitude),Number(selectedNode.longitude)]];
				egoData.nodes.forEach(n => { if (n.latitude!=null && !n.restricted) pts.push([Number(n.latitude),Number(n.longitude)]); });
				if (pts.length > 1) map.fitBounds(L.latLngBounds(pts).pad(0.2),{maxZoom:13});
				mapStatus(egoData.truncated ? __('Showing {0} connections (capped). Refine with type filters.', [egoData.edges.length]) : __('Showing {0} connections.', [egoData.edges.length]));
			} catch(e) {
				if (seq !== egoRequestSeq) return;
				console.error('[SIRAJ] ego network failed:', e);
				mapStatus(__('Could not load connections: {0}',[e.message || String(e)]), true);
				frappe.log_error && frappe.log_error({message: e && e.stack});
			} finally {
				if (seq === egoRequestSeq) egoLoading = false;
			}
		};
		const selectNode = p => {
			if (!p) { clearSelection(); return; }
			clearSelectionVisuals();
			if (selectedNode) selectionTrail.push({doctype:selectedNode.doctype, name:selectedNode.name, label:selectedNode.label});
			selectedNode = p;
			pointsById.set(this.id(p), p);
			markers.eachLayer(m => {
				// Bring matching marker to front; no-op for now.
			});
			map.panTo([Number(p.latitude),Number(p.longitude)]);
			loadEgo(egoDepth);
		};
		const clearSelection = () => {
			selectedNode = null;
			egoData = null;
			clearSelectionVisuals();
			styleDim(false);
			$(document).off('keydown.sxPanel');
			this.showDetails(__('Geographic map'),[[__('About this view'),__('Map tools are docked on the right edge. Click a pin to see its connections.')]]);
			mapStatus('');
			// Deactivate toggle buttons.
			isolateSelected = false;
			this.toolbar.find('button[data-siraj-key=sel_isolate]').removeClass('is-active btn-primary').addClass('btn-default');
		};
		// Format a single field value returned by get_entity_profile.
		const fmtProfileValue = v => {
			if (v == null) return '';
			if (typeof v === 'object' && v.type === 'link') return v.title + ' (' + __(v.doctype) + ')';
			if (typeof v === 'object' && v.type === 'attach') return v.url;
			return String(v);
		};
		const renderValueCell = (v, dt, name) => {
			if (v == null) return '';
			if (typeof v === 'object' && v.type === 'link' && !v.restricted) {
				const b = $('<button type="button" class="btn btn-link btn-xs" style="padding:0"></button>').text(v.title);
				b.on('click', () => {
					// Fly to counterpart if mapped; otherwise open form.
					const key = this.id({doctype:v.doctype, name:v.name});
					const n = pointsById.get(key);
					if (n && n.latitude != null) selectNode(n);
					else frappe.set_route('Form', v.doctype, v.name);
				});
				return b;
			}
			return document.createTextNode(fmtProfileValue(v));
		};
		let profileReqSeq = 0;
		/* ---------- Persistent panel state (per record, per user) ---------- */
		const PANEL_STATE_KEY = (dt, nm) => 'siraj.panel.v1.' + dt + '.' + encodeURIComponent(nm);
		const loadPanelState = (dt, nm) => {
			try { return JSON.parse(localStorage.getItem(PANEL_STATE_KEY(dt, nm)) || '{}'); } catch(_) { return {}; }
		};
		const savePanelState = (dt, nm, st) => {
			try { localStorage.setItem(PANEL_STATE_KEY(dt, nm), JSON.stringify(st)); } catch(_) {}
		};
		const CARET_SVG = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 6 6 6-6 6"/></svg>';

		const renderDetails = async () => {
			if (!selectedNode) return;
			const p = selectedNode;
			const pState = Object.assign({ tab: 'overview', sections: {} }, loadPanelState(p.doctype, p.name));

			this.aside.removeClass('sx-panel-hidden').empty();

			/* ---------- Header ---------- */
			const head = $('<div class="sx-panel-head"></div>').appendTo(this.aside);
			const title = $('<div class="sx-panel-title"></div>').appendTo(head);
			title.append(itemGlyph(p.doctype, 28));
			$('<h4></h4>').attr('title', p.label || p.name).text(p.label || p.name).appendTo(title);
			$('<span class="sx-type-chip"></span>').text(__(p.doctype)).appendTo(title);
			const actions = $('<div class="sx-panel-actions"></div>').appendTo(head);
			$('<button type="button" class="btn btn-link btn-sm"></button>')
				.text(__('Open record'))
				.on('click', () => frappe.set_route('Form', p.doctype, p.name))
				.appendTo(actions);
			$('<button type="button" class="sx-panel-close"></button>').attr('aria-label', __('Close details')).html('&times;')
				.on('click', () => clearSelection())
				.appendTo(actions);

			/* ---------- Toolbar row: back button ---------- */
			if (selectionTrail.length) {
				const tb = $('<div class="sx-panel-toolbar"></div>').appendTo(this.aside);
				$('<button type="button" class="btn btn-xs btn-default sx-back-btn"></button>')
					.html('&larr; ' + __('Back'))
					.on('click', () => {
						const prev = selectionTrail.pop();
						const n = pointsById.get(this.id(prev));
						if (n) selectNode(n); else { selectionTrail.length = 0; clearSelection(); }
					}).appendTo(tb);
			}

			/* ---------- Tab bar ---------- */
			const TABS = [
				{ id:'overview',    label: __('Overview')    },
				{ id:'fields',      label: __('Fields')      },
				{ id:'connections', label: __('Connections') },
				{ id:'location',    label: __('Location')    },
				{ id:'activity',    label: __('Activity')    },
			];
			const tabBar = $('<div class="sx-panel-tabs" role="tablist"></div>').appendTo(this.aside);
			const tabBody = $('<div class="sx-panel-body" role="tabpanel"></div>').appendTo(this.aside);

			const switchTab = (id) => {
				pState.tab = id; savePanelState(p.doctype, p.name, pState);
				tabBar.find('button').removeClass('btn-primary').addClass('btn-default').attr('aria-selected','false');
				tabBar.find('button[data-tab="'+id+'"]').removeClass('btn-default').addClass('btn-primary').attr('aria-selected','true');
				renderTab(id);
			};
			TABS.forEach(t => $('<button type="button" class="btn btn-xs" role="tab"></button>')
				.addClass(pState.tab===t.id?'btn-primary':'btn-default')
				.attr({'data-tab':t.id, 'aria-selected': pState.tab===t.id ? 'true':'false'})
				.html(t.label + '<span class="sx-tab-badge" data-tab-badge="'+t.id+'"></span>')
				.on('click', () => switchTab(t.id))
				.appendTo(tabBar));

			/* ---------- Ego depth row (always visible below tabs) ---------- */
			const egoRow = $('<div class="sx-ego-row"></div>').appendTo(this.aside);
			$('<small></small>').text(__('Network depth')).appendTo(egoRow);
			[1,2,3].forEach(d => $('<button type="button" class="btn btn-xs"></button>')
				.addClass(d===egoDepth?'btn-primary':'btn-default').text(String(d))
				.on('click', (e) => {
					egoRow.find('button.depth').removeClass('btn-primary').addClass('btn-default');
					$(e.currentTarget).removeClass('btn-default').addClass('btn-primary');
					loadEgo(d);
				}).addClass('depth').appendTo(egoRow));
			$('<span class="sx-spacer"></span>').appendTo(egoRow);
			const isoBtn = $('<button type="button" class="btn btn-xs"></button>')
				.addClass(isolateSelected?'btn-primary':'btn-default')
				.text(__('Isolate'))
				.on('click', (e) => {
					isolateSelected = !isolateSelected;
					$(e.currentTarget).toggleClass('btn-primary', isolateSelected).toggleClass('btn-default', !isolateSelected);
					if (selectedNode) renderEgo();
				}).appendTo(egoRow);

			/* ---------- Collapsible section builder ---------- */
			// key identifies the section inside a tab; sections that don't have a
			// stored open/closed state default to open.
			const section = (tabId, key, titleHTML, countNode) => {
				const secKey = tabId + ':' + key;
				const stored = pState.sections[secKey];
				const isOpen = stored == null ? true : !!stored;
				const sec = $('<details class="sx-section"></details>').attr('data-sx-section', secKey);
				if (isOpen) sec.attr('open','open');
				const sum = $('<summary></summary>').appendTo(sec);
				sum.append($('<span class="sx-section-caret">' + CARET_SVG + '</span>'));
				const lbl = $('<span class="sx-section-label"></span>');
				if (typeof titleHTML === 'string') lbl.html(titleHTML); else lbl.append(titleHTML);
				sum.append(lbl);
				if (countNode != null) {
					const c = $('<span class="sx-section-count"></span>');
					if (typeof countNode === 'function') c.data('__fill', countNode);
					else c.text(String(countNode));
					sum.append(c);
				}
				const body = $('<div class="sx-section-body"></div>').appendTo(sec);
				sum.on('click', (ev) => {
					ev.preventDefault();
					const opening = !sec.attr('open');
					if (opening) sec.attr('open','open'); else sec.removeAttr('open');
					pState.sections[secKey] = opening;
					savePanelState(p.doctype, p.name, pState);
				});
				return sec;
			};
			const setBadge = (tabId, text) => {
				const b = tabBar.find('.sx-tab-badge[data-tab-badge="'+tabId+'"]');
				if (text == null || text === '' || text === 0) { b.text('').hide(); }
				else b.text(String(text)).show();
			};

			/* ---------- Tab loader (lazy, cached for the session) ---------- */
			const tabCache = {};
			const setTabCount = (id, n) => setBadge(id, n);
			const renderTab = (id) => {
				tabBody.empty();
				if (tabCache[id]) { mountTab(id, tabCache[id]); return; }
				const loading = $('<div class="sx-panel-loading"></div>')
					.html('<span>⏳</span> ' + __('Loading…'))
					.appendTo(tabBody);
				const seq = ++profileReqSeq;
				frappe.call({ method:'siraj_research.api.entity_profile.get_entity_profile',
					args:{ doctype:p.doctype, name:p.name } })
					.then(r => {
						if (seq !== profileReqSeq || !selectedNode || selectedNode.name !== p.name) return;
						tabCache[id] = r.message || {};
						mountTab(id, tabCache[id]);
					})
					.catch(e => {
						if (seq !== profileReqSeq) return;
						tabBody.empty();
						const err = $('<div class="sx-panel-error"></div>').appendTo(tabBody);
						$('<div></div>').text(__('Could not load details: {0}', [e.message || String(e)])).appendTo(err);
						$('<button type="button" class="btn btn-xs btn-default"></button>')
							.text(__('Retry'))
							.on('click', () => { delete tabCache[id]; renderTab(id); })
							.appendTo(err);
					});
			};

			/* When one tab finishes loading we cache the payload but also prime
			 * the other tabs' caches (the endpoint returns everything at once). */
			const primeCache = (prof) => {
				TABS.forEach(t => { if (!tabCache[t.id]) tabCache[t.id] = prof; });
			};

			const mountTab = (id, prof) => {
				tabBody.empty();
				if (!prof) return;
				primeCache(prof);
				const pane = $('<div class="sx-tab-pane" data-tab-pane="'+id+'"></div>').appendTo(tabBody);

				if (id === 'overview') {
					// Core metadata section (status/modified/owner)
					const metaRows = [];
					if (prof.header && prof.header.status) metaRows.push([__('Status'), prof.header.status]);
					metaRows.push([__('Modified'), prof.header && prof.header.modified]);
					metaRows.push([__('Owner'), prof.header && prof.header.owner]);
					if (prof.permissions) {
						const perms = [];
						if (prof.permissions.can_write)  perms.push(__('can edit'));
						if (prof.permissions.can_create) perms.push(__('can link'));
						if (perms.length) metaRows.push([__('Permissions'), perms.join(', ')]);
					}
					const sec = section('overview', 'meta', __('Record details'), null).appendTo(pane);
					const dl = $('<dl></dl>').appendTo(sec.find('.sx-section-body'));
					metaRows.forEach(([k,v]) => {
						if (v == null || v === '') return;
						$('<dt></dt>').text(k).appendTo(dl);
						$('<dd></dd>').text(String(v)).appendTo(dl);
					});

					// Network summary
					const ns = prof.network_summary || {};
					const sumChips = [
						{ label: __('Relationships'), n: ns.relationship_count || 0, color:'#53706b' },
						{ label: __('Outbound'),      n: ns.outbound_count     || 0, color:'#6a7a7e' },
					{ label: __('Inbound'),       n: ns.inbound_count      || 0, color:'#6a7a7e' },
				];
				const nsSec = section('overview','network',__('Network summary'), ()=>String((ns.relationship_count||0)+(ns.outbound_count||0)+(ns.inbound_count||0))).appendTo(pane);
					const chipRow = $('<div class="sx-chip-row"></div>').appendTo(nsSec.find('.sx-section-body'));
					sumChips.forEach(c => $('<span class="siraj-chip is-on" style="--chip-color:'+c.color+'"></span>')
						.html('<span class="siraj-chip-label">'+c.label+'</span><span class="siraj-chip-count">'+c.n+'</span>')
						.appendTo(chipRow));

					// Quick actions
					if (prof.permissions && prof.permissions.can_create) {
						const act = section('overview', 'actions', __('Quick actions'), null).appendTo(pane);
						$('<div style="display:flex;gap:6px;flex-wrap:wrap"></div>')
							.append(this.button(__('Add relationship…'), () => addRelationship(null)).addClass('btn-primary btn-sm'))
							.appendTo(act.find('.sx-section-body'));
					}

				} else if (id === 'fields') {
					let fieldCount = 0;
					(prof.sections||[]).forEach(secDef => {
						const fields = secDef.fields || [];
						if (!fields.length) return;
						fieldCount += fields.length;
						const sec = section('fields', 'fld_'+secDef.heading, secDef.heading || __('Fields'), String(fields.length)).appendTo(pane);
						const body = sec.find('.sx-section-body');
						const dl = $('<dl></dl>').appendTo(body);
						fields.forEach(f => {
							$('<dt></dt>').text(f.label).appendTo(dl);
							$('<dd></dd>').append(renderValueCell(f.value)).appendTo(dl);
						});
					});
					// Child tables
					Object.entries(prof.children||{}).forEach(([fn, tbl]) => {
						if (!tbl.rows || !tbl.rows.length) return;
						const total = tbl.total || tbl.rows.length;
						const label = tbl.label + (tbl.truncated ? ' (' + __('showing {0} of {1}', [tbl.rows.length, total]) + ')' : '');
						const sec = section('fields', 'ctbl_'+fn, label, String(total)).appendTo(pane);
						const body = sec.find('.sx-section-body');
						const keys = Object.keys(tbl.rows[0]);
						const wrap = $('<div class="sx-table-wrap"></div>').appendTo(body);
						const t = $('<table class="table table-condensed"></table>').appendTo(wrap);
						const thead = $('<thead></thead>').appendTo(t), trh=$('<tr></tr>').appendTo(thead);
						keys.forEach(k => $('<th></th>').text(tbl.rows[0][k].label).appendTo(trh));
						const tbody = $('<tbody></tbody>').appendTo(t);
						tbl.rows.forEach(row => {
							const tr=$('<tr></tr>').appendTo(tbody);
							keys.forEach(k => $('<td></td>').text(fmtProfileValue(row[k].value)).appendTo(tr));
						});
						if (tbl.truncated) {
							$('<button type="button" class="btn btn-link btn-xs sx-show-all"></button>')
								.text(__('Open full record →'))
								.on('click', () => frappe.set_route('Form', p.doctype, p.name))
								.appendTo(body);
						}
					});
					if (!fieldCount && (!prof.children || !Object.keys(prof.children).length)) {
						$('<div class="sx-empty"></div>').text(__('No field data available.')).appendTo(pane);
					}
					setTabCount('fields', fieldCount || null);

				} else if (id === 'connections') {
					const rels = (prof.connections && prof.connections.relationships) || [];
					const ob   = (prof.connections && prof.connections.outbound_links)  || [];
					const ib   = (prof.connections && prof.connections.inbound_links)   || [];
					const unm  = (egoData && egoData.unmapped) || [];

					// Authored relationships — always show an inline "+" in the section header
					// so the add button appears IN CONTEXT of the selected entity rather
					// than floating at the top of the panel.
					const relSec = section('connections','rels',__('Relationships'), String(rels.length)).appendTo(pane);
					// "+ Add" lives inside the <summary> so it sits alongside the
					// section title (context of the clicked record, not the panel top).
					const relHeader = relSec.find('summary');
					if (prof.permissions && prof.permissions.can_create) {
						$('<button type="button" class="btn btn-primary btn-xs sx-rel-add" aria-label="' + __('Add relationship from this record') + '" onclick="event.preventDefault();event.stopPropagation();">+ ' + __('Add') + '</button>')
							.on('click', ev => { ev.preventDefault(); ev.stopPropagation(); addRelationship(null); })
							.appendTo(relHeader);
					}
					if (!rels.length) {
						$('<div class="sx-empty"></div>').text(__('No authored relationships. Use + Add to create one from this record.')).appendTo(relSec.find('.sx-section-body'));
					} else {
						const list = $('<ul class="sx-conn-list"></ul>').appendTo(relSec.find('.sx-section-body'));
						const showAll = $('<button type="button" class="btn btn-link btn-xs sx-show-all" style="display:none"></button>')
							.text(__('Show all'))
							.on('click', () => { list.removeClass('sx-collapsed'); showAll.hide(); })
							.appendTo(relSec.find('.sx-section-body'));
						rels.slice(0,50).forEach((r, i) => {
							if (i === 8 && rels.length > 8) { list.addClass('sx-collapsed'); showAll.show(); }
							const row = $('<li class="sx-conn"></li>').appendTo(list);
							const dirGlyph = r.direction_relative === 'outbound' ? '→' : (r.direction_relative === 'inbound' ? '←' : '↔');
							$('<span class="sx-conn-dir"></span>').text(dirGlyph).appendTo(row);
							row.append(itemGlyph(r.counterpart_doctype, 16));
							const lbl = $('<button type="button" class="sx-conn-name"></button>')
								.text(r.counterpart_title + (r.relationship_type ? ' · ' + r.relationship_type : ''))
								.attr('title', r.counterpart_title + (r.relationship_type ? ' · ' + r.relationship_type : ''))
								.on('click', () => {
									if (r.counterpart_restricted) return;
									const key = this.id({doctype:r.counterpart_doctype, name:r.counterpart_name});
									const n = pointsById.get(key);
									if (n && n.latitude != null) selectNode(n);
									else frappe.set_route('Form', r.counterpart_doctype, r.counterpart_name);
								}).appendTo(row);
							$('<span class="sx-conn-meta"></span>').text(r.start_date || '').appendTo(row);
						});
						if (prof.permissions && prof.permissions.can_create) {
							$('<button type="button" class="btn btn-primary btn-xs" style="margin-top:6px"></button>')
								.text(__('Add relationship…'))
								.on('click', () => addRelationship(null))
								.appendTo(relSec.find('.sx-section-body'));
						}
					}

					// Outbound links
					if (ob.length) {
						const obSec = section('connections','out',__('Outbound links'), String(ob.length)).appendTo(pane);
						const list = $('<ul class="sx-conn-list"></ul>').appendTo(obSec.find('.sx-section-body'));
						ob.forEach(l => {
							const row = $('<li class="sx-conn"></li>').appendTo(list);
							row.append(itemGlyph(l.doctype, 14));
							$('<span class="sx-conn-meta" style="margin-inline-start:0"></span>').text(l.label).appendTo(row);
							const b = $('<button type="button" class="sx-conn-name"></button>').text(l.title).appendTo(row);
							b.on('click', () => { if (l.restricted) return; frappe.set_route('Form', l.doctype, l.name); });
						});
					}

					// Inbound links
					if (ib.length) {
						const ibSec = section('connections','in',__('Inbound links'), String(ib.length)).appendTo(pane);
						const body = ibSec.find('.sx-section-body');
						ib.forEach(l => {
							const row = $('<div style="display:flex;align-items:center;gap:6px;padding:4px 0;font-size:12px"></div>').appendTo(body);
							if (l.restricted) { $('<span class="sx-empty"></span>').text(__('{0}: restricted', [__(l.doctype)])).appendTo(row); return; }
							$('<span class="siraj-chip is-on" style="--chip-color:#6a7a7e"></span>')
								.html('<span class="siraj-chip-label">'+__(l.doctype)+'</span><span class="siraj-chip-count">'+(l.count||0)+'</span>')
								.appendTo(row);
							if (l.sample && l.sample.length) {
								$('<span style="color:var(--text-muted);font-size:11px;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"></span>')
									.text(l.sample.map(s=>s.title).join(', '))
									.appendTo(row);
							}
							$('<button type="button" class="btn btn-link btn-xs"></button>')
								.text(__('View all'))
								.on('click', ()=>frappe.set_route('List', l.doctype))
								.appendTo(row);
						});
					}

					// Unmapped connections
					if (unm.length) {
						const umSec = section('connections','unmapped',__('Unmapped connections'), String(unm.length)).appendTo(pane);
						const body = umSec.find('.sx-section-body');
						unm.slice(0,20).forEach(u => {
							const r = $('<div style="display:flex;align-items:center;gap:6px;padding:3px 0;font-size:12px"></div>').appendTo(body);
							r.append(itemGlyph(u.doctype,16));
							$('<span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"></span>')
								.text(u.label + ' (' + __(u.doctype) + ')').appendTo(r);
							this.button(__('Place'), () => {
								const meas = measure; if (!meas || !meas.activate) return; meas.activate('pick');
								meas.onPick = latlng => {
									frappe.new_doc(u.doctype, {latitude:Number(latlng.lat).toFixed(6), longitude:Number(latlng.lng).toFixed(6), geocoding_method:'map_pick'});
									meas.onPick = null;
								};
								frappe.show_alert({message:__('Click the map to place {0}', [u.label]), indicator:'blue'});
							}).addClass('btn-xs btn-default').appendTo(r);
						});
					}
					setTabCount('connections', String(rels.length + ob.length + ib.length + unm.length));

				} else if (id === 'location') {
					const loc = prof.location || {};
					const rows = [];
					[['latitude',__('Latitude')],['longitude',__('Longitude')],['precision',__('Precision')],['method',__('Method')],['uncertainty_m',__('Uncertainty (m)')],['source',__('Source')],['location_source',__('Provenance')]].forEach(([k,label]) => {
						if (loc[k] == null || loc[k] === '') return;
						rows.push([label, String(loc[k])]);
					});
					const hasCoords = loc.latitude != null && loc.longitude != null;
					const lSec = section('location', 'coords', __('Coordinates'), hasCoords ? '✓' : null).appendTo(pane);
					if (!rows.length) {
						$('<div class="sx-empty"></div>').text(__('No coordinates on this record.')).appendTo(lSec.find('.sx-section-body'));
					} else {
						const dl = $('<dl></dl>').appendTo(lSec.find('.sx-section-body'));
						rows.forEach(([k,v]) => { $('<dt></dt>').text(k).appendTo(dl); $('<dd></dd>').text(v).appendTo(dl); });
					}
					if (hasCoords) {
						$('<div style="margin-top:8px"></div>').append(
							this.button(__('Fly to'), () => map.flyTo([Number(loc.latitude), Number(loc.longitude)], 14)).addClass('btn-xs btn-default')
						).appendTo(lSec.find('.sx-section-body'));
					} else {
						$('<div style="margin-top:8px"></div>').append(
							this.button(__('Place on map'), () => {
								const meas = measure; if (!meas || !meas.activate) return; meas.activate('pick');
								meas.onPick = latlng => {
									frappe.call({ method:'frappe.client.set_value', args: {
										doctype:p.doctype, name:p.name, fieldname:{latitude:Number(latlng.lat).toFixed(6), longitude:Number(latlng.lng).toFixed(6), geocoding_method:'map_pick'}
									} }).then(() => { delete tabCache.location; renderTab('location'); meas.onPick=null; meas.deactivate && meas.deactivate(); });
								};
								frappe.show_alert({message:__('Click the map to place {0}', [p.label || p.name]), indicator:'blue'});
							}).addClass('btn-xs btn-default')
						).appendTo(lSec.find('.sx-section-body'));
					}

				} else if (id === 'activity') {
					const a = prof.activity || {};
					const atts = a.attachments || [];
					const comments = a.comments || [];
					const versions = a.versions || [];
					if (atts.length) {
						const s = section('activity','atts',__('Attachments'), String(atts.length)).appendTo(pane);
						const list = $('<ul class="sx-conn-list"></ul>').appendTo(s.find('.sx-section-body'));
						atts.forEach(f => $('<li class="sx-conn"></li>').append(
							$('<a target="_blank" rel="noopener" class="sx-conn-name" style="padding:0"></a>')
								.attr('href', f.file_url || '').text(f.file_name || f.name)
						).appendTo(list));
					}
					if (comments.length) {
						const s = section('activity','cmt',__('Comments'), String(comments.length)).appendTo(pane);
						const body = s.find('.sx-section-body');
						comments.forEach(c => $('<div style="font-size:12px;padding:4px 0;border-bottom:1px dashed var(--sx-line,#d4dfe0)"></div>')
							.text((c.comment_by || c.comment_email || '') + ' · ' + String(c.content||'').replace(/<[^>]+>/g,''))
							.appendTo(body));
					}
					if (versions.length) {
						const s = section('activity','ver',__('Recent changes'), String(versions.length)).appendTo(pane);
						const body = s.find('.sx-section-body');
						versions.slice(0,30).forEach(v => $('<div style="font-size:12px;padding:2px 0;color:var(--text-muted)"></div>')
							.text((v.owner||'') + ' · ' + v.creation)
							.appendTo(body));
					}
					if (!atts.length && !comments.length && !versions.length) {
						$('<div class="sx-empty"></div>').text(__('No activity recorded.')).appendTo(pane);
					}
					setTabCount('activity', String(atts.length + comments.length + versions.length));
				}

				// Add relationship button at the bottom of every tab
				if (prof.permissions && prof.permissions.can_create && id !== 'connections') {
					$('<div style="margin-top:10px"></div>')
						.append(this.button(__('Add relationship…'), () => addRelationship(null)).addClass('btn-primary btn-sm btn-block'))
						.appendTo(pane);
				}
			};

			switchTab(pState.tab);

			// Keyboard: Esc closes the panel (same as the × button)
			const onKey = (e) => {
				if (e.key === 'Escape' && selectedNode && selectedNode.name === p.name) {
					// Only close if focus isn't inside an input/textarea.
					const tag = (document.activeElement && document.activeElement.tagName) || '';
					if (!/INPUT|TEXTAREA|SELECT/.test(tag)) clearSelection();
				}
			};
			$(document).off('keydown.sxPanel').on('keydown.sxPanel', onKey);
		};
		const selectPoint = selectNode; // backward alias used by markers/renderList
		const renderList = () => {
			recordHeading.text(__('Mapped records ({0})',[currentPoints.length]));
			recordList.empty();
			currentPoints.slice(0, listLimit).forEach(p => {
				const b = $('<button type="button"></button>').on('click', () => {
					selectPoint(p); map.panTo([Number(p.latitude),Number(p.longitude)]);
				}).appendTo(recordList);
				b.addClass('sx-record-item').attr('title',__(p.doctype)+' · '+p.name)
					.html(itemGlyph(p.doctype) + '<span class="sx-item-label">' + this.escape(p.label) + '</span>'
						+ '<span class="sx-item-type" style="margin-inline-start:auto;font-size:10px;color:var(--text-muted);padding:2px 6px;border-radius:999px;background:'+this.colors[p.doctype]+';color:#fff;opacity:0.85">'+__(p.doctype)+'</span>');
			});
			listMore.toggle(currentPoints.length > listLimit);
		};

		// Relationship overlay (shared RelLayer).
		let relData = null;
		this.relLayer = new Kit.RelLayer(map, { pointsById });
		this.relLayer.onEdgeClick = edge => {
			const a = pointsById.get(JSON.stringify(edge.source)), b = pointsById.get(JSON.stringify(edge.target));
			this.showDetails(edge.type || __('Relationship'), [
				[__('Subject'), a ? a.label : JSON.stringify(edge.source)],
				[__('Object'),  b ? b.label : JSON.stringify(edge.target)],
				[__('Direction'), edge.direction],[__('Description'), edge.description],[__('Status'), edge.state],
			], {doctype:'Relationship', name:edge.name});
		};
		const ensureRelData = async () => {
			if (relData) return relData;
			relData = (await frappe.call({method:'siraj_research.visualization.relationship_data'})).message;
			this.relLayer.setEdges(relData.edges || []);
			relData.edges.forEach(e => { if (e.type) this.relLayer.registerType(e.type, this.colors.Relationship || '#53706b', null); });
			return relData;
		};

		// Marker cluster layer
		let markers = L.markerClusterGroup({
			maxClusterRadius:45, showCoverageOnHover:false, spiderfyOnMaxZoom:true,
			iconCreateFunction: c => L.divIcon({className:'sx-cluster', html:'<span>'+c.getChildCount()+'</span>', iconSize:[40,40]})
		}).addTo(map);
		const draw = () => {
			if (selectedCircle && !selectedNode) { map.removeLayer(selectedCircle); selectedCircle=null; }
			markers.clearLayers();
			const st = filterStore.get();
			// Provenance filter: only hide records whose location_source is explicitly 'unmapped' when includeUnlocated is off.
			currentPoints = data.points.filter(p => {
				if (!Filters.isTypeVisible(st, p.doctype)) return false;
				if (!Filters.matchesSearch(st, (p.label||'')+' '+(p.name||''))) return false;
				if (!st.includeUnlocated && p.location_source === 'unmapped') return false;
				const prov = p.location_source || 'direct';
				if (!st.provenance.direct && prov === 'direct') return false;
				if (!st.provenance.inferred && String(prov).startsWith('inferred')) return false;
				return true;
			});
			currentPoints.forEach(p => {
				const m = L.marker([Number(p.latitude),Number(p.longitude)],{icon:pointIcon(p),title:p.label,keyboard:true});
				m.bindTooltip(this.escape(p.label));
				m.on('click', () => selectPoint(p));
				markers.addLayer(m);
			});
			pointsById.clear();
			currentPoints.forEach(p => pointsById.set(this.id(p), p));
			// Also include ego nodes in pointsById if loaded (so clicks on ego-only nodes resolve).
			if (egoData) egoData.nodes.forEach(n => { if (n.latitude != null) pointsById.set(this.id(n), n); });
			const text = data.unavailable ? __('Record data could not be loaded.') : __('Showing {0} record points.',[currentPoints.length]) + ' ' + this.warning(data);
			this.note.toggleClass('sx-warning',!!data.unavailable).text(text);
			renderList();
			renderFilters();
			if (this.relLayer && this.relLayer.redraw) this.relLayer.redraw();
		};
		filterStore.subscribe(() => { listLimit = 100; draw(); });

		// ------ Measurement tool (shared state machine, single-click model) ------
		const measure = new Kit.MeasureTool(map, { onStatus: mapStatus });

		// ------ Pick-to-link flow ------
		const startPick = () => {
			mapStatus(__('Click a point to link it to an existing or new record.'));
			measure.onPick = async latlng => {
				measure.onPick = null;
				const dlg = new frappe.ui.Dialog({
					title: __('Link a record to this point'),
					fields: [
						{ fieldname:'doctype', label:__('Record type'), fieldtype:'Select', options:types.join('\n'), reqd:1 },
						{ fieldname:'target',  label:__('Record'),      fieldtype:'Link',   options:'Person', depends_on:'eval:doc.doctype', reqd:1,
						  description: __('Leave blank to create a new record after saving.') },
						{ fieldname:'note',    label:__('Note'),        fieldtype:'Small Text' },
					],
					primary_action_label: __('Set coordinates'),
					primary_action: async vals => {
						if (!vals.doctype) return;
						if (vals.target) {
							try {
								await frappe.call({ method:'frappe.client.set_value', args: {
									doctype: vals.doctype, name: vals.target,
									fieldname: { latitude: Number(latlng.lat).toFixed(6), longitude: Number(latlng.lng).toFixed(6), geocoding_method:'map_pick' }
								}});
								frappe.show_alert({message:__('Coordinates updated for {0}',[vals.target]), indicator:'green'});
								dlg.hide();
								draw();
							} catch (e) { frappe.msgprint(__('Could not update: ') + (e.message||e)); }
						} else {
							frappe.new_doc(vals.doctype, { latitude: Number(latlng.lat).toFixed(6), longitude: Number(latlng.lng).toFixed(6), geocoding_method:'map_pick' });
							dlg.hide();
						}
					}
				});
				// Update the Link field's options when doctype changes.
				dlg.fields_dict.doctype.$input.on('change', () => {
					const dt = dlg.get_value('doctype');
					if (dt && dlg.fields_dict.target) {
						dlg.fields_dict.target.df.options = dt;
						dlg.fields_dict.target.refresh();
					}
				});
				dlg.show();
				// Display the clicked point temporarily so the user sees what they picked.
				L.circleMarker(latlng,{radius:6,color:'#1a6670',weight:2,fillColor:'#1a6670',fillOpacity:0.4}).addTo(map).bindTooltip(dms(latlng.lat,true)+' · '+dms(latlng.lng,false)).openTooltip();
			};
			measure.activate('pick');
		};

		// ------ In-map toolbar (MAP TOOLS ONLY) ------
		this.toolbar = L.control.sirajToolbar({ position:'topright' }).addTo(map);
		const localPacks = new Map();
		const toggleBtn = (key, on) => { const b=this.toolbar._buttons && this.toolbar._buttons.get(key); if (b) b.classList.toggle('is-active',!!on); };

		// Navigate
		this.toolbar.group(__('Navigate'))
			.add({ icon:'zoom_in',   label:__('Zoom in'),    key:'nav_in',    tooltip:__('Zoom in'),    hotkey:'+', action: () => map.zoomIn() })
			.add({ icon:'zoom_out',  label:__('Zoom out'),   key:'nav_out',   tooltip:__('Zoom out'),   hotkey:'-', action: () => map.zoomOut() })
			.add({ icon:'home',      label:__('Reset view'), key:'nav_home',  tooltip:__('Home view'),  hotkey:'H', action: () => map.setView([33.3152,44.3661],4) })
			.add({ icon:'fit',       label:__('Fit to data'),key:'nav_fit',   tooltip:__('Fit data to view'), hotkey:'F', action: () => {
				if (currentPoints.length) map.fitBounds(L.latLngBounds(currentPoints.map(p=>[Number(p.latitude),Number(p.longitude)])).pad(0.15),{maxZoom:12});
			}})
			.add({ icon:'locate_me', label:__('My location'),key:'nav_me',    tooltip:__('My location'),hotkey:'M', action: () => map.locate({setView:true,maxZoom:12,enableHighAccuracy:true}) })
			.add({ icon:'locate',    label:__('Go to coordinates'),key:'nav_goto',tooltip:__('Go to coordinates'),hotkey:'G', mode:'popover', menuTitle:__('Go to coordinates'), menu: pop => {
				const w=$('<div></div>').appendTo(pop);
				const row=$('<div style="display:flex;gap:4px"></div>').appendTo(w);
				const lat=$('<input type="number" step="any" min="-90" max="90" class="form-control input-sm" placeholder="'+__('Lat')+'">').appendTo(row);
				const lon=$('<input type="number" step="any" min="-180" max="180" class="form-control input-sm" placeholder="'+__('Lon')+'">').appendTo(row);
				$('<button type="button" class="btn btn-sm btn-primary" style="margin-top:4px">'+__('Go')+'</button>').appendTo(w).on('click',()=>{
					const la=Number(lat.val()),lo=Number(lon.val());
					if (![la,lo].every(Number.isFinite)||Math.abs(la)>90||Math.abs(lo)>180) return;
					map.setView([la,lo],Math.max(8,map.getZoom()));
				});
			}});

		// Basemap
		const selectBasemap = val => {
			if (onlineLayer) { map.removeLayer(onlineLayer); onlineLayer=null; }
			if (localPackLayer) { map.removeLayer(localPackLayer); localPackLayer=null; }
			map.setMinZoom(0);
			const pack = localPacks.get(String(val).replace(/^pack-/,''));
			if (pack) {
				if (offlineLayer) map.removeLayer(offlineLayer);
				map.setMinZoom(pack.minzoom);
				localPackLayer = L.tileLayer('/api/method/siraj_research.local_maps.tile?kind='+encodeURIComponent(pack.kind)+'&z={z}&x={x}&y={y}',{minZoom:pack.minzoom,maxZoom:22,maxNativeZoom:pack.maxzoom,attribution:pack.attribution||''}).addTo(map);
				localPackLayer.on('tileerror',()=>mapStatus(__('Some local tiles are unavailable.'),true));
			} else if (val==='online') {
				if (offlineLayer) map.removeLayer(offlineLayer);
				onlineLayer = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:22,maxNativeZoom:19,attribution:'&copy; OpenStreetMap contributors'}).addTo(map);
				mapStatus(__('Online tiles disclose your IP to OpenStreetMap.'));
			} else {
				if (offlineLayer) offlineLayer.addTo(map).bringToBack();
			}
		};
		this.toolbar.group(__('Basemap'))
			.add({ icon:'layers', label:__('Basemap'), key:'basemap', tooltip:__('Basemap'), hotkey:'B', mode:'popover', menuTitle:__('Basemap'), menu: pop => {
				const w=$('<div></div>').appendTo(pop);
				const opt=(val,icon,label,active)=>{
					const b=$('<button type="button" class="siraj-toolbar-opt"></button>').html(window.sirajIcons.toolSvg(icon,{size:16})+'<span>'+label+'</span>');
					if (active) b.addClass('is-active');
					b.on('click',()=>{w.find('.is-active').removeClass('is-active');b.addClass('is-active');selectBasemap(val);});
					b.appendTo(w); return b;
				};
				opt('local','offline',__('Offline'),true);
				opt('online','online',__('Online: OSM'),false);
				$('<hr>').appendTo(w);
				frappe.call({method:'siraj_research.local_maps.available_packs',type:'GET',silent:true}).then(res=>{
					if (!Array.isArray(res.message)) return;
					res.message.forEach(pack=>{
						if (pack.unavailable||!['standard','aerial'].includes(pack.kind)) return;
						localPacks.set(pack.kind,pack);
						opt('pack-'+pack.kind,'layers',pack.kind==='aerial'?__('Local aerial'):__('Local standard'),false);
					});
				}).catch(()=>{});
			}});
		this.toolbar.separator();

		// Measure group
		this.toolbar.group(__('Measure'))
			.add({ icon:'ruler',   label:__('Measure distance'), key:'measure_dist', tooltip:__('Distance'), hotkey:'D', action: () => measure.activate('distance') })
			.add({ icon:'area',    label:__('Measure area'),     key:'measure_area', tooltip:__('Area'),     hotkey:'A', action: () => measure.activate('area') })
			.add({ icon:'radius',  label:__('Measure radius'),   key:'measure_rad',  tooltip:__('Radius'),   hotkey:'R', action: () => measure.activate('radius') })
			.add({ icon:'bearing', label:__('Measure bearing'),  key:'measure_brg',  tooltip:__('Bearing'),  hotkey:'Y', action: () => measure.activate('bearing') })
			.add({ icon:'clear',   label:__('Clear measurements'),key:'measure_clear',tooltip:__('Clear measurement'), hotkey:'C', action: () => measure.clear() });
		this.toolbar.separator();

		// Pick
		this.toolbar.group(__('Pick'))
			.add({ icon:'pick', label:__('Pick point to link'), key:'pick', tooltip:__('Pick a point to link a record'), hotkey:'P', action: startPick });
		this.toolbar.separator();

		// Overlays (toggles)
		this.toolbar.group(__('Overlays'))
			.add({ icon:'cluster', label:__('Marker clusters'), key:'clusters', tooltip:__('Cluster markers'), hotkey:'K', mode:'toggle', active:true, action: function() {
				clustered=!clustered; this.toolbar.setActive('clusters',clustered);
				map.removeLayer(markers);
				markers = clustered
					? L.markerClusterGroup({maxClusterRadius:45,showCoverageOnHover:false,spiderfyOnMaxZoom:true,iconCreateFunction:c=>L.divIcon({className:'sx-cluster',html:'<span>'+c.getChildCount()+'</span>',iconSize:[40,40]})})
					: L.featureGroup();
				markers.addTo(map); draw();
			}.bind(this)})
			.add({ icon:'lines', label:__('Relationship lines'), key:'rel_lines', tooltip:__('Relationship lines'), hotkey:'L', mode:'toggle', action: async function() {
				const btn=$(this);
				if (overlayEnabled) { overlayEnabled=false; map.removeLayer(this.relLayer.layer); this.toolbar.setActive('rel_lines',false); return; }
				btn.prop('disabled',true);
				try { await ensureRelData(); overlayEnabled=true; this.relLayer.layer.addTo(map); this.toolbar.setActive('rel_lines',true); draw(); }
				catch { mapStatus(__('Unable to load relationship lines.'),true); }
				finally { btn.prop('disabled',false); }
			}.bind(this)});

		// Selection group (shown in dock; actions act on the selected entity).
		const selGroup = this.toolbar.group(__('Selection'));
		selGroup.add({ icon:'ego',      label:__('Show connections'),  key:'sel_ego',     tooltip:__('Show connections of selected'), hotkey:'S', action: () => { if (!selectedNode) { mapStatus(__('Select a record first.'),true); return; } loadEgo(egoDepth); }});
		selGroup.add({ icon:'isolate',  label:__('Isolate selection'), key:'sel_isolate', tooltip:__('Isolate selection'), hotkey:'I', mode:'toggle', active:false, action: function() { isolateSelected=!isolateSelected; this.toolbar.setActive('sel_isolate',isolateSelected); if(selectedNode) renderEgo(); }.bind(this) });
		selGroup.add({ icon:'link_add', label:__('Add relationship'),  key:'link_add',    tooltip:__('Add relationship to selected'), hotkey:'N', action: () => { if(!selectedNode){mapStatus(__('Select a record first.'),true);return;} addRelationship(null); }});
		selGroup.add({ icon:'back',     label:__('Back'),              key:'sel_back',    tooltip:__('Back to previous selection'), hotkey:'Backspace', action: function() { if (selectionTrail.length) { const prev = selectionTrail.pop(); const n = pointsById.get(this.id(prev)); if(n) selectNode(n); else { selectionTrail.length=0; clearSelection(); } } else clearSelection(); }.bind(this) });
		selGroup.add({ icon:'eraser',   label:__('Clear selection'),   key:'sel_clear',   tooltip:__('Clear selection'), hotkey:'Esc', action: clearSelection });

		// Toolbar visibility toggle + help.
		const tbarGroup = this.toolbar.group(__('Toolbar'));
		tbarGroup.add({ icon:'panel_left', label:__('Hide toolbar'), key:'toolbar_toggle', tooltip:__('Show/hide toolbar'), hotkey:'\\', action: function() {
			const visible = this.toolbar.toggle();
			$(this).toggleClass('is-active', !visible);
			mapStatus(visible ? '' : __('Toolbar hidden — press \\ to show.'));
		}.bind(this)});

		// Help / hotkeys button (generated from TOOL_SPEC — single source of truth).
		const helpGroup = this.toolbar.group(__('Help'));
		helpGroup.add({ icon:'help', label:__('Help & hotkeys'), key:'help', tooltip:__('Help & hotkeys'), mode:'popover', action: function() {
			if (!Kit.helpOverlay) return;
			const node = Kit.helpOverlay();
			const dlg = new frappe.ui.Dialog({ title: __('Map tools & hotkeys'), primary_action_label: __('Close'), primary_action: () => dlg.hide() });
			$(dlg.body).append(node);
			dlg.show();
		}});

		// Hotkey handler (driven by TOOL_SPEC hotkey field).
		const HOTKEY_MAP = {};
		(Kit.TOOL_SPEC||[]).forEach(spec => { if (spec.hotkey && spec.key) HOTKEY_MAP[String(spec.hotkey).toLowerCase()] = spec.key; });
		const self = this;
		L.DomEvent.on(document, 'keydown', function(e) {
			if (e.target && /INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) return;
			const k = e.key;
			const code = k === 'Escape' ? 'esc' : k === 'Enter' ? 'enter' : k === 'Backspace' ? 'backspace' : k.toLowerCase();
			const target = HOTKEY_MAP[code];
			if (!target) return;
			e.preventDefault();
			switch (target) {
				case 'sel_clear': clearSelection(); break;
				case 'sel_back': if (selectionTrail.length) { const prev = selectionTrail.pop(); const n = pointsById.get(self.id(prev)); if(n) selectNode(n); else clearSelection(); } break;
				case 'sel_isolate': isolateSelected=!isolateSelected; if(selectedNode) renderEgo(); break;
				case 'sel_ego': if(selectedNode) loadEgo(egoDepth); break;
				case 'sel_depth1': if(selectedNode) loadEgo(1); break;
				case 'sel_depth2': if(selectedNode) loadEgo(2); break;
				case 'sel_depth3': if(selectedNode) loadEgo(3); break;
				case 'link_add': if(selectedNode) addRelationship(null); else mapStatus(__('Select a record first.'),true); break;
				case 'sel_open': if(selectedNode) frappe.set_route('Form', selectedNode.doctype, selectedNode.name); break;
			}
		});

		// Empty the legacy top strip (we now use appPanel + in-canvas dock).
		this.tools.empty();

		draw();
		this.showDetails(__('Geographic map'), [[__('About this view'),__('Map tools (navigate, basemap, measure, pick, overlays, selection) live in the dock on the right edge of the map. Records, filters, and export live in the panel at the upper left. Press ? or the Help button for the full hotkey list.')]]);
		if (currentPoints.length) map.fitBounds(L.latLngBounds(currentPoints.map(p=>[Number(p.latitude),Number(p.longitude)])).pad(0.15),{maxZoom:12});
		setTimeout(()=>map.invalidateSize(),0);
	}
	async relationships(data, renderId) {
		await frappe.require(['/assets/siraj_research/vendor/vis-network/vis-network.min.js', '/assets/siraj_research/css/siraj_explorer.css']);
		if (renderId !== this.renderId) return;
		this.canvas.addClass('sx-graph');
		const types = [...new Set(data.nodes.map(n => n.doctype))];
		this.showLegend(types);
		const all = new Map(data.nodes.map(n => [this.id(n), n]));
		const edgeLookup = new Map(data.edges.map(e => [e.name, e]));
		const nodeSet = new vis.DataSet();
		const edgeSet = new vis.DataSet();
		let currentEdges = [], currentNodes = [], history = [], trail = [], currentId = null, centerIds = [];
		let searchTerm = '', selectedType = '', edgeType = '', hideEnded = false, evidenceOnly = false, evidenceLoaded = false, layout = 'force', maxDistance = 1;
		let centerButton, resetButton;

		// Build a unified pool of "centerable" records covering all four map-capable
		// core types plus other relatable endpoints so users can centre on any
		// person, place, institution, or unit (and deployments/events/sources that
		// appear as relationship endpoints).
		const CENTERABLE_TYPES = ['Person', 'Institution', 'Place', 'Military Unit', 'Operational Deployment', 'Research Event', 'Source'];
		const centerItems = data.nodes
			.filter(n => CENTERABLE_TYPES.indexOf(n.doctype) >= 0)
			.map(n => ({ id: this.id(n), label: n.label, sub: n.name, doctype: n.doctype }))
			.sort((a, b) => a.label.localeCompare(b.label));
		const graphHost = $('<div class="sx-graph-host"></div>').appendTo(this.canvas);
		const matrixHost = $('<div class="sx-atlas-matrix"></div>').hide().appendTo(this.canvas);
		// Generate a data-URI for each doctype so the network shows the same
		// glyph+colour that appears on map pins, list avatars, and form pills.
		const nodeImageCache = new Map();
		const nodeImage = doctype => {
			if (nodeImageCache.has(doctype)) return nodeImageCache.get(doctype);
			const colour = this.colors[doctype] || '#6a7a7e';
			// Use the server/boot GLYPH strings directly (just path/circle fragments
			// on a 24×24 grid), so we can draw them white inside a coloured disc.
			const meta = (window.sirajRecordMeta && window.sirajRecordMeta.glyphs) ? window.sirajRecordMeta.glyphs[doctype] : null;
			const glyphPaths = meta || (window.sirajIcons && window.sirajIcons.types[doctype] && window.sirajIcons.types[doctype].replace
				? window.sirajIcons.types[doctype]
				: '<path d="M6 3h9l3 3v15H6Z"/><path d="M9 10h6M9 14h6"/>');
			const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48"><circle cx="24" cy="24" r="21" fill="${colour}" stroke="#fff" stroke-width="3"/><g transform="translate(12 12) scale(1)" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${glyphPaths}</g></svg>`;
			const uri = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
			nodeImageCache.set(doctype, uri);
			return uri;
		};
		const itemGlyph = (doctype, size) => {
			const c = this.colors && this.colors[doctype] ? this.colors[doctype] : '#6a7a7e';
			const s = size || 14, pad = Math.ceil(s/3);
			const g = (window.sirajIcons && window.sirajIcons.svg)
				? window.sirajIcons.svg(doctype, {size: Math.round(s*0.7)})
				: '';
			return `<span class="sx-item-glyph" style="background:${c};width:${s+pad}px;height:${s+pad}px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;color:#fff;flex-shrink:0">${g}</span>`;
		};
		const CARET_SVG = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 6 6 6-6 6"/></svg>';
		const escapeHtml = s => String(s == null ? '' : s).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
		const fmtValue = v => {
			if (v == null || v === '') return '';
			if (typeof v === 'object') {
				if (v.type === 'link') return v.title || v.name;
				if (v.type === 'attach') return v.url;
				return JSON.stringify(v);
			}
			return String(v);
		};
		this.network = new vis.Network(graphHost[0], { nodes: nodeSet, edges: edgeSet }, {
			interaction: { hover: true, navigationButtons: true, keyboard: true },
			physics: { stabilization: { iterations: 100 }, barnesHut: { gravitationalConstant: -5000, springLength: 150 } },
			nodes: { shape: 'circularImage', size: 22, borderWidth: 3, color: { border:'#fff', background:'#6a7a7e' }, font: { size:13, color:'#233b37' } },
			edges: { color: { color: '#9aa9b1', highlight: '#267b77' }, smooth: { type: 'dynamic' }, font: { size: 11, align: 'middle' } }
		});
		const showNode = (id, remember = true) => {
			const node = all.get(id);
			if (!node || !nodeSet.get(id)) return;
			if (remember && currentId && currentId !== id) history.push(currentId);
			currentId = id;
			if (centerButton) centerButton.prop('disabled', false);
			this.network.selectNodes([id]);
			this.network.focus(id, { scale: 1, animation: { duration: 400 } });
			this.showDetails(node.label, [[__('Type'), __(node.doctype)], [__('ID'), node.name], ...Object.entries(node.details || {}).map(([label, value]) => [__(label), value])], node);
			const connected = currentEdges.filter(e => JSON.stringify(e.source) === id || JSON.stringify(e.target) === id);
			// Connections heading with an inline "+ Add" button that opens the
			// dialog pre-filled to THIS selected node — keeps the action in the
			// context of the item the user just clicked.
			const connHead = $('<div class="sx-neighbors-head"></div>').appendTo(this.aside);
			$('<h5 class="sx-neighbors-heading"></h5>').text(__('Connections ({0})', [connected.length])).appendTo(connHead);
			$('<button type="button" class="btn btn-primary btn-xs sx-conn-add" aria-label="' + __('Add relationship from this record') + '">+ ' + __('Add') + '</button>')
				.on('click', () => {
					this.openAddRelationshipDialog(node, null, { onSaved: () => refreshGraph() });
				})
				.appendTo(connHead);
			if (!connected.length) $('<p class="sx-muted"></p>').text(__('No visible connections in this view. Use + Add to create one from this record.')).appendTo(this.aside);
			connected.forEach(edge => {
				const sourceId = JSON.stringify(edge.source), targetId = JSON.stringify(edge.target);
				const neighbor = all.get(sourceId === id ? targetId : sourceId);
				if (!neighbor) return;
				const row = $('<div class="sx-neighbor"></div>').appendTo(this.aside);
				this.button(edge.type || __('Relationship'), () => showEdge(edge)).addClass('sx-edge-link').appendTo(row);
				this.button(neighbor.label, () => showNode(this.id(neighbor))).addClass('sx-neighbor-link').appendTo(row);
			});

			// Suggested partners — quick "+" chips for likely missing edges.
			const suggestions = suggestPartners(id);
			if (suggestions.length) {
				$('<h5 class="sx-neighbors-heading"></h5>').text(__('Suggested connections')).appendTo(this.aside);
				const chipRow = $('<div class="sx-suggest-row"></div>').appendTo(this.aside);
				suggestions.forEach(other => {
					const chip = $('<button type="button" class="btn btn-xs btn-default sx-suggest-chip"></button>')
						.append(itemGlyph(other.doctype, 14))
						.append($('<span></span>').text(other.label))
						.on('click', () => {
							this.openAddRelationshipDialog(node, other, { onSaved: () => refreshGraph() });
						})
						.appendTo(chipRow);
				});
			}
		};
		const edgeCache = {};
		let edgeSeq = 0;
		const showEdge = edge => {
			if (!edge) return;
			currentId = null;
			if (centerButton) centerButton.prop('disabled', true);
			renderEdgePanel(edge);
		};
		const renderEdgePanel = async edge => {
			const E_TABS = [
				{ id:'overview', label: __('Overview') },
				{ id:'fields',   label: __('Details') },
				{ id:'evidence', label: __('Evidence') },
				{ id:'endpoints',label: __('Endpoints') },
			];
			const state = { tab: 'overview', sections: {} };

			this.aside.removeClass('sx-panel-hidden').empty();

			// Header
			const head = $('<div class="sx-panel-head"></div>').appendTo(this.aside);
			const title = $('<div class="sx-panel-title"></div>').appendTo(head);
			title.append(itemGlyph('Relationship', 28));
			const heading = $('<h4></h4>').attr('title', edge.type || edge.name).text(edge.type || __('Relationship')).appendTo(title);
			$('<span class="sx-type-chip"></span>').text(__('Relationship')).appendTo(title);
			if (edge.is_current || !edge.end_date) {
				$('<span class="sx-status-chip sx-status-active"></span>').text(__('Current')).appendTo(title);
			} else {
				$('<span class="sx-status-chip sx-status-ended"></span>').text(__('Ended')).appendTo(title);
			}
			const actions = $('<div class="sx-panel-actions"></div>').appendTo(head);
			$('<button type="button" class="btn btn-link btn-sm"></button>')
				.text(__('Add related'))
				.on('click', () => {
					const a = all.get(JSON.stringify(edge.source)), b = all.get(JSON.stringify(edge.target));
					this.openAddRelationshipDialog(a, null, { onSaved: () => refreshGraph() });
				})
				.appendTo(actions);
			$('<button type="button" class="btn btn-link btn-sm"></button>')
				.text(__('Open record'))
				.on('click', () => frappe.set_route('Form', 'Relationship', edge.name))
				.appendTo(actions);
			$('<button type="button" class="sx-panel-close"></button>').attr('aria-label', __('Close details')).html('&times;')
				.on('click', () => this.aside.addClass('sx-panel-hidden'))
				.appendTo(actions);

			// Direction banner
			const banner = $('<div class="sx-edge-banner"></div>').appendTo(this.aside);
			[['subject', edge.source], ['object', edge.target]].forEach(([role, key]) => {
				const id = JSON.stringify(key), node = all.get(id);
				const side = $('<div class="sx-edge-endpoint"></div>').addClass('sx-edge-' + role).appendTo(banner);
				if (node) {
					side.append(itemGlyph(node.doctype, 22));
					const txt = $('<div class="sx-edge-ep-text"></div>').appendTo(side);
					$('<span class="sx-edge-ep-role"></span>').text(role === 'subject' ? __('Subject') : __('Object')).appendTo(txt);
					$('<button type="button" class="btn btn-link btn-xs sx-edge-ep-name"></button>')
						.text(node.label)
						.attr('title', node.label + ' · ' + node.name)
						.on('click', () => showNode(id))
						.appendTo(txt);
				} else {
					side.append(itemGlyph('Source', 22));
					$('<div class="sx-edge-ep-text"></div>')
						.append($('<span class="sx-edge-ep-role"></span>').text(role === 'subject' ? __('Subject') : __('Object')))
						.append($('<span class="sx-muted"></span>').text(key[1] || ''))
						.appendTo(side);
				}
			});
			const arrow = $('<div class="sx-edge-arrow" aria-hidden="true"></div>').appendTo(banner);
			arrow.html(/^(directed|one.way)$/i.test(edge.direction || '') ? '→' : '↔');

			// Tab bar
			const tabBar = $('<div class="sx-panel-tabs" role="tablist"></div>').appendTo(this.aside);
			const tabBody = $('<div class="sx-panel-body" role="tabpanel"></div>').appendTo(this.aside);
			const setBadge = (tabId, text) => {
				const b = tabBar.find('.sx-tab-badge[data-tab-badge="'+tabId+'"]');
				if (text == null || text === '' || text === 0) b.text('').hide(); else b.text(String(text)).show();
			};
			const section = (tabId, key, titleText, countNode) => {
				const secKey = tabId + ':' + key;
				const stored = state.sections[secKey];
				const isOpen = stored == null ? true : !!stored;
				const sec = $('<details class="sx-section"></details>').attr('data-sx-section', secKey);
				if (isOpen) sec.attr('open', 'open');
				const sum = $('<summary></summary>').appendTo(sec);
				sum.append($('<span class="sx-section-caret">' + CARET_SVG + '</span>'));
				sum.append($('<span class="sx-section-label"></span>').text(titleText));
				if (countNode != null) {
					const c = $('<span class="sx-section-count"></span>');
					c.text(String(typeof countNode === 'function' ? '…' : countNode));
					sum.append(c);
				}
				const body = $('<div class="sx-section-body"></div>').appendTo(sec);
				sum.on('click', ev => {
					ev.preventDefault();
					const opening = !sec.attr('open');
					if (opening) sec.attr('open','open'); else sec.removeAttr('open');
					state.sections[secKey] = opening;
				});
				return sec;
			};
			const switchTab = id => {
				state.tab = id;
				tabBar.find('button').removeClass('btn-primary').addClass('btn-default').attr('aria-selected','false');
				tabBar.find('button[data-tab="'+id+'"]').removeClass('btn-default').addClass('btn-primary').attr('aria-selected','true');
				renderTab(id);
			};
			E_TABS.forEach(t => $('<button type="button" class="btn btn-xs" role="tab"></button>')
				.addClass(state.tab===t.id?'btn-primary':'btn-default')
				.attr({'data-tab':t.id, 'aria-selected': state.tab===t.id ? 'true':'false'})
				.html(t.label + '<span class="sx-tab-badge" data-tab-badge="'+t.id+'"></span>')
				.on('click', () => switchTab(t.id))
				.appendTo(tabBar));

			const renderTab = id => {
				tabBody.empty();
				if (edgeCache[edge.name]) { mountTab(id, edgeCache[edge.name]); return; }
				const loading = $('<div class="sx-panel-loading"></div>')
					.html('<span>⏳</span> ' + __('Loading…'))
					.appendTo(tabBody);
				const seq = ++edgeSeq;
				frappe.call({ method:'siraj_research.api.relationship_profile.get_relationship_profile', args:{ name: edge.name } })
					.then(r => {
						if (seq !== edgeSeq) return;
						edgeCache[edge.name] = r.message || {};
						mountTab(id, edgeCache[edge.name]);
					})
					.catch(e => {
						if (seq !== edgeSeq) return;
						tabBody.empty();
						const err = $('<div class="sx-panel-error"></div>').appendTo(tabBody);
						$('<div></div>').text(__('Could not load details: {0}', [e.message || String(e)])).appendTo(err);
						$('<button type="button" class="btn btn-xs btn-default"></button>')
							.text(__('Retry'))
							.on('click', () => { delete edgeCache[edge.name]; renderTab(id); })
							.appendTo(err);
					});
			};

			const mountTab = (id, prof) => {
				tabBody.empty();
				if (!prof) return;
				const pane = $('<div class="sx-tab-pane" data-tab-pane="'+id+'"></div>').appendTo(tabBody);

				if (id === 'overview') {
					const metaRows = [];
					if (prof.header && prof.header.status) metaRows.push([__('Status'), prof.header.status]);
					metaRows.push([__('Direction'), (/^(directed|one.way)$/i.test((prof.header && prof.header.direction) || edge.direction || '') ? __('Directed') : __('Symmetric'))]);
					metaRows.push([__('Ongoing'), prof.header && prof.header.is_current ? __('Yes') : __('No')]);
					if (edge.description) metaRows.push([__('Description'), edge.description]);
					metaRows.push([__('Modified'), prof.header && prof.header.modified]);
					metaRows.push([__('Owner'), prof.header && prof.header.owner]);
					if (prof.permissions) {
						const perms = [];
						if (prof.permissions.can_write) perms.push(__('can edit'));
						if (prof.permissions.can_create) perms.push(__('can link'));
						if (perms.length) metaRows.push([__('Permissions'), perms.join(', ')]);
					}
					const sec = section('overview', 'meta', __('Relationship details')).appendTo(pane);
					const dl = $('<dl></dl>').appendTo(sec.find('.sx-section-body'));
					metaRows.forEach(([k, v]) => {
						if (v == null || v === '') return;
						$('<dt></dt>').text(k).appendTo(dl);
						$('<dd></dd>').text(String(v)).appendTo(dl);
					});

					const counters = prof.counters || { evidence: Number(edge.evidence_count)||0, external_identifiers: 0 };
					const chipData = [
						{ label: __('Evidence'), n: counters.evidence || 0, color:'#53706b' },
						{ label: __('External IDs'), n: counters.external_identifiers || 0, color:'#6a7a7e' },
					];
					const nsSec = section('overview','counters',__('Summary')).appendTo(pane);
					const chipRow = $('<div class="sx-chip-row"></div>').appendTo(nsSec.find('.sx-section-body'));
					chipData.forEach(c => $('<span class="siraj-chip is-on" style="--chip-color:'+c.color+'"></span>')
						.html('<span class="siraj-chip-label">'+c.label+'</span><span class="siraj-chip-count">'+c.n+'</span>')
						.appendTo(chipRow));
					setBadge('evidence', counters.evidence || null);

				} else if (id === 'fields') {
					let fieldCount = 0;
					(prof.sections||[]).forEach(secDef => {
						const fields = secDef.fields || [];
						if (!fields.length) return;
						fieldCount += fields.length;
						const sec = section('fields', 'fld_'+secDef.heading, secDef.heading || __('Fields'), String(fields.length)).appendTo(pane);
						const body = sec.find('.sx-section-body');
						const dl = $('<dl></dl>').appendTo(body);
						fields.forEach(f => {
							$('<dt></dt>').text(f.label).appendTo(dl);
							const v = f.value;
							const dd = $('<dd></dd>').appendTo(dl);
							if (v && typeof v === 'object' && v.type === 'link') {
								$('<button type="button" class="btn btn-link btn-xs"></button>')
									.text(v.title || v.name)
									.on('click', () => frappe.set_route('Form', v.doctype, v.name))
									.appendTo(dd);
							} else if (v && typeof v === 'object' && v.type === 'attach') {
								$('<a target="_blank" rel="noopener"></a>').attr('href', v.url).text(v.url).appendTo(dd);
							} else {
								dd.text(fmtValue(v));
							}
						});
					});
					if (!fieldCount) $('<div class="sx-empty"></div>').text(__('No field data available.')).appendTo(pane);
					setBadge('fields', fieldCount || null);

				} else if (id === 'evidence') {
					const children = prof.children || {};
					const ev = children.evidence;
					const ext = children.external_identifiers;
					if (ev && ev.rows && ev.rows.length) {
						const sec = section('evidence','ev',__('Evidence'), String(ev.total)).appendTo(pane);
						const wrap = $('<div class="sx-table-wrap"></div>').appendTo(sec.find('.sx-section-body'));
						const keys = Object.keys(ev.rows[0]);
						const t = $('<table class="table table-condensed"></table>').appendTo(wrap);
						const thead = $('<thead></thead>').appendTo(t), trh = $('<tr></tr>').appendTo(thead);
						keys.forEach(k => $('<th></th>').text(ev.rows[0][k].label).appendTo(trh));
						const tbody = $('<tbody></tbody>').appendTo(t);
						ev.rows.forEach(row => { const tr=$('<tr></tr>').appendTo(tbody); keys.forEach(k => $('<td></td>').text(fmtValue(row[k].value)).appendTo(tr)); });
						if (ev.truncated) $('<div class="sx-muted" style="padding:6px 0"></div>').text(__('Showing first 50 entries. Open the record for the full list.')).appendTo(sec.find('.sx-section-body'));
					} else {
						$('<div class="sx-empty"></div>').text(__('No evidence attached.')).appendTo(pane);
					}
					if (ext && ext.rows && ext.rows.length) {
						const sec = section('evidence','ext',__('External identifiers'), String(ext.total)).appendTo(pane);
						const wrap = $('<div class="sx-table-wrap"></div>').appendTo(sec.find('.sx-section-body'));
						const keys = Object.keys(ext.rows[0]);
						const t = $('<table class="table table-condensed"></table>').appendTo(wrap);
						const thead = $('<thead></thead>').appendTo(t), trh = $('<tr></tr>').appendTo(thead);
						keys.forEach(k => $('<th></th>').text(ext.rows[0][k].label).appendTo(trh));
						const tbody = $('<tbody></tbody>').appendTo(t);
						ext.rows.forEach(row => { const tr=$('<tr></tr>').appendTo(tbody); keys.forEach(k => $('<td></td>').text(fmtValue(row[k].value)).appendTo(tr)); });
					}

				} else if (id === 'endpoints') {
					const ep = prof.endpoints || {};
					['subject','object'].forEach(role => {
						const p = ep[role];
						const sec = section('endpoints', role, role === 'subject' ? __('Subject') : __('Object')).appendTo(pane);
						const body = sec.find('.sx-section-body');
						if (!p || !p.name) {
							$('<div class="sx-empty"></div>').text(__('Endpoint unavailable.')).appendTo(body);
							return;
						}
						const card = $('<div class="sx-endpoint-card"></div>').appendTo(body);
						card.append(itemGlyph(p.doctype || 'Source', 24));
						const txt = $('<div class="sx-endpoint-text"></div>').appendTo(card);
						$('<div class="sx-endpoint-title"></div>').text(p.title || p.name).appendTo(txt);
						$('<div class="sx-endpoint-sub"></div>').text(__(p.doctype) + ' · ' + p.name).appendTo(txt);
						const idStr = JSON.stringify([p.doctype, p.name]);
						const btnRow = $('<div style="display:flex;gap:6px;margin-top:6px;flex-wrap:wrap"></div>').appendTo(body);
						if (all.get(idStr)) {
							$('<button type="button" class="btn btn-xs btn-default"></button>')
								.text(__('Focus in network'))
								.on('click', () => showNode(idStr))
								.appendTo(btnRow);
						}
						if (p.readable) {
							$('<button type="button" class="btn btn-xs btn-default"></button>')
								.text(__('Open record'))
								.on('click', () => frappe.set_route('Form', p.doctype, p.name))
								.appendTo(btnRow);
						}
					});
				}
			};

			switchTab(state.tab);
		};
		const drawMatrix = (nodes, edges) => {
			matrixHost.empty();
			const NS = 'http://www.w3.org/2000/svg', step = 24, offset = 160;
			const side = Math.max(450, offset + nodes.length * step + 20);
			const svg = document.createElementNS(NS, 'svg');
			svg.setAttribute('width', side); svg.setAttribute('height', side);
			svg.setAttribute('role', 'group'); svg.setAttribute('aria-label', __('Relationship matrix'));
			matrixHost.append(svg);
			const positions = new Map(nodes.map((node, i) => [this.id(node), i]));
			const text = (x, y, label, transform, node) => {
				const el = document.createElementNS(NS, 'text'); el.setAttribute('x', x); el.setAttribute('y', y);
				if (transform) el.setAttribute('transform', transform);
				el.textContent = label.length > 22 ? label.slice(0, 21) + '…' : label;
				el.setAttribute('tabindex', '0'); el.setAttribute('role', 'button'); el.setAttribute('aria-label', label);
				el.setAttribute('class', 'sx-matrix-label');
				el.addEventListener('click', () => showNode(this.id(node)));
				el.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); showNode(this.id(node)); } });
				svg.appendChild(el);
			};
			nodes.forEach((n, i) => {
				const y = offset + i * step + 16, x = offset + i * step + 16;
				text(4, y, n.label, null, n); text(x, offset - 8, n.label, `rotate(-90 ${x} ${offset - 8})`, n);
			});
			const pairCounts = new Map();
			edges.forEach(edge => {
				const i = positions.get(JSON.stringify(edge.source)), j = positions.get(JSON.stringify(edge.target));
				if (i === undefined || j === undefined) return;
				const pair = i + ':' + j, overlap = pairCounts.get(pair) || 0; pairCounts.set(pair, overlap + 1);
				const rect = document.createElementNS(NS, 'rect');
				rect.setAttribute('x', offset + j * step + 2 + (overlap % 3) * 4);
				rect.setAttribute('y', offset + i * step + 2 + (overlap % 3) * 4);
				rect.setAttribute('width', 18 - (overlap % 3) * 4); rect.setAttribute('height', 18 - (overlap % 3) * 4);
				rect.setAttribute('fill', this.colors[nodes[i].doctype]); rect.setAttribute('class', 'sx-matrix-cell');
				rect.setAttribute('tabindex', '0'); rect.setAttribute('role', 'button');
				rect.setAttribute('aria-label', nodes[i].label + ' → ' + nodes[j].label + ': ' + (edge.type || __('Relationship')));
				const title = document.createElementNS(NS, 'title'); title.textContent = rect.getAttribute('aria-label'); rect.appendChild(title);
				rect.addEventListener('click', () => showEdge(edge));
				rect.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); showEdge(edge); } });
				svg.appendChild(rect);
			});
		};
		const update = () => {
			const term = searchTerm.toLocaleLowerCase();
			let nodes = data.nodes.filter(n => (!selectedType || n.doctype === selectedType) && (n.label + ' ' + n.name).toLocaleLowerCase().includes(term));
			let ids = new Set(nodes.map(n => this.id(n)));
			const eligibleEdges = data.edges.filter(e => ids.has(JSON.stringify(e.source)) && ids.has(JSON.stringify(e.target)) && (!edgeType || e.type === edgeType) && (!hideEnded || !e.end_date) && (!evidenceOnly || Number(e.evidence_count) > 0));
			const distance = new Map();
			const activeCenters = centerIds.filter(cid => ids.has(cid));
			if (activeCenters.length) {
				const neighbors = new Map();
				eligibleEdges.forEach(e => {
					const a = JSON.stringify(e.source), b = JSON.stringify(e.target);
					if (!neighbors.has(a)) neighbors.set(a, []);
					if (!neighbors.has(b)) neighbors.set(b, []);
					neighbors.get(a).push(b); neighbors.get(b).push(a);
				});
				// Multi-source BFS: each center starts at distance 0; with
				// multiple centers rings become a "union of balls" so the
				// orbit layout places all selected records on the innermost ring.
				const queue = [];
				activeCenters.forEach(cid => { distance.set(cid, 0); queue.push(cid); });
				for (let index = 0; index < queue.length; index++) {
					const id = queue[index], depth = distance.get(id);
					if (depth >= maxDistance) continue;
					(neighbors.get(id) || []).forEach(neighbor => {
						if (!distance.has(neighbor)) { distance.set(neighbor, depth + 1); queue.push(neighbor); }
					});
				}
				nodes = nodes.filter(n => distance.has(this.id(n)));
				ids = new Set(distance.keys());
			}
			currentEdges = eligibleEdges.filter(e => ids.has(JSON.stringify(e.source)) && ids.has(JSON.stringify(e.target)));
			currentNodes = nodes;
			edgeSet.clear(); nodeSet.clear(); history = []; currentId = null;
			if (centerButton) centerButton.prop('disabled', true);
			if (resetButton) resetButton.prop('disabled', activeCenters.length === 0);
			const large = nodes.length > 500;
			this.network.setOptions({ physics: { enabled: layout === 'force' && !large } });
			const columns = Math.ceil(Math.sqrt(nodes.length || 1));
			const positions = new Map(), rings = new Map();
			nodes.forEach(n => {
				const id = this.id(n), ring = activeCenters.length ? distance.get(id) : 1;
				if (!rings.has(ring)) rings.set(ring, []);
				rings.get(ring).push(id);
			});
			let previousRadius = 0;
			[...rings.keys()].sort((a, b) => a - b).forEach(ring => {
				const idsInRing = rings.get(ring);
				if (ring === 0) {
					// Lay all selected centers out on a small inner circle so
					// multi-centre views don't collapse to a point.
					const r = Math.max(40, idsInRing.length * 18);
					idsInRing.forEach((id, i) => {
						const angle = idsInRing.length === 1 ? 0 : 2 * Math.PI * i / idsInRing.length;
						positions.set(id, {x: r * Math.cos(angle), y: r * Math.sin(angle)});
					});
					previousRadius = r + 140;
					return;
				}
				const radius = Math.max(previousRadius + 180, idsInRing.length * 22);
				previousRadius = radius;
				idsInRing.forEach((id, i) => {
					const angle = 2 * Math.PI * i / idsInRing.length;
					positions.set(id, {x: radius * Math.cos(angle), y: radius * Math.sin(angle)});
				});
			});
			// Visually distinguish center nodes with a thicker border.
			const centerSet = new Set(activeCenters);
			nodeSet.add(nodes.map((n, i) => {
				const isCenter = centerSet.has(this.id(n));
				return { id: this.id(n), label: n.label, image: nodeImage(n.doctype),
					borderWidth: isCenter ? 6 : 3, color: { border: isCenter ? '#c69a21' : '#fff', background: this.colors[n.doctype] || '#6a7a7e', highlight:{border: isCenter ? '#c69a21' : '#fff', background: this.colors[n.doctype] || '#6a7a7e'} },
					...(layout === 'orbit' ? positions.get(this.id(n)) : large ? { x: (i % columns) * 180, y: Math.floor(i / columns) * 110 } : {}) };
			}));
			graphHost.toggle(layout !== 'matrix'); matrixHost.toggle(layout === 'matrix');
			if (layout === 'matrix') drawMatrix(nodes, currentEdges);
			edgeSet.add(currentEdges.map(e => ({ id: e.name, from: JSON.stringify(e.source), to: JSON.stringify(e.target), label: e.type, arrows: /^(directed|one.way)$/i.test(e.direction) ? 'to' : '' })));
			const suffix = activeCenters.length
				? ' ' + __('Centered on {0} record(s).', [activeCenters.length])
				: '';
			this.note.text(__('Showing {0} records and {1} relationships. Only visible records and links are included.', [nodes.length, currentEdges.length]) + suffix + ' ' + this.warning(data) + (evidenceOnly && data.edges.some(e => e.evidence_count == null) ? ' ' + __('Evidence counts are unavailable for some relationships.') : '') + ' ' + __('Tip: hold Shift and drag one node onto another to create a relationship.'));
			this.showDetails(__('Relationship map'), [[__('About this view'), __('Select one or more records (via the Centre picker or by clicking a node) to walk out N degrees. Drag nodes to rearrange the network. Click an edge to inspect the relationship.')]]);
		};
		this.network.on('selectNode', event => showNode(event.nodes[0]));
		this.network.on('selectEdge', event => showEdge(edgeLookup.get(event.edges[0])));
		$('<h5></h5>').text(__('Filters')).appendTo(this.rail);
		const filters = this.filterControls(types, (search, type) => { searchTerm = search; selectedType = type; centerIds = []; trail = []; centerSelect.set([]); update(); }, this.rail);
		$('<h5></h5>').text(__('Arrangement')).appendTo(this.rail);
		const layoutSelect = $('<select class="form-control input-sm"></select>').attr('aria-label', __('Relationship layout')).appendTo(this.rail);
		[['force', __('Force')], ['orbit', __('Orbit')], ['matrix', __('Matrix')]].forEach(([id, title]) => $('<option></option>').val(id).text(title).appendTo(layoutSelect));
		layoutSelect.on('change', () => { const selected = currentId; layout = layoutSelect.val(); update(); if (selected && nodeSet.get(selected)) showNode(selected, false); if (layout !== 'matrix') this.network.fit({animation: true}); });
		$('<h5></h5>').text(__('Relationship type')).appendTo(this.rail);
		const edgeSelect = $('<select class="form-control input-sm"></select>').attr('aria-label', __('Relationship type')).appendTo(this.rail);
		$('<option value=""></option>').text(__('All relationship types')).appendTo(edgeSelect);
		[...new Set(data.edges.map(e => e.type).filter(Boolean))].sort().forEach(type => $('<option></option>').val(type).text(type).appendTo(edgeSelect));
		edgeSelect.on('change', () => { edgeType = edgeSelect.val(); update(); });
		const ended = $('<label class="sx-check"></label>').appendTo(this.rail);
		$('<input type="checkbox">').on('change', e => { hideEnded = e.target.checked; update(); }).appendTo(ended);
		ended.append(document.createTextNode(__('Hide ended relationships')));
		const evidenceLabel = $('<label class="sx-check"></label>').appendTo(this.rail);
		const evidenceCheck = $('<input type="checkbox">').appendTo(evidenceLabel);
		evidenceLabel.append(document.createTextNode(__('Only relationships with evidence')));
		evidenceCheck.on('change', async () => {
			if (!evidenceCheck.prop('checked')) { evidenceOnly = false; update(); return; }
			if (!evidenceLoaded) {
				evidenceCheck.prop('disabled', true);
				try {
					const response = await frappe.call({method: 'siraj_research.visualization.relationship_data', args: {include_evidence: 1}});
					if (renderId !== this.renderId) return;
					const counts = new Map(response.message.edges.map(edge => [edge.name, edge.evidence_count]));
					data.edges.forEach(edge => { edge.evidence_count = counts.has(edge.name) ? counts.get(edge.name) : null; });
					evidenceLoaded = true;
				} catch (error) {
					if (renderId === this.renderId) { evidenceCheck.prop('checked', false); this.note.text(__('Unable to load evidence counts.')).addClass('sx-warning'); }
					return;
				} finally { evidenceCheck.prop('disabled', false); }
			}
			evidenceOnly = evidenceCheck.prop('checked'); update();
		});
		const depthSelect = $('<select class="form-control input-sm"></select>').attr('aria-label', __('Relationship depth')).appendTo(this.tools);
		[[1, __('Direct relationships')], [2, __('Two degrees')], [3, __('Three degrees')]].forEach(([value, title]) => $('<option></option>').val(value).text(title).appendTo(depthSelect));
		depthSelect.on('change', () => {
			maxDistance = Number(depthSelect.val()); update();
			if (centerIds.length && layout !== 'matrix') this.network.fit({animation: true});
		});
		const centerSelect = this.centerPicker(centerItems, ids => {
			centerIds = ids.slice();
			trail = [];
			update();
			if (layout !== 'matrix') this.network.fit({animation: true});
		}, this.tools);
		centerButton = this.button(__('Center on selected record'), () => {
			if (!currentId) return;
			// Toggle: if already a center, remove; otherwise add.
			const set = new Set(centerIds);
			if (set.has(currentId)) set.delete(currentId); else set.add(currentId);
			centerIds = [...set];
			centerSelect.set(centerIds);
			trail = [];
			update();
			showNode(currentId, false);
			if (layout !== 'matrix') this.network.fit({animation: true});
		}).prop('disabled', true).appendTo(this.tools);
		resetButton = this.button(__('Show all records'), () => { centerIds = []; trail = []; centerSelect.set([]); update(); }).prop('disabled', true).appendTo(this.tools);
		this.button(__('Back'), () => {
			while (history.length) { const id = history.pop(); if (nodeSet.get(id)) { showNode(id, false); return; } }
		}).appendTo(this.tools);

		// ---------- Advanced relationship authoring ----------
		// "Add relationship" — works with zero, one, or two pre-filled endpoints.
		// With a selected node it pre-fills the subject; with drag-link (see below)
		// it pre-fills both subject and object.
		const addBtn = this.button(__('+ Add relationship'), () => {
			const sel = currentId ? all.get(currentId) : null;
			this.openAddRelationshipDialog(sel, null, {
				onSaved: () => { refreshGraph(); },
			});
		}).addClass('btn-primary btn-sm').appendTo(this.tools);

		// Drag-link mode: hold Shift and drag from one node onto another to
		// immediately open the add-relationship dialog with both endpoints
		// pre-filled. A visual connector line follows the cursor during the drag.
		let dragLink = null; // {from:id}
		let ghostLine = null;
		const $canvas = $(graphHost);
		this.network.on('dragStart', params => {
			if (!params.nodes || !params.nodes.length) return;
			if (!(params.event && params.event.srcEvent && params.event.srcEvent.shiftKey)) return;
			dragLink = { from: params.nodes[0] };
			this.network.setOptions({ interaction: { dragNodes: false } });
		});
		this.network.on('dragging', params => {
			if (!dragLink) return;
			const dom = params.event && params.event.center;
			if (!dom) return;
			if (!ghostLine) {
				ghostLine = $('<div class="sx-link-ghost" aria-hidden="true"></div>').appendTo($canvas);
			}
			const a = this.network.getPositions([dragLink.from])[dragLink.from];
			if (!a) return;
			const ap = this.network.canvasToDOM({x:a.x, y:a.y});
			ghostLine.css({
				left: ap.x, top: ap.y,
				width: Math.hypot(dom.x - ap.x, dom.y - ap.y),
				transform: `rotate(${Math.atan2(dom.y - ap.y, dom.x - ap.x)}rad)`,
			});
		});
		this.network.on('dragEnd', params => {
			if (!dragLink) return;
			this.network.setOptions({ interaction: { dragNodes: true } });
			if (ghostLine) { ghostLine.remove(); ghostLine = null; }
			const targetId = params.nodes && params.nodes.length ? params.nodes[params.nodes.length - 1] : null;
			// If the drop landed on a different node, open the dialog pre-filled.
			if (targetId && targetId !== dragLink.from && all.get(targetId)) {
				this.openAddRelationshipDialog(all.get(dragLink.from), all.get(targetId), {
					onSaved: () => refreshGraph(),
				});
			}
			dragLink = null;
		});

		// Suggested-connections hint: when a single node is selected, scan the
		// node set for same-type/places-in-common/commander-parent partners that
		// aren't yet linked and surface up to 5 as one-click chips in the panel.
		function suggestPartners(nodeId) {
			if (!nodeId) return [];
			const n = all.get(nodeId);
			if (!n) return [];
			const existing = new Set();
			data.edges.forEach(e => {
				const a = JSON.stringify(e.source), b = JSON.stringify(e.target);
				if (a === nodeId) existing.add(b);
				if (b === nodeId) existing.add(a);
			});
			const score = new Map();
			data.nodes.forEach(other => {
				const oid = JSON.stringify([other.doctype, other.name]);
				if (oid === nodeId || existing.has(oid)) return;
				let s = 0;
				// Same place or shared linked_place/birthplace → small boost.
				const nPlace = (n.details && n.details['Place (HQ location)']) || (n.details && n.details.Place) || n.place || n.birthplace;
				const oPlace = (other.details && other.details['Place (HQ location)']) || (other.details && other.details.Place) || other.place || other.birthplace;
				if (nPlace && oPlace && nPlace === oPlace) s += 5;
				// Same echelon or type → boost.
				if (n.doctype === other.doctype) s += 2;
				if (n.doctype === 'Military Unit' && other.doctype === 'Military Unit') {
					if (n.details && other.details && n.details.Echelon === other.details.Echelon) s += 3;
				}
				// Persons sharing a unit / institution → boost.
				if (s > 0) score.set(oid, s);
			});
			return [...score.entries()].sort((a,b) => b[1] - a[1]).slice(0, 5).map(([id]) => all.get(id)).filter(Boolean);
		}

		// refreshGraph: refetch relationship data (so the new edge appears).
		const refreshGraph = async () => {
			try {
				const res = await frappe.call({ method: 'siraj_research.visualization.relationship_data', args: { include_evidence: evidenceLoaded ? 1 : 0 } });
				if (res && res.message) {
					// Preserve any previously-loaded evidence counts.
					const oldCounts = new Map(data.edges.map(e => [e.name, e.evidence_count]));
					data = res.message;
					if (!Array.isArray(data.nodes)) data.nodes = [];
					if (!Array.isArray(data.edges)) data.edges = [];
					if (evidenceLoaded) {
						data.edges.forEach(e => {
							if (oldCounts.has(e.name)) e.evidence_count = oldCounts.get(e.name);
						});
					}
					data.edges.forEach(e => edgeLookup.set(e.name, e));
					data.nodes.forEach(n => all.set(this.id(n), n));
					// Refresh the center picker items with any new nodes.
					centerItems.length = 0;
					data.nodes.filter(n => CENTERABLE_TYPES.indexOf(n.doctype) >= 0)
						.map(n => ({ id: this.id(n), label: n.label, sub: n.name, doctype: n.doctype }))
						.sort((a, b) => a.label.localeCompare(b.label))
						.forEach(it => centerItems.push(it));
				}
			} catch (e) { /* ignore: offline or perm */ }
			update();
			if (currentId && nodeSet.get(currentId)) showNode(currentId, false);
		};
		this.button(__('Export SVG'), () => {
			const ns = 'http://www.w3.org/2000/svg';
			const make = (tag, attrs, text) => {
				const el = document.createElementNS(ns, tag);
				Object.entries(attrs || {}).forEach(([key, value]) => el.setAttribute(key, value));
				if (text != null) el.textContent = text;
				return el;
			};
			let svg;
			if (layout === 'matrix') {
				svg = matrixHost.find('svg')[0].cloneNode(true);
				svg.querySelectorAll('text').forEach(el => { el.setAttribute('font-family', 'sans-serif'); el.setAttribute('font-size', '11'); el.setAttribute('fill', '#233b37'); });
				svg.querySelectorAll('rect').forEach(el => { el.setAttribute('stroke', '#fff'); el.setAttribute('stroke-width', '1'); });
			} else {
				// vis-network is canvas-based. Export a standalone vector rendering
				// of the current nodes/edges at their current network positions.
				const positions = this.network.getPositions(currentNodes.map(n => this.id(n)));
				const placed = currentNodes.filter(n => positions[this.id(n)] && Number.isFinite(positions[this.id(n)].x) && Number.isFinite(positions[this.id(n)].y));
				if (placed.length !== currentNodes.length) {
					this.note.text(__('Unable to export: some node positions are unavailable. Try again after the layout settles.')).addClass('sx-warning');
					return;
				}
				let minX = 0, maxX = 0, minY = 0, maxY = 0;
				if (placed.length) {
					minX = maxX = positions[this.id(placed[0])].x; minY = maxY = positions[this.id(placed[0])].y;
					placed.forEach(n => { const p = positions[this.id(n)]; minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x); minY = Math.min(minY, p.y); maxY = Math.max(maxY, p.y); });
				}
				const pairKey = edge => JSON.stringify([JSON.stringify(edge.source), JSON.stringify(edge.target)].sort());
				const pairTotals = new Map();
				currentEdges.forEach(edge => { const key = pairKey(edge); pairTotals.set(key, (pairTotals.get(key) || 0) + 1); });
				let padding = 180;
				pairTotals.forEach(total => { padding = Math.max(padding, 70 + total * 25); });
				placed.forEach(node => { padding = Math.max(padding, String(node.label).length * 8); });
				currentEdges.forEach(edge => { padding = Math.max(padding, String(edge.type || '').length * 7); });
				svg = make('svg', {xmlns: ns, viewBox: `${minX - padding} ${minY - padding} ${Math.max(2 * padding, maxX - minX + 2 * padding)} ${Math.max(2 * padding, maxY - minY + 2 * padding)}`, role: 'img', 'aria-label': __('Relationship map')});
				const defs = make('defs');
				const arrow = make('marker', {id: 'sx-arrow', viewBox: '0 0 10 10', refX: '9', refY: '5', markerWidth: '6', markerHeight: '6', orient: 'auto-start-reverse'});
				arrow.appendChild(make('path', {d: 'M 0 0 L 10 5 L 0 10 z', fill: '#64777d'})); defs.appendChild(arrow); svg.appendChild(defs);
				const multiplicity = new Map();
				currentEdges.forEach(edge => {
					const a = positions[JSON.stringify(edge.source)], b = positions[JSON.stringify(edge.target)];
					if (!a || !b || ![a.x, a.y, b.x, b.y].every(Number.isFinite)) return;
					const pair = pairKey(edge);
					const index = multiplicity.get(pair) || 0; multiplicity.set(pair, index + 1);
					let path, labelX, labelY;
					if (a.x === b.x && a.y === b.y) {
						const r = 35 + index * 12;
						path = `M ${a.x - 10} ${a.y - 10} C ${a.x - r} ${a.y - r * 2}, ${a.x + r} ${a.y - r * 2}, ${a.x + 10} ${a.y - 10}`;
						labelX = a.x; labelY = a.y - r * 1.5;
					} else {
						const dx = b.x - a.x, dy = b.y - a.y, length = Math.hypot(dx, dy), offset = index ? (Math.ceil(index / 2) * 25 * (index % 2 ? 1 : -1)) : 0;
						const x1 = a.x + dx / length * 14, y1 = a.y + dy / length * 14, x2 = b.x - dx / length * 18, y2 = b.y - dy / length * 18;
						const cx = (a.x + b.x) / 2 - dy / length * offset, cy = (a.y + b.y) / 2 + dx / length * offset;
						path = `M ${x1} ${y1} Q ${cx} ${cy} ${x2} ${y2}`;
						labelX = (x1 + 2 * cx + x2) / 4; labelY = (y1 + 2 * cy + y2) / 4;
					}
					const line = make('path', {d: path, fill: 'none', stroke: '#64777d', 'stroke-width': 2});
					if (/^(directed|one.way)$/i.test(edge.direction)) line.setAttribute('marker-end', 'url(#sx-arrow)');
					line.appendChild(make('title', {}, edge.type || __('Relationship'))); svg.appendChild(line);
					if (edge.type) svg.appendChild(make('text', {x: labelX, y: labelY - 4, 'text-anchor': 'middle', 'font-family': 'sans-serif', 'font-size': 11, fill: '#344c4c'}, edge.type));
				});
				placed.forEach(node => {
					const p = positions[this.id(node)], group = make('g', {});
					group.appendChild(make('circle', {cx: p.x, cy: p.y, r: 13, fill: this.colors[node.doctype] || '#64777d', stroke: '#344c4c', 'stroke-width': 2}));
					group.appendChild(make('text', {x: p.x, y: p.y + 31, 'text-anchor': 'middle', 'font-family': 'sans-serif', 'font-size': 13, fill: '#233b37'}, node.label));
					group.appendChild(make('title', {}, __(node.doctype) + ' · ' + node.name)); svg.appendChild(group);
				});
			}
			svg.setAttribute('xmlns', ns);
			const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(svg)], {type: 'image/svg+xml'}));
			const a = document.createElement('a'); a.href = url; a.download = 'siraj-relationships.svg'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
		}).appendTo(this.tools);
		this.button(__('Fit network'), () => this.network.fit({ animation: true })).appendTo(this.tools);
		this.button(__('Stabilize layout'), () => this.network.stabilize()).appendTo(this.tools);
		update();
	}

	async structures(renderId) {
		await frappe.require(['/assets/siraj_research/vendor/d3/d3.min.js', '/assets/siraj_research/css/siraj_explorer.css']);
		await frappe.require('/assets/siraj_research/vendor/d3-sankey/d3-sankey.min.js');
		await frappe.require('/assets/siraj_research/js/structure_deck.js');
		if (renderId !== this.renderId) return;
		this.canvas.removeClass('sx-canvas').addClass('sx-structure-host');

		// ---------- Dataset registry (with groups for the multi-select chip bar) -----
		const SOURCES = [
			{ id: 'people',        label: __('People'),          glyph: 'Person',               group: __('Entities') },
			{ id: 'institutions',  label: __('Institutions'),    glyph: 'Institution',          group: __('Entities') },
			{ id: 'places',        label: __('Places'),          glyph: 'Place',                group: __('Entities') },
			{ id: 'mil_units',     label: __('Military Units'),  glyph: 'Military Unit',        group: __('Military') },
			{ id: 'forces',        label: __('Forces (echelon)'),glyph: 'Military Unit',        group: __('Military') },
			{ id: 'units',         label: __('Command hierarchy'), glyph: 'Military Unit',      group: __('Military') },
			{ id: 'units-ops',     label: __('Units × Operations'), glyph: 'Military Unit',    group: __('Military') },
			{ id: 'deployments',   label: __('Deployments'),     glyph: 'Operational Deployment', group: __('Military') },
			{ id: 'missions',      label: __('Missions'),        glyph: 'Mission',              group: __('Military') },
			{ id: 'exercises',     label: __('Training exercises'), glyph: 'Training Exercise', group: __('Military') },
			{ id: 'events',        label: __('Research events'), glyph: 'Research Event',       group: __('Research') },
			{ id: 'relationships', label: __('Relationships'),   glyph: 'Relationship',         group: __('Research') },
			{ id: 'sources',       label: __('Sources'),         glyph: 'Source',               group: __('Research') },
		];

		// ---------- Filter bar (search + multi-select chips + view switcher) ----------
		const filterBar = $('<div class="sx-struct-filter" role="toolbar" aria-label="Structure filters"></div>').appendTo(this.tools);
		const searchWrap = $('<div class="sx-struct-search"></div>').appendTo(filterBar);
		const searchInput = $('<input type="search" class="form-control input-sm" autocomplete="off">')
			.attr({'aria-label': __('Search structure views'), placeholder: __('Search datasets or filter content…')})
			.appendTo(searchWrap);
		$('<span class="sx-struct-search-icon" aria-hidden="true">⌕</span>').prependTo(searchWrap);

		const activeSource = $('<div class="sx-struct-active" aria-live="polite"></div>').appendTo(filterBar);
		const chipHost = $('<div class="sx-struct-chips"></div>').appendTo(this.tools);
		const groupHeaders = {};

		function renderChips(term = '') {
			chipHost.empty();
			const q = term.trim().toLocaleLowerCase();
			const groups = new Map();
			SOURCES.forEach(src => {
				if (q && src.label.toLocaleLowerCase().indexOf(q) < 0 && src.group.toLocaleLowerCase().indexOf(q) < 0) return;
				if (!groups.has(src.group)) groups.set(src.group, []);
				groups.get(src.group).push(src);
			});
			if (!groups.size) {
				$('<span class="sx-muted"></span>').text(__('No matching views')).appendTo(chipHost);
				return;
			}
			for (const [group, list] of groups) {
				const header = $('<div class="sx-struct-group-head"></div>').text(group).appendTo(chipHost);
				const row = $('<div class="sx-struct-chip-row" role="group"></div>').attr('aria-label', group).appendTo(chipHost);
				list.forEach(src => {
					const chip = $('<button type="button" class="btn btn-sm sx-struct-chip"></button>')
						.attr('aria-pressed', src.id === currentId ? 'true' : 'false')
						.toggleClass('active', src.id === currentId)
						.appendTo(row);
					chip.append($('<span class="sx-struct-chip-glyph"></span>').html((window.sirajIcons && window.sirajIcons.svg(src.glyph, {size:14})) || ''));
					chip.append($('<span class="sx-struct-chip-label"></span>').text(src.label));
					chip.on('click', () => selectSource(src.id));
				});
			}
		}

		// Default starting source.
		let currentId = 'people';
		let request = 0;
		let currentDeck = null;
		const filterTerm = () => searchInput.val() || '';

		const selectSource = async (id) => {
			currentId = id;
			activeSource.empty();
			const src = SOURCES.find(s => s.id === id);
			if (src) {
				activeSource.append($('<span class="sx-struct-active-glyph"></span>').html((window.sirajIcons && window.sirajIcons.svg(src.glyph, {size:14})) || ''));
				activeSource.append($('<strong></strong>').text(src.label));
				activeSource.append($('<span class="sx-struct-active-group"></span>').text(src.group));
			}
			renderChips(filterTerm());
			const seq = ++request;
			this.structureDeck = null;
			this.canvas.find('.sd-bar, .sd-stage, .sd-legend, .sd-crumbs, .sd-footer, .sd-table').remove();
			this.aside.empty();
			this.note.removeClass('sx-warning').text(__('Loading…'));
			try {
				const result = await frappe.call({ method: 'siraj_research.visualization.structure_data', args: { source: id } });
				if (renderId !== this.renderId || seq !== request) return;
				const data = result.message;
				this.note.text(__('Counting {0} visible records.', [data.count])
					+ ' ' + __('Source:') + ' ' + (src ? src.label : id)
					+ (data.unavailable_types && data.unavailable_types.length ? ' ' + __('Some record types are not readable: {0}', [data.unavailable_types.map(type => __(type)).join(', ')]) : ''));
				currentDeck = new window.SirajStructureDeck(this, this.canvas, this.aside, data);
				// Apply in-deck search if user typed into the filter bar.
				const t = filterTerm();
				if (t && currentDeck) {
					// Defer so the find input (if any) can be referenced.
					setTimeout(() => currentDeck.find(t), 0);
				}
			} catch (error) {
				if (renderId !== this.renderId || seq !== request) return;
				this.aside.empty();
				this.note.text(__('Unable to load this structure. Check permissions.')).addClass('sx-warning');
				console.error(error);
			}
		};

		searchInput.on('input', () => {
			const term = filterTerm();
			renderChips(term);
			// Live filter within the deck too (if already loaded).
			if (currentDeck && term.length >= 2) currentDeck.find(term);
		});

		// Keyboard: focus filter bar with "/"
		this.canvas.off('keydown.structfilter').on('keydown.structfilter', e => {
			if (e.key === '/' && !/^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName)) {
				e.preventDefault(); searchInput.trigger('focus').select();
			}
		});

		renderChips();
		await selectSource(currentId);
	}
}
