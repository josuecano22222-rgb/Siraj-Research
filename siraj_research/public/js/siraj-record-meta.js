/* SIRAJ record metadata bootstrap.
 *
 * Reads the record-metadata dict that the server injects into frappe.boot and
 * exposes window.sirajIcons / window.sirajColours from it. All surfaces —
 * maps, network graphs, lists, forms, autocomplete — draw icons and colours
 * from here so there is a single source of truth for "what a Person looks
 * like".
 */
(() => {
	'use strict';

	// Glyphs live on both sides because (a) they're static SVGs, (b) offline
	// printing / email / PDF generation may render before boot JS runs. The
	// server (siraj_research.record_icons.GLYPHS) carries the same strings.
	const GLYPHS = {
		'Person':              '<circle cx="12" cy="8" r="3"/><path d="M5 19c0-4 3-6 7-6s7 2 7 6"/>',
		'Institution':         '<path d="M3 9h18L12 3 3 9Zm2 1v8m5-8v8m4-8v8m5-8v8M3 20h18"/>',
		'Place':               '<path d="M12 21s-6-6-6-11a6 6 0 0 1 12 0c0 5-6 11-6 11Z"/><circle cx="12" cy="10" r="2"/>',
		'Research Event':      '<path d="M12 2l2.5 6 6.5.5-5 4 1.5 6.5-5.5-3.5L6.5 19 8 12.5l-5-4L9.5 8Z"/>',
		'Source':              '<path d="M6 3h9l3 3v15H6Z"/><path d="M15 3v4h3"/><path d="M9 10h6M9 14h6M9 18h4"/>',
		'Military Unit':       '<path d="M12 2 20 5v6c0 5-3 8-8 11-5-3-8-6-8-11V5Z"/><path d="M12 7v10M7 12h10"/>',
		'Operational Deployment': '<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3"/>',
		'Training Exercise':   '<path d="M12 3l9 4-9 4-9-4Z"/><path d="M3 12l9 4 9-4M3 17l9 4 9-4"/>',
		'Mission':             '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
		'Unit Classification':'<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/>',
		'Armament':            '<path d="M3 14h6l3-3 7 1v3l-7-1-3 3H5Z"/><path d="M14 7l3-3 3 3-3 3"/>',
		'Command Appointment': '<path d="M6 8h12v3l-6 4-6-4Z"/><path d="M8 11v8h8v-8"/>',
		'Relationship':        '<path d="M4 12a4 4 0 0 1 4-4h3"/><circle cx="7" cy="12" r="1.5"/><path d="M20 12a4 4 0 0 0-4-4"/><path d="M13 12h4"/><circle cx="17" cy="12" r="1.5"/>',
		'Country':             '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
		'Governorate':         '<path d="M3 5l4-2 4 3 4-2 6 4v11l-5 3-5-2-4 2-4-3Z"/>',
		'District':            '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M9 4v16M15 4v16M4 9h16M4 15h16"/>',
		'Municipality':        '<path d="M3 21V10l9-6 9 6v11"/><path d="M9 21v-6h6v6"/>',
		'Village':             '<path d="M4 20 12 6l8 14"/><path d="M8 20v-5h8v5"/>',
		'Community':           '<circle cx="9" cy="10" r="2"/><circle cx="15" cy="10" r="2"/><circle cx="12" cy="15" r="2"/><path d="M9 12v2M15 12v2M10.5 14.5l1 1M13.5 14.5l-1 1"/>',
	};

	const TOOLS = {
		search:     '<circle cx="11" cy="11" r="6"/><path d="m16 16 4 4"/>',
		layers:     '<path d="M12 3 2 8l10 5 10-5Z"/><path d="m4 12 8 4 8-4M4 16l8 4 8-4"/>',
		zoom_in:    '<circle cx="12" cy="12" r="9"/><path d="M12 8v8M8 12h8"/>',
		zoom_out:   '<circle cx="12" cy="12" r="9"/><path d="M8 12h8"/>',
		fit:        '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/><path d="m9 9 6 6"/>',
		locate:     '<circle cx="12" cy="12" r="3"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3"/>',
		ruler:      '<path d="m3 17 6-6 4 4 8-8"/><path d="m15 7h4v4"/>',
		area:       '<path d="m3 14 5-8 5 5 7-6 1 10H3Z"/>',
		clear:      '<path d="M6 6l12 12M18 6 6 18"/>',
		download:   '<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/>',
		export:     '<path d="M12 16V4"/><path d="m7 9 5-5 5 5"/>',
		cluster:    '<circle cx="8" cy="8" r="3"/><circle cx="16" cy="8" r="3"/><circle cx="12" cy="16" r="3"/>',
		lines:      '<path d="m4 8 5-3 6 6 5-5"/><circle cx="4" cy="8" r="1.5" fill="currentColor"/><circle cx="9" cy="5" r="1.5" fill="currentColor"/><circle cx="15" cy="11" r="1.5" fill="currentColor"/><circle cx="20" cy="6" r="1.5" fill="currentColor"/>',
		panel_left: '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M4 9h5v11H4"/>',
		panel_right:'<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M20 9h-5v11h5"/>',
		coordinates:'<path d="M12 21s-6-6-6-11a6 6 0 0 1 12 0c0 5-6 11-6 11Z"/><circle cx="12" cy="10" r="1.5" fill="currentColor"/>',
		info:       '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 8v.01"/>',
		home:       '<path d="m3 11 9-8 9 8"/><path d="M5 10v10h14V10"/>',
		menu:       '<path d="M4 6h16M4 12h16M4 18h16"/>',
		chevron:    '<path d="m9 6 6 6-6 6"/>',
		check:      '<path d="m5 12 5 5 9-11"/>',
		warning:    '<path d="M12 3 2 20h20Z"/><path d="M12 10v4M12 18v.01"/>',
		online:     '<circle cx="12" cy="12" r="3"/><path d="M2 12a10 10 0 0 1 20 0M5 12a7 7 0 0 1 14 0"/>',
		offline:    '<circle cx="12" cy="12" r="3"/><path d="M3 6l18 12"/>',
		locate_me:  '<circle cx="12" cy="12" r="3"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3"/><path d="M7 7l-3-4M17 7l3-4M7 17l-3 4M17 17l3 4"/>',
		radius:     '<circle cx="12" cy="12" r="9"/><path d="M12 12l6-3"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/><path d="M18 9l-1.5-1M18 9l.5 1.8"/>',
		bearing:    '<path d="M4 20l14-8-14-2 5 2Z"/>',
		pick:       '<path d="M12 21s-6-6-6-11a6 6 0 0 1 12 0c0 5-6 11-6 11Z"/><path d="M12 10l2 2"/><path d="M8 14l-2 4 4-2"/>',
		ego:        '<circle cx="12" cy="12" r="2.5" fill="currentColor"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1"/>',
		link_add:   '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 1 0-5.7-5.7L11.5 7"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 1 0 5.7 5.7L12.5 17"/><path d="M18 6l-4 4"/><path d="M15 6h3v3"/>',
		link_chain: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 1 0-5.7-5.7L11.5 7"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 1 0 5.7 5.7L12.5 17"/>',
		path:       '<circle cx="5" cy="17" r="1.5" fill="currentColor"/><circle cx="12" cy="7" r="1.5" fill="currentColor"/><circle cx="19" cy="14" r="1.5" fill="currentColor"/><path d="M5 17c3-5 4-5 7-10s4 7 7 7"/>',
		hop1:       '<circle cx="12" cy="12" r="2" fill="currentColor"/><circle cx="12" cy="12" r="7" fill="none"/>',
		hop2:       '<circle cx="12" cy="12" r="2" fill="currentColor"/><circle cx="12" cy="12" r="5" fill="none"/><circle cx="12" cy="12" r="9" fill="none"/>',
		hop3:       '<circle cx="12" cy="12" r="2" fill="currentColor"/><circle cx="12" cy="12" r="4" fill="none"/><circle cx="12" cy="12" r="7" fill="none"/><circle cx="12" cy="12" r="10" fill="none"/>',
		isolate:    '<circle cx="12" cy="12" r="3" fill="currentColor"/><path d="M3 3l4 4M21 3l-4 4M3 21l4-4M21 21l-4-4" opacity=".6"/>',
		pin_sel:    '<path d="M12 21s-6-6-6-11a6 6 0 0 1 12 0c0 5-6 11-6 11Z"/><path d="M9 8l6 8M15 8l-6 8"/>',
		arrow:      '<path d="M5 12h13M13 7l5 5-5 5"/>',
		inferred:   '<circle cx="12" cy="12" r="5" fill="none" stroke-dasharray="2 2"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/>',
		halo:       '<circle cx="12" cy="12" r="3"/><circle cx="12" cy="12" r="8" fill="none" stroke-dasharray="2 3" opacity=".7"/>',
		edge_filter:'<path d="m4 7 4 5 4-5M12 7h8M4 12h8m4 0l4-5-4-5M4 17l4-5 4 5M12 17h8"/>',
		edges_off:  '<path d="m4 7 5 5 5-7 6 8"/><path d="M3 3l18 18" opacity=".7"/>',
		edge_expand:'<circle cx="7" cy="12" r="2"/><circle cx="17" cy="12" r="2"/><path d="M9 12h6M4 20l3-3M20 20l-3-3"/>',
		undo:       '<path d="M9 14L4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/>',
		time:       '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2"/>',
		funnel:     '<path d="M3 4h18l-7 9v6l-4-2v-4Z"/>',
		help:       '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 0 1 5 0c0 1.5-2.5 2-2.5 3.5"/><circle cx="12" cy="17" r="0.8" fill="currentColor"/>',
		list:       '<path d="M4 6h16M4 12h16M4 18h16"/><circle cx="4" cy="6" r="1" fill="currentColor"/><circle cx="4" cy="12" r="1" fill="currentColor"/><circle cx="4" cy="18" r="1" fill="currentColor"/>',
		card:       '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M8 4v16M4 9h16"/>',
		eraser:     '<path d="M14 3a2 2 0 0 1 3 3l-9 12H4l-1-5Z"/><path d="M10 13l6-6"/><path d="M4 20h12"/>',
		back:       '<path d="M15 6l-6 6 6 6"/>',
		// Toolbar chrome: group collapse/expand and label-mode switcher.
		chevrons_up:   '<path d="m6 14 6-6 6 6"/><path d="m6 10 6-6 6 6"/>',
		chevrons_down: '<path d="m6 10 6 6 6-6"/><path d="m6 14 6 6 6-6"/>',
		icon_only: '<rect x="3" y="3" width="8" height="8" rx="1.5"/><rect x="13" y="3" width="8" height="8" rx="1.5"/><rect x="3" y="13" width="8" height="8" rx="1.5"/><rect x="13" y="13" width="8" height="8" rx="1.5"/>',
		icon_text: '<rect x="3" y="4" width="6" height="16" rx="1"/><path d="M12 8h9M12 12h9M12 16h6"/>',
		icon_auto: '<rect x="3" y="3" width="7" height="18" rx="1"/><path d="M14 7h7M14 12h7M14 17h4"/><path d="M3 12h7" opacity=".4"/>',
	};

	// Server may have overridden/extended at boot time (future-proofing).
	const boot = (frappe.boot && frappe.boot.siraj_record_meta) || {};
	const colours = Object.assign({
		'Person':'#3577c0','Institution':'#8262b0','Place':'#188c7e','Research Event':'#d08733',
		'Source':'#aa6b85','Military Unit':'#c3564b',
		'Operational Deployment':'#867e45','Training Exercise':'#4f8a65','Mission':'#b56d2c',
		'Unit Classification':'#6f6a8a','Armament':'#5b6c46',
		'Command Appointment':'#7b4c79','Relationship':'#53706b',
		'Country':'#2f6f83','Governorate':'#5c8699','District':'#82a2b0','Municipality':'#a4bcc6',
		'Village':'#c4d6dd','Community':'#dde8ec',
	}, boot.colours || {});

	function svg(glyphSet, name, opts) {
		const defs = glyphSet[name] || glyphSet['Source'];
		if (!defs) return '';
		const size = (opts && opts.size) || 24;
		const cls = (opts && opts.cls) || '';
		const aria = (opts && opts.ariaLabel) ? ` role="img" aria-label="${opts.ariaLabel}"` : ' aria-hidden="true"';
		const fill = (opts && opts.fill) ? ` fill="${opts.fill}"` : ' fill="none"';
		return `<svg class="${cls}" viewBox="0 0 24 24" width="${size}" height="${size}"${aria}${fill} stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${defs}</svg>`;
	}

	function colour(doctype) {
		return colours[doctype] || '#6a7a7e';
	}

	function pin(doctype, color, size) {
		const s = size || 36, i = Math.round(s * 0.58), inner = Math.round(s * 0.5);
		return `<span class="sx-map-pin siraj-pin" data-doctype="${doctype}" style="background:${color || colour(doctype)};width:${s}px;height:${s}px;border-width:${Math.max(2, Math.round(s/12))}px">${svg(GLYPHS, doctype, {size: i})}</span>`;
	}

	function swatch(doctype, size) {
		const s = size || 14;
		return `<span class="siraj-swatch" data-doctype="${doctype}" style="display:inline-flex;align-items:center;justify-content:center;width:${s}px;height:${s}px;border-radius:3px;background:${colour(doctype)};color:#fff;vertical-align:-2px;margin-inline-end:4px">${svg(GLYPHS, doctype, {size: Math.round(s*0.7)})}</span>`;
	}

	window.sirajRecordMeta = boot;
	window.sirajColours = colours;
	window.sirajIcons = { types: GLYPHS, tools: TOOLS, svg: (n,o)=>svg(GLYPHS,n,o), toolSvg: (n,o)=>svg(TOOLS,n,o), pin, swatch, colour };
})();

// Build stamp — bump on every bundle change so stale caches are obvious in the console.
window.SIRAJ_BUILD = '2026-11-16.toolbar-advanced.14';
try { console.info('%c[SIRAJ]', 'color:#0c5e5b;font-weight:bold', 'build', window.SIRAJ_BUILD, '| engines: maplibre (preferred), leaflet (compat) | advanced map toolbar (grouped sections, collapse/expand, scrollable body, icons/labels/auto label modes, keyboard nav, persistent state, RTL-friendly); complete Arabic i18n across all tabs; advanced structure filter bar; inline add-relationship; shift+drag link; self-test retries'); } catch (_) {}
