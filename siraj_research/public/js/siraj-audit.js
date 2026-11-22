// SIRAJ audit view — formatted Frappe Version history for records the
// current user may read. Loaded app-wide via app_include_js: entity forms
// get a "History" button, and the Explorer inspector opens the same dialog
// through window.sirajAudit. Server side: siraj_research.api.audit.
(function () {
	'use strict';

	const ENTITY_DOCTYPES = [
		'Person', 'Institution', 'Place', 'Research Event', 'Siraj Event',
		'Military Unit', 'Source', 'Relationship', 'Operational Deployment'
	];

	const when = value => (value && frappe.datetime.str_to_user ? frappe.datetime.str_to_user(value) : (value || ''));

	function renderChange(change, body) {
		const row = $('<div class="sx-audit-change"></div>').appendTo(body);
		$('<span class="sx-audit-field"></span>')
			.text(change.label || change.field)
			.appendTo(row);
		const diff = $('<span class="sx-audit-diff"></span>').appendTo(row);
		const hasOld = change.old !== '' && change.old !== null && change.old !== undefined;
		const hasNew = change.new !== '' && change.new !== null && change.new !== undefined;
		if (hasOld) $('<del class="sx-audit-old"></del>').attr('dir', 'auto').text(String(change.old)).appendTo(diff);
		if (hasOld && hasNew) $('<span class="sx-audit-arrow"> → </span>').appendTo(diff);
		if (hasNew) $('<ins class="sx-audit-new"></ins>').attr('dir', 'auto').text(String(change.new)).appendTo(diff);
	}

	function renderEntry(entry, body) {
		const card = $('<div class="sx-audit-entry"></div>').appendTo(body);
		const head = $('<div class="sx-audit-head"></div>').appendTo(card);
		$('<span class="sx-audit-when"></span>').text(when(entry.when)).appendTo(head);
		if (entry.by) $('<span class="sx-audit-by"></span>').text(entry.by).appendTo(head);
		$('<span class="sx-audit-action"></span>')
			.text(entry.action === 'created' ? __('Created') : __('Updated'))
			.appendTo(head);
		const changes = entry.changes || [];
		if (changes.length) {
			const list = $('<div class="sx-audit-changes"></div>').appendTo(card);
			changes.forEach(change => renderChange(change, list));
		}
	}

	async function open(doctype, name) {
		let message = null;
		try {
			const res = await frappe.call({
				method: 'siraj_research.api.audit.document_history',
				args: { doctype: doctype, name: name, limit: 100 }
			});
			message = res && res.message;
		} catch (error) {
			console.error('[SIRAJ audit] history failed:', error);
			frappe.msgprint(__('Unable to load the change history for this record.'));
			return;
		}
		const history = (message && message.history) || [];
		const dialog = new frappe.ui.Dialog({
			title: __('Change history: {0}', [name]),
			fields: [{ fieldtype: 'HTML', fieldname: 'body' }],
			primary_action_label: __('Close'),
			primary_action: function () { dialog.hide(); }
		});
		const body = $(dialog.fields_dict.body.wrapper).empty();
		if (!history.length) {
			$('<p class="text-muted" style="margin:8px 0"></p>').text(__('No recorded changes.')).appendTo(body);
		} else {
			history.forEach(entry => renderEntry(entry, body));
		}
		dialog.show();
		return history;
	}

	function attachFormButton(frm) {
		if (!frm.doc || frm.doc.__islocal) return;
		frm.clear_custom_buttons();
		frm.add_custom_button(__('History'), function () {
			open(frm.doctype, frm.doc.name);
		});
	}

	ENTITY_DOCTYPES.forEach(function (doctype) {
		frappe.ui.form.on(doctype, {
			refresh: attachFormButton
		});
	});

	window.sirajAudit = { open: open, doctypes: ENTITY_DOCTYPES };
})();
