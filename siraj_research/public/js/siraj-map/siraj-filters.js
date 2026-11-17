/* siraj-filters.js — engine-neutral shared filter state.
 *
 * Single source of truth for which entity types, relationship types, statuses,
 * provenance flags and text query are active across all map surfaces
 * (Geographic, Relationship, Structures, records panel, ego overlay, native
 * list Map view). Pure reducer with Node tests; Leaflet/MapLibre adapters
 * subscribe via the small event bus below.
 *
 * IMPORTANT: We do NOT write to location.hash. Frappe's Desk router owns the
 * hash (history routing under /app/...); writing our state there causes
 * "Page not found" errors on reload. Persistence is per-user localStorage
 * (namespaced by user and page). A one-shot migration strips the old
 * broken "#sf=..." hash from the URL so existing bookmarks still load.
 *
 * Exposed as window.SirajFilters.
 */
(function () {
	'use strict';

	const STORAGE_KEY_PREFIX = 'siraj.filter.v1.';
	const LEGACY_HASH_KEY = 'sf';  // removed; only used for migration

	/* ---------- Preset registry (data, not code) ---------- */
	const BUILTIN_PRESETS = [
		{ id:'all',         label:__('All types'),               types:null, relTypes:null, isBuiltin:true },
		{ id:'people',      label:__('People'),                  types:['Person'] },
		{ id:'inst',        label:__('Institutions'),            types:['Institution'] },
		{ id:'ppl_inst',    label:__('People + Institutions'),   types:['Person','Institution'] },
		{ id:'military',    label:__('Military'),                types:['Military Unit','Operational Deployment','Mission','Training Exercise','Military Division','Command Region'] },
		{ id:'places',      label:__('Places'),                  types:['Place'] },
		{ id:'events',      label:__('Events and operations'),   types:['Research Event','Operational Deployment','Mission','Training Exercise'] },
		{ id:'sources',     label:__('Sources'),                 types:['Source'] },
	];

	/* ---------- Arabic / English text normalisation ---------- */
	function normaliseText(s) {
		if (s == null) return '';
		return String(s).toLowerCase()
			.replace(/[\u064B-\u065F\u0670]/g, '')          // remove harakat / diacritics
			.replace(/[إأٱآا]/g, 'ا')                        // alef variants
			.replace(/ة/g, 'ه')                              // ta marbuta → ha
			.replace(/[ىي]/g, 'ي')                           // ya / alef maqsura
			.replace(/\s+/g, ' ')
			.trim();
	}

	/* ---------- Initial state ---------- */
	function initialState(allTypes, page) {
		// allTypes: string[] of DocType names currently in the registry.
		const types = {};
		(allTypes || []).forEach(t => { types[t] = true; });
		const defaults = {
			types,
			relTypes: {},
			statuses: {},
			provenance: { direct: true, inferred: true, unmapped: false },
			dateFrom: null,
			dateTo:   null,
			search: '',
			presets: loadUserPresets(page),
			activePreset: 'all',
			includeHiddenConnectors: true,
			includeUnlocated: false,
		};
		const saved = loadState(page, allTypes);
		if (saved) return Object.assign(defaults, saved, { types: Object.assign(types, saved.types || {}) });
		return defaults;
	}

	function storageKey(page) { return STORAGE_KEY_PREFIX + (page || 'default'); }
	function loadUserPresets(page) {
		try {
			const raw = (typeof localStorage !== 'undefined' && localStorage.getItem(storageKey(page) + '.presets'));
			return raw ? JSON.parse(raw) : {};
		} catch (_) { return {}; }
	}
	function saveUserPresets(presets, page) {
		try { if (typeof localStorage !== 'undefined') localStorage.setItem(storageKey(page) + '.presets', JSON.stringify(presets)); } catch (_) {}
	}
	function loadState(page, allTypes) {
		try {
			const raw = typeof localStorage !== 'undefined' && localStorage.getItem(storageKey(page));
			if (!raw) return null;
			const parsed = JSON.parse(raw);
			if (!parsed || typeof parsed !== 'object' || !parsed.types) return null;
			// Fill any new DocTypes that appeared since save (default-on).
			(allTypes||[]).forEach(t => { if (!(t in parsed.types)) parsed.types[t] = true; });
			return parsed;
		} catch (_) { return null; }
	}
	function saveState(state, page) {
		try { if (typeof localStorage !== 'undefined') localStorage.setItem(storageKey(page), JSON.stringify(state)); } catch (_) {}
	}
	/* Strip a stale legacy "#sf=..." hash from the URL without reloading. This
	 * is defensive for bookmarks created while the buggy version was live. */
	function migrateLegacyHash() {
		try {
			if (typeof window === 'undefined' || !window.location || !window.history) return;
			const h = window.location.hash || '';
			if (!h) return;
			const re = new RegExp('&?' + LEGACY_HASH_KEY + '=[^&]*', 'g');
			if (!re.test(h)) return;
			const stripped = h.replace(re, '').replace(/^#&?/, '#').replace(/#$/,'');
			window.history.replaceState(null, '', window.location.pathname + window.location.search + (stripped === '#' ? '' : stripped));
		} catch (_) {}
	}

	/* ---------- Reducer (pure; returns new state) ---------- */
	function reduce(state, action) {
		const s = cloneState(state);
		switch (action.type) {
			case 'SET_TYPES':            // {types:{...}}
				Object.keys(s.types).forEach(k => { s.types[k] = false; });
				(action.types || []).forEach(t => { s.types[t] = true; });
				s.activePreset = null; break;
			case 'TOGGLE_TYPE':          // {doctype}
				s.types[action.doctype] = !s.types[action.doctype];
				s.activePreset = null; break;
			case 'SELECT_ALL_TYPES':
				Object.keys(s.types).forEach(k => { s.types[k] = true; });
				s.activePreset = 'all'; break;
			case 'SELECT_NONE_TYPES':
				Object.keys(s.types).forEach(k => { s.types[k] = false; });
				s.activePreset = null; break;
			case 'INVERT_TYPES':
				Object.keys(s.types).forEach(k => { s.types[k] = !s.types[k]; });
				s.activePreset = null; break;
			case 'TOGGLE_RELTYPE':
				s.relTypes[action.relType] = s.relTypes[action.relType] === false ? true : !s.relTypes[action.relType] ? false : false;
				break;
			case 'SET_RELTYPES':
				s.relTypes = {};
				(action.relTypes || []).forEach(t => { s.relTypes[t] = true; }); break;
			case 'TOGGLE_STATUS':
				s.statuses[action.status] = s.statuses[action.status] === false; break;
			case 'SET_PROVENANCE':       // {key, value}
				if (action.key in s.provenance) s.provenance[action.key] = !!action.value;
				break;
			case 'SET_DATE_RANGE':
				s.dateFrom = action.from || null; s.dateTo = action.to || null; break;
			case 'SET_SEARCH':
				s.search = action.value || ''; break;
			case 'APPLY_PRESET': {
				const preset = BUILTIN_PRESETS.find(p => p.id === action.id) || s.presets[action.id];
				if (!preset) break;
				if (preset.types === null) Object.keys(s.types).forEach(k => { s.types[k] = true; });
				else {
					Object.keys(s.types).forEach(k => { s.types[k] = false; });
					preset.types.forEach(t => { if (t in s.types) s.types[t] = true; });
				}
				if (preset.relTypes === null) Object.keys(s.relTypes).forEach(k => { s.relTypes[k] = true; });
				else if (preset.relTypes) {
					Object.keys(s.relTypes).forEach(k => { s.relTypes[k] = false; });
					preset.relTypes.forEach(t => { s.relTypes[t] = true; });
				}
				s.activePreset = preset.id; break;
			}
			case 'SAVE_PRESET': {
				s.presets[action.id] = { id: action.id, label: action.label, types: Object.keys(s.types).filter(t=>s.types[t]), relTypes: Object.keys(s.relTypes).filter(t=>s.relTypes[t]) };
				saveUserPresets(s.presets); s.activePreset = action.id; break;
			}
			case 'DELETE_PRESET':
				delete s.presets[action.id]; saveUserPresets(s.presets);
				if (s.activePreset === action.id) s.activePreset = 'all';
				break;
			case 'TOGGLE_HIDDEN_CONNECTORS':
				s.includeHiddenConnectors = !s.includeHiddenConnectors; break;
			case 'TOGGLE_UNLOCATED':
				s.includeUnlocated = !s.includeUnlocated; break;
			case 'SET_AVAILABLE_TYPES': {
				// Add any new DocTypes that appeared in data but not in state; default-on.
				(action.types||[]).forEach(t => { if (!(t in s.types)) s.types[t] = true; }); break;
			}
			case 'SET_AVAILABLE_RELTYPES':
				(action.relTypes||[]).forEach(t => { if (!(t in s.relTypes)) s.relTypes[t] = true; }); break;
			case 'RESTORE':               // {state} full replace (e.g. URL hash)
				return cloneState(action.state);
			default: return state;
		}
		return s;
	}

	function cloneState(s) {
		return {
			types: Object.assign({}, s.types),
			relTypes: Object.assign({}, s.relTypes),
			statuses: Object.assign({}, s.statuses),
			provenance: Object.assign({}, s.provenance),
			dateFrom: s.dateFrom, dateTo: s.dateTo,
			search: s.search,
			presets: Object.assign({}, s.presets),
			activePreset: s.activePreset,
			includeHiddenConnectors: s.includeHiddenConnectors,
			includeUnlocated: s.includeUnlocated,
		};
	}

	/* ---------- Selectors ---------- */
	function isTypeVisible(state, doctype) { return state.types[doctype] !== false; }
	function isRelTypeVisible(state, relType) { return state.relTypes[relType] !== false; }
	function isStatusVisible(state, status) {
		const anyActive = Object.values(state.statuses).some(v => v);
		if (!anyActive) return true;
		return !!state.statuses[status];
	}
	function visibleTypes(state) { return Object.keys(state.types).filter(t => state.types[t]); }
	function visibleRelTypes(state) { return Object.keys(state.relTypes).filter(t => state.relTypes[t] !== false); }
	function typeCount(state) { return Object.keys(state.types).length; }
	function visibleTypeCount(state) { return visibleTypes(state).length; }
	function matchesSearch(state, text) {
		const q = normaliseText(state.search);
		if (!q) return true;
		return normaliseText(text).indexOf(q) >= 0;
	}
	/* Should an edge be drawn given the current filter and its endpoint visibility?
	 * If either endpoint is hidden and includeHiddenConnectors is false → hide.
	 * If both endpoints are visible but relType is off → hide.
	 */
	function isEdgeVisible(state, edge, aType, bType) {
		if (!isRelTypeVisible(state, edge.type || edge.kind || null)) return false;
		const aVis = isTypeVisible(state, aType);
		const bVis = isTypeVisible(state, bType);
		if (aVis && bVis) return true;
		if (!aVis && !bVis) return false;
		return !!state.includeHiddenConnectors;
	}

	/* ---------- URL-hash round trip (sharable; types only, no secrets) ---------- */
	function encodeHash(state) {
		const vt = visibleTypes(state).join(',');
		return btoa(unescape(encodeURIComponent(vt))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
	}
	function decodeHash(str) {
		if (!str) return null;
		try {
			const b = str.replace(/-/g,'+').replace(/_/g,'/');
			const pad = b.length % 4 ? '='.repeat(4 - (b.length % 4)) : '';
			const types = decodeURIComponent(escape(atob(b+pad))).split(',').filter(Boolean);
			if (!types.length) return null;
			const o = {}; types.forEach(t => { o[t] = true; });
			return { types: o, relTypes:{}, statuses:{}, provenance:{direct:true,inferred:true,unmapped:false},
				dateFrom:null,dateTo:null,search:'',presets:{},activePreset:null,
				includeHiddenConnectors:true, includeUnlocated:false };
		} catch(_) { return null; }
	}

	/* ---------- Tiny event bus (subscribe only) ---------- */
	function createStore(initial) {
		let state = initial;
		const subs = new Set();
		return {
			get: () => state,
			dispatch: (action) => { state = reduce(state, action); subs.forEach(fn => { try { fn(state, action); } catch(e) { console.error('[SIRAJ filter] subscriber failed:', e); } }); },
			subscribe: fn => { subs.add(fn); return () => subs.delete(fn); },
		};
	}

	/* ---------- Count aggregation (used by filter chips / active-filter bar) ---------- */
	function countByType(points) {
		const c = {};
		(points||[]).forEach(p => { const t = p.doctype; c[t] = (c[t]||0)+1; });
		return c;
	}
	function countByRelType(edges) {
		const c = {};
		(edges||[]).forEach(e => { const t = e.type || __('Structural'); c[t] = (c[t]||0)+1; });
		return c;
	}

	window.SirajFilters = {
		BUILTIN_PRESETS,
		initialState, reduce,
		isTypeVisible, isRelTypeVisible, isStatusVisible, isEdgeVisible,
		visibleTypes, visibleRelTypes, visibleTypeCount, typeCount,
		matchesSearch, normaliseText,
		createStore, countByType, countByRelType,
		saveState, migrateLegacyHash,
	};
})();
