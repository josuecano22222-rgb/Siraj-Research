/* Global SIRAJ list/link avatar hook.
 *
 * After any list view renders, swap the leading Frappe "avatar" (coloured dot
 * with initials) for our doctype-specific glyph swatch. The same registry
 * drives map pins, graph nodes and form indicators.
 */
(() => {
	'use strict';

	function colour(name) { return (window.sirajColours && window.sirajColours[name]) || '#6a7a7e'; }

	function avatarHtml(doctype, size) {
		if (!window.sirajIcons) return '';
		const s = size || 24;
		return `<span class="siraj-list-avatar" style="background:${colour(doctype)}" title="${doctype}">${window.sirajIcons.svg(doctype, {size: Math.round(s*0.6)})}</span>`;
	}

	function decorateList() {
		$('.list-row-container').each((_, row) => {
			const $row = $(row);
			if ($row.data('sirajAvatared')) return;
			// Frappe list rows store the doctype on the list view; pull from URL.
			const doctype = (frappe.get_route && frappe.get_route()[0] === 'List') ? frappe.get_route()[1] : null;
			if (!doctype || !window.sirajColours[doctype]) return;
			$row.find('.list-subject, .list-id, a[id^="list"]').first().each((_, el) => {
				const $el = $(el);
				if ($el.find('.siraj-list-avatar').length) return;
				$el.prepend(avatarHtml(doctype, 22));
			});
			$row.data('sirajAvatared', true);
		});
	}

	function decorateForm() {
		// Add a tiny coloured glyph indicator next to the form title bar.
		if (!$('.form-dashboard-section').length && !$('.siraj-form-indicator').length) {
			const doctype = cur_frm && cur_frm.doctype;
			if (doctype && window.sirajColours[doctype] && cur_frm.docid) {
				const $bar = $('.form-page .title-area, .form-dashboard .title-text').first();
				if ($bar.length) {
					const ind = $('<span class="siraj-form-indicator"></span>')
						.css('background', colour(doctype))
						.html(window.sirajIcons.svg(doctype, {size: 12}) + '&nbsp;' + __(doctype));
					$bar.append(ind);
				}
			}
		}
	}

	$(document).on('render_listview_rows_loaded list_sorting list_filter', () => setTimeout(decorateList, 10));
	$(document).on('form_refresh', () => setTimeout(decorateForm, 50));
})();
