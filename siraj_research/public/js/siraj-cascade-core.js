/* Pure cascade helpers shared by Desk forms and Node regression tests.
 *
 * No Frappe, jQuery or DOM access here. The index is built from the same
 * same-origin geo package the offline worker uses, so the chain remains
 * available when the browser cannot reach even the local API.
 */
(function (root) {
	'use strict';
	const LEVELS = [
		{ level: 0, field: 'country', doctype: 'Country', parent: null },
		{ level: 1, field: 'governorate', doctype: 'Governorate', parent: 'country' },
		{ level: 2, field: 'district', doctype: 'District', parent: 'governorate' },
		{ level: 3, field: 'municipality', doctype: 'Municipality', parent: 'district' },
		{ level: 4, field: 'village', doctype: 'Village', parent: 'municipality' },
		{ level: 5, field: 'community', doctype: 'Community', parent: 'village' },
	];
	const FIELDS = LEVELS.map(s => s.field);
	const indexOfField = field => FIELDS.indexOf(String(field || ''));

	function optionFromRecord(field, rec) {
		const r = rec || {};
		const value = r.linked_name || r.name || r.pcode || '';
		const label_en = r.name_en || '';
		const label_ar = r.name_ar || '';
		return {
			value, label: label_en || label_ar || value,
			label_en: label_en || value, label_ar: label_ar || label_en || value,
			code: r.pcode || '', pcode: r.pcode || '',
			doctype: (LEVELS[indexOfField(field)] || {}).doctype || '',
		};
	}

	function buildIndex(pkg) {
		const byPcode = Object.create(null);
		const children = Object.create(null);
		const countries = Object.create(null);
		for (const field of FIELDS) children[field] = Object.create(null);
		for (const row of ((pkg && pkg.polygons) || [])) {
			const level = Number(row[0]) | 0;
			if (level < 0 || level >= LEVELS.length) continue;
			const rec = {
				level,
				field: LEVELS[level].field,
				pcode: String(row[1] || ''),
				parent_pcode: String(row[2] || ''),
				name_en: String(row[3] || ''),
				name_ar: String(row[4] || ''),
				linked_name: String(row[6] || ''),
				country: String(row[7] || ''),
			};
			if (!rec.pcode) continue;
			byPcode[rec.pcode] = rec;
			if (rec.country) countries[rec.country] = { value: rec.country, label: rec.country, label_ar: rec.country, code: rec.country, pcode: '', doctype: 'Country' };
			const parentField = LEVELS[level].parent;
			if (parentField && rec.parent_pcode) {
				const bucket = children[parentField][rec.parent_pcode] || (children[parentField][rec.parent_pcode] = []);
				bucket.push(rec);
			}
		}
		return { byPcode, children, countries, version: (pkg && pkg.version) || 0, dataset: (pkg && pkg.dataset) || '' };
	}

	function ancestorFilters(field, values) {
		const index = indexOfField(field);
		if (index <= 0) return {};
		const filters = {};
		for (let i = 1; i <= index; i++) {
			const parent = LEVELS[i].parent;
			const value = values[parent];
			if (value !== undefined && value !== null && value !== '' && value !== false) filters[parent] = value;
		}
		return filters;
	}

	function chainFromRecord(field, value, index) {
		const idx = index || buildIndex(null);
		const chain = Object.create(null);
		for (const f of FIELDS) chain[f] = { value: '', label: '', label_ar: '', label_en: '', code: '', pcode: '', doctype: (LEVELS[indexOfField(f)] || {}).doctype || '' };
		const level = indexOfField(field);
		if (level < 0) return chain;
		let rec = idx.byPcode[String(value || '')];
		if (!rec) {
			// A linked DocType name may differ from its pcode. Try the visible
			// value as a fallback when the package still carries a pcode.
			rec = Object.values(idx.byPcode).find(r => r.linked_name === String(value || '')) || null;
		}
		let country = rec && rec.country;
		for (let i = level; i >= 0 && rec; i--) {
			const spec = LEVELS[i];
			chain[spec.field] = optionFromRecord(spec.field, rec);
			if (rec.country) country = rec.country;
			rec = spec.parent ? idx.byPcode[rec.parent_pcode] : null;
		}
		if (country && !chain.country.value) {
			chain.country = { value: country, label: country, label_ar: country, label_en: country, code: country, pcode: '', doctype: 'Country' };
		}
		return chain;
	}

	function optionsFor(field, values, index) {
		const idx = index || buildIndex(null);
		const level = indexOfField(field);
		if (level < 0) return [];
		const byLabel = (a, b) => String(a.label).localeCompare(String(b.label));
		if (level === 0) {
			return Object.values(idx.countries).sort(byLabel);
		}
		const parentField = LEVELS[level].parent;
		const parentValue = values[parentField];
		if (!parentValue) {
			// No ancestor chosen yet: expose every place at this level so the
			// user can search globally, then back-fill higher fields on pick.
			return Object.values(idx.byPcode)
				.filter(rec => rec.level === level)
				.map(rec => optionFromRecord(field, rec))
				.sort(byLabel);
		}
		const parentRec = idx.byPcode[String(parentValue)] || Object.values(idx.byPcode).find(r => r.linked_name === String(parentValue));
		// Country rows are not in the package; level-1 polygons point at the
		// Country code directly in their parent_pcode.
		const parentPcode = parentField === 'country' ? String(parentValue) : (parentRec && parentRec.pcode);
		if (!parentPcode) {
			// Parent chosen but not present in the offline package: fall back
			// to a global list rather than a dead empty dropdown.
			return Object.values(idx.byPcode)
				.filter(rec => rec.level === level)
				.map(rec => optionFromRecord(field, rec))
				.sort(byLabel);
		}
		const rows = (idx.children[parentField] && idx.children[parentField][parentPcode]) || [];
		return rows.map(rec => optionFromRecord(field, rec)).sort(byLabel);
	}

	const api = { LEVELS, FIELDS, optionFromRecord, buildIndex, ancestorFilters, chainFromRecord, optionsFor };
	root.SirajCascadeCore = api;
	if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
