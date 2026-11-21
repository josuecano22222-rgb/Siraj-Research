/* siraj-map-search.js — advanced map search: coordinates, regions, places, records.
 *
 * One box answers four questions: is the text a coordinate (decimal or DMS,
 * parsed server-side with exact arithmetic), does it name an admin region,
 * a gazetteer place, or a mapped research record. Pure helpers are exported
 * for Node tests; mount() builds the desk widget.
 *
 * Precision rule: coordinate strings from the server are displayed verbatim
 * — this file never routes them through Number() except when handing a
 * value to Leaflet for viewport placement (rendering only).
 */
((root) => {
	'use strict';

	// Node has no frappe __; identity keeps the pure helpers testable while
	// every literal stays discoverable by the translation audit.
	const __ = (typeof root !== 'undefined' && typeof root.__ === 'function')
		? root.__
		: (s) => s;

	const MIN_CHARS = 2;
	const METHOD = 'siraj_research.api.map_search.search';
	const BBOX_METHOD = 'siraj_research.api.map_search.search_bbox';
	const CASCADE_METHOD = 'siraj_research.api.map_search.region_children';
	const GROUP_KEYS = ['coordinate', 'regions', 'places', 'records'];
	// Must match GEO_TYPES on the server exactly (visualization.py) —
	// unknown values are silently dropped by parse_types, which would
	// broaden a filter instead of applying it.
	const RECORD_TYPES = [
		['', 'All types'], ['Person', 'Person'], ['Institution', 'Institution'],
		['Place', 'Place'], ['Research Event', 'Research Event'],
		['Military Unit', 'Military Unit'], ['Operational Deployment', 'Operational Deployment'],
	];

	/* ---------- pure helpers (node-testable) ---------- */

	function buildParams(state) {
		const params = {
			query: String((state && state.query) || '').trim(),
			scope: (state && state.scope) || 'all',
			limit: (state && state.limit) || 8,
		};
		if (state && state.levels) params.levels = String(state.levels);
		if (state && state.types) params.types = String(state.types);
		return params;
	}

	function shouldSearch(query) {
		return String(query || '').trim().length >= MIN_CHARS;
	}

	/* Exact coordinate rendering: strings only, no float round-trip. */
	function coordinateDisplay(coord) {
		if (!coord) return null;
		if (coord.error) {
			return {
				error: coord.error,
				input: coord.input || '',
				suggestion: coord.suggestion
					? {
						lat: coord.suggestion.lat,
						lon: coord.suggestion.lon,
						text: coord.suggestion.lat + ', ' + coord.suggestion.lon,
					}
					: null,
			};
		}
		return {
			format: coord.format,
			primary: coord.lat + ', ' + coord.lon,
			input: coord.input || '',
			fraction:
				coord.format === 'dms' && coord.lat_fraction
					? coord.lat_fraction + '  ·  ' + (coord.lon_fraction || '')
					: null,
			assumed_order: coord.assumed_order || 'lat,lon',
		};
	}

	/* Error codes → caller-supplied translator (so __() stays discoverable). */
	function coordinateErrorText(code, translate) {
		const table = {
			invalid_number: __('That does not look like a number.'),
			dms_out_of_range: __('Degrees/minutes/seconds are out of range (minutes and seconds must be below 60).'),
			dms_sign_conflict: __('A negative sign conflicts with the hemisphere letter.'),
			wrong_hemisphere: __('That hemisphere letter belongs to the other coordinate.'),
			conflicting_hemisphere: __('A minus sign conflicts with the hemisphere letter.'),
			out_of_range: __('Latitude must be between -90 and 90, longitude between -180 and 180.'),
		};
		const text = table[code] || __('Invalid coordinates.');
		return translate ? translate(text) : text;
	}

	function groupResults(resp) {
		const groups = [];
		if (!resp) return groups;
		if (resp.coordinate) groups.push({ key: 'coordinate', items: [resp.coordinate] });
		if (resp.regions && resp.regions.length) groups.push({ key: 'regions', items: resp.regions });
		if (resp.places && resp.places.length) groups.push({ key: 'places', items: resp.places });
		if (resp.records && resp.records.length) groups.push({ key: 'records', items: resp.records });
		return groups;
	}

	/* Viewport (bbox) search params: exact bounds verbatim, no rounding. */
	function buildBboxParams(bounds, state) {
		const params = {
			min_lat: String(bounds.min_lat),
			min_lon: String(bounds.min_lon),
			max_lat: String(bounds.max_lat),
			max_lon: String(bounds.max_lon),
			limit: (state && state.limit) || 25,
		};
		if (state && state.types) params.types = String(state.types);
		return params;
	}

	/* Region payload for a cascade selection — bbox when the dataset has
	 * one, centroid as fallback, chain of every selected ancestor. */
	function cascadePayload(selected, row) {
		const chain = selected
			.filter(Boolean)
			.map((s) => ({ level: s.level, name_en: s.name_en, name_ar: s.name_ar, pcode: s.pcode }));
		return {
			kind: 'region',
			level: row.level,
			level_name: row.level_name,
			name_en: row.name_en,
			name_ar: row.name_ar,
			pcode: row.pcode,
			source: 'registry',
			centroid: row.centroid || [null, null],
			bbox: row.bbox || null,
			chain,
		};
	}

	/* Coordinate detail lines: admin chain, explicitly missing levels,
	 * nearest places with distances (derived metres, 1 dp). */
	function coordinateChains(coord) {
		if (!coord || coord.error) return null;
		const chain = (coord.admin_chain || []).map((lvl) => ({
			level: lvl.level,
			label: (lvl.level_name || '') + ': ' + (lvl.name_en || lvl.name_ar || ''),
		}));
		const missing = (coord.missing_levels || []).slice();
		const nearby = (coord.nearby || []).map((n) => ({
			name: n.name, distance: n.distance, distance_m: n.distance_m,
		}));
		return { chain, missing, nearby, on_land: coord.on_land !== false };
	}

	function regionTitle(r) {
		return (r && (r.name_en || r.name_ar || r.pcode)) || '';
	}

	function placeTitle(r) {
		return (r && (r.name_en || r.name_ar || r.asciiname || r.pcode)) || '';
	}

	function recordTitle(r) {
		return (r && (r.label || r.name)) || '';
	}

	function groupLabel(key, translate) {
		const table = {
			coordinate: __('Coordinates'),
			regions: __('Regions'),
			places: __('Places'),
			records: __('Records'),
		};
		const text = table[key] || key;
		return translate ? translate(text) : text;
	}

	/* ---------- widget ---------- */

	function mount(host, options) {
		const opts = options || {};
		const frappeRef = opts.frappe || root.frappe;
		const onJump = opts.onJump || (() => {});
		if (!host || !frappeRef) return null;

		const wrap = document.createElement('div');
		wrap.className = 'siraj-map-search';
		wrap.setAttribute('role', 'search');

		const row = document.createElement('div');
		row.className = 'sms-row';
		const input = document.createElement('input');
		input.type = 'search';
		input.className = 'form-control input-sm sms-input';
		input.setAttribute('aria-label', __('Advanced map search'));
		input.setAttribute('placeholder', __('Region, place, record or 31.5, 34.47…'));
		input.setAttribute('autocomplete', 'off');
		input.setAttribute('role', 'combobox');
		input.setAttribute('aria-expanded', 'false');
		input.setAttribute('aria-autocomplete', 'list');
		const scopeSel = document.createElement('select');
		scopeSel.className = 'form-control input-sm sms-scope';
		scopeSel.setAttribute('aria-label', __('Search scope'));
		[['all', 'Everything'], ['regions', 'Regions'], ['places', 'Places'],
			['records', 'Records']].forEach(([value, label]) => {
			const opt = document.createElement('option');
			opt.value = value;
			opt.textContent = __(label);
			scopeSel.appendChild(opt);
		});
		row.appendChild(input);
		row.appendChild(scopeSel);
		row.appendChild(bboxBtn);

		const row2 = document.createElement('div');
		row2.className = 'sms-row sms-level-row';
		row2.hidden = true;
		const typeSel = document.createElement('select');
		typeSel.className = 'form-control input-sm sms-types';
		typeSel.setAttribute('aria-label', __('Record type'));
		RECORD_TYPES.forEach(([value, label]) => {
			const opt = document.createElement('option');
			opt.value = value;
			opt.textContent = __(label);
			typeSel.appendChild(opt);
		});
		const levelSel = document.createElement('select');
		levelSel.className = 'form-control input-sm sms-levels';
		levelSel.setAttribute('aria-label', __('Region level'));
		const levelOptions = [
			['', 'All levels'], ['0', 'Country'], ['1', 'Governorate'], ['2', 'District'],
			['3', 'Municipality'], ['4', 'Village'], ['5', 'Community'],
		];
		levelOptions.forEach(([value, label]) => {
			const opt = document.createElement('option');
			opt.value = value;
			opt.textContent = __(label);
			levelSel.appendChild(opt);
		});
		row2.appendChild(levelSel);
		row2.appendChild(typeSel);

		const cascade = document.createElement('div');
		cascade.className = 'sms-cascade';
		cascade.hidden = true;

		const bboxBtn = document.createElement('button');
		bboxBtn.type = 'button';
		bboxBtn.className = 'btn btn-xs btn-default sms-bbox';
		bboxBtn.textContent = __('Search this area');
		bboxBtn.hidden = !opts.getBounds;
		bboxBtn.setAttribute('aria-label', __('Search this area (current map view)'));

		const menu = document.createElement('div');
		menu.className = 'sms-menu';
		menu.setAttribute('role', 'listbox');
		menu.hidden = true;

		const status = document.createElement('div');
		status.className = 'sms-status';
		status.setAttribute('aria-live', 'polite');

		wrap.appendChild(row);
		wrap.appendChild(row2);
		wrap.appendChild(cascade);
		wrap.appendChild(menu);
		wrap.appendChild(status);
		host.appendChild(wrap);

		let timer = null;
		let seq = 0;
		let items = [];
		let active = -1;
		// Cascade: selected[level] = chosen child row; children[level] =
		// loaded options for that level. Level -1 = countries (level 0).
		const selected = {};
		const children = {};
		let cascadeSeq = 0;

		const closeMenu = () => {
			menu.hidden = true;
			input.setAttribute('aria-expanded', 'false');
			active = -1;
		};
		const openMenu = () => {
			menu.hidden = false;
			input.setAttribute('aria-expanded', 'true');
		};

		const setActive = (index) => {
			const nodes = menu.querySelectorAll('.sms-item');
			if (!nodes.length) { active = -1; return; }
			active = ((index % nodes.length) + nodes.length) % nodes.length;
			nodes.forEach((n, i) => n.classList.toggle('is-active', i === active));
			nodes[active].scrollIntoView({ block: 'nearest' });
			input.setAttribute('aria-activedescendant', nodes[active].id || '');
		};

		const fire = (group, item) => {
			closeMenu();
			onJump(group, item);
		};

		const renderItem = (group, item, index) => {
			const el = document.createElement('div');
			el.className = 'sms-item';
			el.id = 'sms-item-' + index;
			el.setAttribute('role', 'option');
			el.dataset.group = group;

			const title = document.createElement('span');
			title.className = 'sms-item-title';
			const sub = document.createElement('span');
			sub.className = 'sms-item-sub';

			if (group === 'coordinate') {
				const disp = coordinateDisplay(item);
				if (disp && disp.error) {
					el.classList.add('sms-item-error');
					title.textContent = coordinateErrorText(disp.error);
					sub.textContent = disp.input;
					if (disp.suggestion) {
						const btn = document.createElement('button');
						btn.type = 'button';
						btn.className = 'btn btn-xs btn-default sms-suggest';
						btn.textContent = __('Use {0}', [disp.suggestion.text]);
						btn.addEventListener('click', (e) => {
							e.stopPropagation();
							input.value = disp.suggestion.text;
							runSearch();
						});
						el.appendChild(title);
						el.appendChild(sub);
						el.appendChild(btn);
						return el;
					}
				} else if (disp) {
					title.textContent = disp.primary;
					const bits = [];
					bits.push(disp.format === 'dms'
						? __('DMS · {0}', [disp.input])
						: __('Exact coordinates'));
					const detail = coordinateChains(item);
					if (detail) {
						if (detail.chain.length) {
							bits.push(detail.chain[detail.chain.length - 1].label);
						}
						if (detail.missing.length) {
							bits.push(__('Missing levels') + ': ' + detail.missing.join(', '));
						}
					}
					sub.textContent = bits.join(' · ');
				}
			} else if (group === 'regions') {
				title.textContent = regionTitle(item);
				const bits = [];
				if (item.level_name) bits.push(__(item.level_name));
				if (item.pcode) bits.push(item.pcode);
				if (item.name_ar && item.name_en) bits.push(item.name_ar);
				sub.textContent = bits.join(' · ');
			} else if (group === 'places') {
				title.textContent = placeTitle(item);
				const bits = [];
				if (item.feature_code) bits.push(item.feature_code);
				if (item.pcode) bits.push(item.pcode);
				if (item.name_ar && item.name_en) bits.push(item.name_ar);
				sub.textContent = bits.join(' · ');
			} else {
				title.textContent = recordTitle(item);
				sub.textContent = item.doctype ? __(item.doctype) : '';
			}
			el.appendChild(title);
			el.appendChild(sub);
			if (group === 'coordinate') {
				const detail = coordinateChains(item);
				if (detail && detail.chain.length) {
					const chainEl = document.createElement('div');
					chainEl.className = 'sms-chain';
					detail.chain.forEach((lvl) => {
						const chip = document.createElement('span');
						chip.className = 'sms-chain-chip';
						chip.textContent = lvl.label;
						chainEl.appendChild(chip);
					});
					el.appendChild(chainEl);
				}
				if (detail && detail.missing.length) {
					const missEl = document.createElement('div');
					missEl.className = 'sms-chain-missing';
					missEl.textContent = __('Missing levels') + ': ' + detail.missing.join(', ');
					el.appendChild(missEl);
				}
				if (detail && detail.nearby.length) {
					const nearEl = document.createElement('ul');
					nearEl.className = 'sms-nearby';
					detail.nearby.slice(0, 5).forEach((n) => {
						const li = document.createElement('li');
						li.textContent = n.name + ' — ' + n.distance + ' m';
						nearEl.appendChild(li);
					});
					el.appendChild(nearEl);
				}
			}
			el.addEventListener('click', () => fire(group, item));
			return el;
		};

		const render = (resp) => {
			const groups = groupResults(resp);
			menu.innerHTML = '';
			items = [];
			if (!groups.length) {
				status.textContent = __('No results for “{0}”', [resp.query || input.value]);
				closeMenu();
				return;
			}
			status.textContent = '';
			let index = 0;
			groups.forEach((group) => {
				const head = document.createElement('div');
				head.className = 'sms-group-head';
				head.textContent = groupLabel(group.key);
				menu.appendChild(head);
				group.items.forEach((item) => {
					menu.appendChild(renderItem(group.key, item, index));
					items.push({ group: group.key, item });
					index += 1;
				});
			});
			openMenu();
			setActive(0);
		};

		function runSearch() {
			const query = input.value;
			if (!shouldSearch(query)) {
				status.textContent = '';
				closeMenu();
				return;
			}
			const mySeq = ++seq;
			const args = buildParams({
				query,
				scope: scopeSel.value,
				levels: scopeSel.value === 'regions' || scopeSel.value === 'all' ? levelSel.value : '',
				types: typeSel.value,
				limit: 8,
			});
			status.textContent = __('Searching…');
			frappeRef.call({
				method: METHOD,
				args,
				callback(r) {
					if (mySeq !== seq) return; // stale response
					const resp = (r && r.message) || {};
					render(resp);
				},
				error() {
					if (mySeq !== seq) return;
					status.textContent = __('Search failed — try again.');
					closeMenu();
				},
			});
		}

		/* ----- region cascade (Country → Community) ----- */
		const LEVEL_NAMES = ['Country', 'Governorate', 'District', 'Municipality', 'Village', 'Community'];
		const orderSelected = () => Object.keys(selected)
			.map(Number).sort((a, b) => a - b).map((k) => selected[k]);

		const renderCascade = () => {
			cascade.innerHTML = '';
			for (let level = 0; level <= 5; level++) {
				if (level > 0 && !selected[level - 1]) break;
				const sel = document.createElement('select');
				sel.className = 'form-control input-sm sms-cascade-select';
				sel.setAttribute('aria-label', __(LEVEL_NAMES[level]));
				const placeholder = document.createElement('option');
				placeholder.value = '';
				placeholder.textContent = level === 0
					? __('Country…')
					: __('Choose {0}…', [__(LEVEL_NAMES[level])]);
				sel.appendChild(placeholder);
				(children[level] || []).forEach((child) => {
					const opt = document.createElement('option');
					opt.value = child.name;
					const label = child.name_en || child.name_ar || child.name || '';
					opt.textContent = child.pcode ? label + ' (' + child.pcode + ')' : label;
					sel.appendChild(opt);
				});
				if (selected[level]) sel.value = selected[level].name;
				sel.addEventListener('change', () => {
					const row = (children[level] || []).find((c) => c.name === sel.value);
					if (!row) {
						delete selected[level];
						for (let d = level + 1; d <= 5; d++) delete selected[d];
						renderCascade();
						return;
					}
					selected[level] = row;
					for (let d = level + 1; d <= 5; d++) delete selected[d];
					// Fly to this selection immediately — each refinement
					// tightens the view with the polygon bbox when available.
					fire('regions', cascadePayload(orderSelected(), row));
					loadChildren(level + 1);
					renderCascade();
				});
				cascade.appendChild(sel);
				if (!selected[level]) break;
			}
		};

		const loadChildren = (level) => {
			if (level > 5) return;
			const mySeq = ++cascadeSeq;
			const args = { level, limit: 200 };
			if (level > 0 && selected[level - 1]) args.parent = selected[level - 1].name;
			frappeRef.call({
				method: CASCADE_METHOD,
				args,
				callback(r) {
					if (mySeq !== cascadeSeq) return;
					children[level] = ((r && r.message) || {}).children || [];
					renderCascade();
				},
			});
		};

		/* ----- viewport ("search this area") ----- */
		bboxBtn.addEventListener('click', () => {
			if (!opts.getBounds) return;
			let bounds = null;
			try { bounds = opts.getBounds(); } catch (e) { bounds = null; }
			if (!bounds) {
				status.textContent = __('Map view unavailable.');
				return;
			}
			const mySeq = ++seq;
			status.textContent = __('Searching this area…');
			frappeRef.call({
				method: BBOX_METHOD,
				args: buildBboxParams(bounds, { types: typeSel.value, limit: 25 }),
				callback(r) {
					if (mySeq !== seq) return;
					const resp = (r && r.message) || {};
					if (resp.error) {
						status.textContent = __('Invalid map view.');
						closeMenu();
						return;
					}
					resp.query = __('this area');
					render(resp);
					if (resp.counts) {
						status.textContent = __('{0} records · {1} places · {2} regions',
							[resp.counts.records, resp.counts.places, resp.counts.regions]);
					}
				},
				error() {
					if (mySeq !== seq) return;
					status.textContent = __('Search failed — try again.');
				},
			});
		});

		/* ----- scope chrome (level / type / cascade visibility) ----- */
		const applyScopeChrome = () => {
			const s = scopeSel.value;
			row2.hidden = !(s === 'all' || s === 'regions' || s === 'records');
			levelSel.hidden = !(s === 'all' || s === 'regions');
			typeSel.hidden = !(s === 'all' || s === 'records');
			const showCascade = (s === 'all' || s === 'regions');
			cascade.hidden = !showCascade;
			if (showCascade && !children[0] && !selected[0]) loadChildren(0);
		};

		input.addEventListener('input', () => {
			clearTimeout(timer);
			timer = setTimeout(runSearch, 300);
		});
		input.addEventListener('keydown', (e) => {
			if (e.key === 'ArrowDown') { e.preventDefault(); if (menu.hidden) runSearch(); else setActive(active + 1); }
			else if (e.key === 'ArrowUp') { e.preventDefault(); if (!menu.hidden) setActive(active - 1); }
			else if (e.key === 'Enter') {
				const nodes = menu.querySelectorAll('.sms-item');
				if (!menu.hidden && active >= 0 && nodes[active]) {
					e.preventDefault();
					nodes[active].click();
				} else { e.preventDefault(); clearTimeout(timer); runSearch(); }
			} else if (e.key === 'Escape') { closeMenu(); status.textContent = ''; }
		});
		scopeSel.addEventListener('change', () => {
			applyScopeChrome();
			if (input.value.trim().length >= MIN_CHARS) runSearch();
		});
		levelSel.addEventListener('change', () => {
			if (scopeSel.value === 'regions' || scopeSel.value === 'all') runSearch();
		});
		typeSel.addEventListener('change', () => {
			if (input.value.trim().length >= MIN_CHARS) runSearch();
		});
		applyScopeChrome();
		// Keep focus (and the menu) alive while clicking an item: plain
		// mousedown would blur the input and close the menu first.
		menu.addEventListener('mousedown', (e) => e.preventDefault());
		input.addEventListener('blur', () => setTimeout(closeMenu, 150));

		return { input, scopeSel, levelSel, runSearch, closeMenu };
	}

	const api = {
		MIN_CHARS,
		RECORD_TYPES,
		buildParams,
		buildBboxParams,
		cascadePayload,
		coordinateChains,
		shouldSearch,
		coordinateDisplay,
		coordinateErrorText,
		groupResults,
		regionTitle,
		placeTitle,
		recordTitle,
		groupLabel,
		mount,
	};
	if (typeof module !== 'undefined' && module.exports) module.exports = api;
	else root.SirajMapSearch = api;
})(typeof window !== 'undefined' ? window : globalThis);
