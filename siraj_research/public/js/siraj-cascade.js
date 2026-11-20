/* Universal hierarchy cascade for every Desk form.
 *
 * Downward: choosing Country filters Governorate (and deeper Links) to the
 * children of that Country, and displays the available next-level values.
 * Upward: choosing District/Municipality/Village/Community reads the selected
 * record's own Link fields and fills all higher levels.
 *
 * The local bench API is authoritative. If it cannot be reached, the same
 * index used by the offline Web Worker provides a same-origin fallback, so
 * the form still cascades without any external network call.
 */
(() => {
	'use strict';
	const core = window.SirajCascadeCore || {};
	const FIELDS = core.FIELDS || ['country', 'governorate', 'district', 'municipality', 'village', 'community'];
	const t = s => (typeof __ === 'function' ? __(s) : s);
	const registered = new Set();
	const lastValue = new WeakMap();

	function state(frm) {
		let s = lastValue.get(frm);
		if (!s) { s = {}; lastValue.set(frm, s); }
		return s;
	}
	function level(field) { return FIELDS.indexOf(String(field || '')); }
	function writable(frm, field) {
		const control = frm && frm.fields_dict && frm.fields_dict[field];
		if (!control) return false;
		return !control.get_status || control.get_status() === 'Write';
	}
	function controlFor(frm, field) {
		return (frm && frm.fields_dict && frm.fields_dict[field]) || null;
	}
	function isLink(frm, field) {
		const c = controlFor(frm, field);
		return !!c && !!c.df && c.df.fieldtype === 'Link';
	}
	function ancestorsFromDoc(doc) {
		const values = {};
		for (const f of FIELDS) if (doc && doc[f]) values[f] = doc[f];
		return values;
	}
	function filters(field, doc) {
		return core.ancestorFilters ? core.ancestorFilters(field, ancestorsFromDoc(doc)) : {};
	}

	function applyQueries(frm) {
		if (!frm || !frm.doc) return;
		for (const field of FIELDS) {
			if (!controlFor(frm, field)) continue;
			const f = filters(field, frm.doc);
			try {
				frm.set_query(field, () => ({ filters: f }));
			} catch (_) { /* read-only or quick-entry control: harmless */ }
		}
	}

	async function offlineCascade(field, value, doc) {
		if (!window.SirajGeo || !window.SirajGeo.ready) return null;
		try {
			const pkg = await window.SirajGeo.ready();
			if (!pkg || !core.buildIndex) return null;
			const idx = core.buildIndex(pkg);
			const chain = value && core.chainFromRecord
				? core.chainFromRecord(field, value, idx)
				: Object.fromEntries(FIELDS.map(f => [f, { value: doc[f] || '', label: doc[f] || '', label_en: doc[f] || '', label_ar: '', code: '', pcode: '', doctype: '' }]));
			const options = core.optionsFor ? core.optionsFor(field, ancestorsFromDoc(doc), idx) : [];
			return { field, value: value || '', chain, filters: filters(field, doc),
				options, source: 'offline-package' };
		} catch (_) { return null; }
	}

	async function fetchCascade(frm, field, value) {
		const doc = frm.doc || {};
		try {
			const args = Object.assign({ field, value: value || null }, ancestorsFromDoc(doc));
			const result = await frappe.xcall('siraj_research.geo_cascade.cascade', args);
			if (result && !result.error) return result;
		} catch (_) { /* offline fallback below */ }
		return offlineCascade(field, value, doc);
	}

	function valueForControl(frm, field, row) {
		if (!row || !row.value) return null;
		return isLink(frm, field) ? row.value : (row.label || row.value);
	}

	function setValues(frm, values) {
		const keys = Object.keys(values);
		if (!keys.length) return;
		try {
			frm.set_value(values);
		} catch (_) {
			keys.forEach(k => { try { frm.set_value(k, values[k]); } catch (__) {} });
		}
	}

	function showDiff(frm, updates, diffs, source) {
		const values = Object.assign({}, updates);
		const d = new frappe.ui.Dialog({
			title: t('Hierarchy selection'),
			fields: [{ fieldtype: 'HTML', fieldname: 'summary' }],
			primary_action_label: t('Replace higher levels'),
			secondary_action_label: t('Keep existing'),
			primary_action() {
				diffs.forEach(x => { values[x.field] = x.proposed; });
				setValues(frm, values);
				d.hide();
			},
		});
		let html = '<p>' + t('The selected place implies different higher-level values:') + '</p><ul>';
		diffs.forEach(x => {
			html += '<li><b>' + frappe.utils.escape_html(x.label) + '</b>: '
				+ frappe.utils.escape_html(String(x.current)) + ' → '
				+ frappe.utils.escape_html(String(x.proposed)) + '</li>';
		});
		html += '</ul><p class="text-muted">'
			+ t('Empty fields are filled either way; source: {0}.', [source || 'local'])
			+ '</p>';
		d.fields_dict.summary.$wrapper.html(html);
		d.show();
	}

	function applyChain(frm, chain, source) {
		const updates = {};
		const diffs = [];
		for (const field of FIELDS) {
			if (!writable(frm, field)) continue;
			const proposed = valueForControl(frm, field, chain && chain[field]);
			if (!proposed) continue;
			const current = frm.doc && frm.doc[field];
			const label = (controlFor(frm, field) || {}).df?.label || field;
			if (!current || String(current) === String(proposed)) updates[field] = proposed;
			else if (String(current) !== String(proposed)) {
				diffs.push({ field, label, current, proposed });
			}
		}
		if (diffs.length) showDiff(frm, updates, diffs, source);
		else setValues(frm, updates);
	}

	function clearDescendants(frm, field) {
		const from = level(field);
		if (from < 0) return;
		const cleared = {};
		for (let i = from + 1; i < FIELDS.length; i++) {
			const f = FIELDS[i];
			if (writable(frm, f) && frm.doc && frm.doc[f]) cleared[f] = '';
		}
		if (Object.keys(cleared).length) setValues(frm, cleared);
	}

	function statusBox(frm) {
		const control = controlFor(frm, 'longitude') || controlFor(frm, 'country');
		if (!control || !control.$wrapper) return $();
		const $section = control.$wrapper.closest('.form-section');
		let $box = $section.find('.siraj-cascade-status').first();
		if (!$box.length) {
			$box = $('<div class="siraj-cascade-status" data-siraj-cascade="1"></div>');
			const $body = $section.find('.section-body').first();
			if ($body.length) $body.append($box); else control.$wrapper.after($box);
		}
		return $box;
	}

	function renderStatus(frm, result) {
		const $box = statusBox(frm);
		if (!$box.length) return;
		$box.empty().attr('data-source', result.source || '');
		const chain = result.chain || {};
		const labels = FIELDS.map(f => {
			const row = chain[f];
			return row && row.value ? (row.label_ar || row.label_en || row.value) : null;
		}).filter(Boolean);
		if (labels.length) {
			$('<div class="siraj-cascade-chain"></div>')
				.text(labels.join(' › ')).appendTo($box);
		}
		const nextField = FIELDS[Math.min(level(result.field) + 1, FIELDS.length - 1)];
		const options = result.options || [];
		if (nextField && nextField !== result.field) {
			const label = (controlFor(frm, nextField) || {}).df?.label || nextField;
			const scoped = result.filters && Object.keys(result.filters).length > 0;
			const scopeNote = scoped ? '' : ' ' + t('(all countries — pick a parent to narrow)');
			$('<div class="siraj-cascade-next"></div>')
				.text(t('{0} available', [options.length]) + ': ' + t(label) + scopeNote)
				.appendTo($box);
			if (options.length) {
				const $chips = $('<div class="siraj-cascade-options"></div>').appendTo($box);
				options.slice(0, 16).forEach(opt => {
					$('<button type="button" class="siraj-cascade-option"></button>')
						.text(opt.label || opt.value)
						.attr('title', opt.value)
						.on('click', () => {
							if (!writable(frm, nextField)) return;
							setValues(frm, { [nextField]: opt.value });
						})
						.appendTo($chips);
				});
				if (options.length > 16) {
					$('<span class="siraj-cascade-more"></span>')
						.text(' +' + (options.length - 16) + ' …').appendTo($chips);
				}
			} else {
				$('<div class="siraj-cascade-gap"></div>')
					.text(scoped
						? t('No matching children in the offline dataset.')
						: t('No rows at this level yet. Import a boundary dataset to populate the hierarchy.'))
					.appendTo($box);
			}
		}
		if (result.source === 'offline-package') {
			$('<div class="siraj-cascade-source"></div>').text(t('offline data')).appendTo($box);
		}
	}

	async function onFieldChange(frm, field) {
		if (!frm || !frm.doc) return;
		if (!writable(frm, field)) return;
		if ((frm._sirajCascadeDepth || 0) > 0) return;
		const value = frm.doc[field] || '';
		const previous = state(frm)[field] || '';
		const changed = value !== previous;
		state(frm)[field] = value;
		frm._sirajCascadeDepth = (frm._sirajCascadeDepth || 0) + 1;
		try {
			if (changed && previous && level(field) >= 0) clearDescendants(frm, field);
			const result = await fetchCascade(frm, field, value);
			if (!result || result.error) return;
			applyChain(frm, result.chain, result.source);
			applyQueries(frm);
			renderStatus(frm, result);
		} finally {
			frm._sirajCascadeDepth = Math.max(0, (frm._sirajCascadeDepth || 1) - 1);
			if (!frm._sirajCascadeDepth) delete frm._sirajCascadeDepth;
		}
	}

	function deepestSelected(doc) {
		for (let i = FIELDS.length - 1; i >= 0; i--) if (doc && doc[FIELDS[i]]) return FIELDS[i];
		return 'country';
	}

	function attach(frm) {
		if (!frm || !frm.doctype) return;
		const fields = FIELDS.filter(f => !!controlFor(frm, f));
		if (!fields.length) return;
		applyQueries(frm);
		if (!registered.has(frm.doctype)) {
			registered.add(frm.doctype);
			const handlers = {
				refresh(f) { setTimeout(() => attach(f), 0); },
			};
			fields.forEach(f => { handlers[f] = form => onFieldChange(form, f); });
			frappe.ui.form.on(frm.doctype, handlers);
		}
		// Restore the chain for documents that already have a selection and
		// show the next-level choices without waiting for another edit.
		const selected = deepestSelected(frm.doc);
		if (frm.doc[selected]) setTimeout(() => onFieldChange(frm, selected), 0);
	}

	$(document).on('form-refresh.sirajCascade', (_e, frm) => {
		if (frm && frm.doctype) setTimeout(() => attach(frm), 0);
	});

	window.SirajCascade = {
		FIELDS, attach, onFieldChange, applyQueries, renderStatus,
		core,
	};
})();
