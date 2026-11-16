/* Global SIRAJ icon / colour decorator.
 *
 * Every surface that shows a record — list rows, form titles, link-field
 * autocomplete dropdowns, breadcrumbs, dashboard shortcut cards, and printed
 * views — gets its doctype glyph + colour from the single source of truth
 * (window.sirajIcons / window.sirajColours) so a Person, Place, Unit or
 * Event looks identical everywhere.
 *
 * Decorators are event-driven (MutationObserver + Frappe events) so they keep
 * working as the DOM swaps out lists, popups and dashboards.
 */
(() => {
	'use strict';

	function colour(doctype) { return (window.sirajColours && window.sirajColours[doctype]) || '#6a7a7e'; }
	function swatch(doctype, size) {
		if (!window.sirajIcons) return '';
		const s = size || 18;
		return `<span class="siraj-list-avatar" style="background:${colour(doctype)};width:${s}px;height:${s}px" data-doctype="${doctype}">${window.sirajIcons.svg(doctype,{size:Math.round(s*0.6)})}</span>`;
	}

	/* 1) List rows — glyph avatar in front of the subject cell. */
	function decorateList() {
		$('.list-row-container').each((_, row) => {
			const $row = $(row);
			if ($row.data('sirajAvatared')) return;
			const doctype = (frappe.get_route && frappe.get_route()[0] === 'List') ? frappe.get_route()[1] : null;
			if (!doctype || !window.sirajColours || !window.sirajColours[doctype]) return;
			$row.find('.list-subject, .list-id, a[id^="list"]').first().each((_, el) => {
				const $el = $(el);
				if ($el.find('.siraj-list-avatar').length) return;
				$el.prepend(swatch(doctype, 20));
			});
			$row.data('sirajAvatared', true);
		});
	}

	/* 2) Form title bar — coloured glyph pill. */
	function decorateForm() {
		if ($('.siraj-form-indicator').length) return;
		const doctype = cur_frm && cur_frm.doctype;
		if (!doctype || !window.sirajColours || !window.sirajColours[doctype]) return;
		if (!cur_frm.docid && !cur_frm.docname) return;
		const $bar = $('.form-page .title-area, .form-dashboard .title-text, .form-header .title-text').first();
		if (!$bar.length) return;
		$('<span class="siraj-form-indicator"></span>')
			.css('background', colour(doctype))
			.html(window.sirajIcons.svg(doctype, {size:12}) + '&nbsp;' + __(doctype))
			.appendTo($bar);
	}

	/* 3) Link-field autocomplete / awesomplete results — doctype swatch per row. */
	function decorateAwesomplete() {
		$('.awesomplete ul li, .link-field ul li, ul[data-fieldtype="Link"] li').each((_, li) => {
			const $li = $(li);
			if ($li.data('sirajLinked')) return;
			// Traverse up to find the field wrapper and read the options=doctype.
			const wrap = $li.closest('[data-fieldtype="Link"], .link-field, .awesomplete');
			let dt = null;
			if (wrap.length) {
				const inp = wrap.prev('input') || wrap.find('input[data-fieldtype="Link"]');
				if (inp.length) dt = inp.attr('data-options') || inp.data('options');
			}
			if (!dt) return;
			if (!window.sirajColours[dt]) return;
			$li.prepend(swatch(dt, 16));
			$li.data('sirajLinked', true);
		});
	}

	/* 4) Breadcrumbs in the Desk header — add the doctype glyph. */
	function decorateBreadcrumbs() {
		$('.breadcrumb a, .breadcrumb-bar a, .form-breadcrumbs a').each((_, a) => {
			const $a = $(a);
			if ($a.data('sirajBreadcrumb')) return;
			// hrefs look like /app/doctype/name
			const href = $a.attr('href') || '';
			const m = href.match(/\/app\/([a-z0-9_-]+)(?:\/|$)/i);
			if (!m) return;
			const slug = m[1];
			const dt = slug.split(/[-_]/).map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ').replace(/ /g,'');
			// Many slugs map to DocType names (Person, Institution, Place…). Use a fuzzy match.
			const matched = Object.keys(window.sirajColours || {}).find(k => k.toLowerCase().replace(/\s+/g,'') === dt.toLowerCase()) ||
							Object.keys(window.sirajColours || {}).find(k => k.toLowerCase().replace(/\s+/g,'').startsWith(dt.toLowerCase().slice(0,5)));
			if (matched) {
				$a.css({display:'inline-flex',alignItems:'center',gap:'4px'}).prepend(swatch(matched, 14));
				$a.data('sirajBreadcrumb', matched);
			}
		});
	}

	/* 5) Dashboard / number cards / shortcut cards — colour the icon tile by DocType if we can guess. */
	function decorateDashboard() {
		$('.shortcut-card, .number-card, .widget.shortcut').each((_, card) => {
			const $card = $(card);
			if ($card.data('sirajCarded')) return;
			const $link = $card.find('a[href*="/app/"]').first();
			if (!$link.length) return;
			const href = $link.attr('href') || '';
			const m = href.match(/\/app\/([a-z0-9_-]+)/i);
			if (!m) return;
			const slug = m[1];
			const dt = Object.keys(window.sirajColours || {}).find(k => k.toLowerCase().replace(/\s+/g,'') === slug.toLowerCase()) ||
					   Object.keys(window.sirajColours || {}).find(k => k.toLowerCase().replace(/\s+/g,'').startsWith(slug.toLowerCase().slice(0,5)));
			if (!dt) return;
			$card.find('.widget-icon, .card-icon, .shortcut-icon').each((_, icon) => {
				// Replace the widget-icon's background with our glyph.
				$(icon).css({background: colour(dt), color:'#fff', border:0})
					.html(window.sirajIcons.svg(dt, {size:18}));
			});
			$card.data('sirajCarded', true);
		});
	}

	function all() {
		try { decorateList(); } catch (_) {}
		try { decorateForm(); } catch (_) {}
		try { decorateAwesomplete(); } catch (_) {}
		try { decorateBreadcrumbs(); } catch (_) {}
		try { decorateDashboard(); } catch (_) {}
	}

	// Run on every Frappe re-render event we know about.
	$(document).on('render_listview_rows_loaded list_sorting list_filter form_refresh page_change awesomplete_open awesomplete-select awesomplete-close', () => setTimeout(all, 20));
	// Also run on DOM mutation to catch dashboards and autocomplete popups that don't fire events.
	if (window.MutationObserver) {
		const obs = new MutationObserver(() => {
			// Throttle with rAF.
			if (obs._pending) return; obs._pending = true;
			requestAnimationFrame(() => { obs._pending = false; all(); });
		});
		obs.observe(document.body, { childList:true, subtree:true });
	}
	setTimeout(all, 200);
})();
