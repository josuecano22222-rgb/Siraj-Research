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
	const GROUP_KEYS = ['coordinate', 'regions', 'places', 'records'];

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

		const row2 = document.createElement('div');
		row2.className = 'sms-row sms-level-row';
		row2.hidden = true;
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

		const menu = document.createElement('div');
		menu.className = 'sms-menu';
		menu.setAttribute('role', 'listbox');
		menu.hidden = true;

		const status = document.createElement('div');
		status.className = 'sms-status';
		status.setAttribute('aria-live', 'polite');

		wrap.appendChild(row);
		wrap.appendChild(row2);
		wrap.appendChild(menu);
		wrap.appendChild(status);
		host.appendChild(wrap);

		let timer = null;
		let seq = 0;
		let items = [];
		let active = -1;

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
					sub.textContent = disp.format === 'dms'
						? __('DMS · {0}', [disp.input])
						: __('Exact coordinates');
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
			row2.hidden = !(scopeSel.value === 'regions' || scopeSel.value === 'all');
			if (input.value.trim().length >= MIN_CHARS) runSearch();
		});
		levelSel.addEventListener('change', () => {
			if (scopeSel.value === 'regions' || scopeSel.value === 'all') runSearch();
		});
		// Keep focus (and the menu) alive while clicking an item: plain
		// mousedown would blur the input and close the menu first.
		menu.addEventListener('mousedown', (e) => e.preventDefault());
		input.addEventListener('blur', () => setTimeout(closeMenu, 150));

		return { input, scopeSel, levelSel, runSearch, closeMenu };
	}

	const api = {
		MIN_CHARS,
		buildParams,
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
