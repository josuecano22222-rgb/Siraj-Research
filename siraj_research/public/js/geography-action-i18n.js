/* Localize DocType Action dropdowns that Frappe can render from raw metadata.
 * Core normally translates action labels, but some v15 builds leave the action
 * group and item text untouched when rebuilding the inner toolbar.
 */
(() => {
	'use strict';

	const DOCTYPES = ['Person', 'Institution', 'Place', 'Research Event'];
	const GROUP = 'Geography';
	const ACTION = 'Open geographic explorer';

	function replaceButtonText(button, text) {
		if (!button) return;
		const textNode = Array.from(button.childNodes).find(node => node.nodeType === Node.TEXT_NODE);
		if (textNode) textNode.nodeValue = `\n\t\t\t\t\t\t${text}\n\t\t\t\t\t\t`;
		else button.prepend(document.createTextNode(text));
		button.setAttribute('aria-label', text);
	}

	function localizeGeographyAction(frm) {
		if (!frm || !frm.page || !frm.page.wrapper) return;
		const root = frm.page.wrapper.jquery ? frm.page.wrapper[0] : frm.page.wrapper;
		if (!root) return;

		const encodedAction = encodeURIComponent(ACTION);
		const action = root.querySelector(`a.dropdown-item[data-label="${encodedAction}"]`);
		if (!action) return;

		action.textContent = __(ACTION);
		action.setAttribute('aria-label', __(ACTION));
		const dropdown = action.closest('.dropdown');
		if (dropdown) replaceButtonText(dropdown.querySelector('button.dropdown-toggle'), __(GROUP));
	}

	function scheduleLocalization(frm) {
		// Frappe may rebuild DocType actions just after refresh; cover both the
		// immediate render and delayed toolbar refresh without a permanent observer.
		[0, 100, 400].forEach(delay => setTimeout(() => localizeGeographyAction(frm), delay));
	}

	DOCTYPES.forEach(doctype => {
		frappe.ui.form.on(doctype, {
			refresh: scheduleLocalization,
		});
	});

	window.SirajGeographyActionI18n = { localizeGeographyAction };
})();
