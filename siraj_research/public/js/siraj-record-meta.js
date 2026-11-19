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
		'Siraj Event':      '<path d="M12 2l2.5 6 6.5.5-5 4 1.5 6.5-5.5-3.5L6.5 19 8 12.5l-5-4L9.5 8Z"/>',
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
		// Distinct from the single 'chevron' (which is a sideways chevron used for
		// breadcrumbs/back). These are DOUBLE up/down chevrons for the collapse/
		// expand-all buttons.
		chevrons_up:   '<path d="m5 10 7-6 7 6"/><path d="m5 17 7-6 7 6"/>',
		chevrons_down: '<path d="m5 7 7 6 7-6"/><path d="m5 14 7 6 7-6"/>',
		// Label-mode icons — all visually distinct so they can be told apart at
		// 14px in the footer. "Icons only" = a 3×3 grid of filled squares (dense
		// tile), "Icons + text" = a wide sidebar icon + three text lines, "Auto" =
		// a slider/toggle between compact and wide.
		icon_only: '<rect x="4" y="4" width="5" height="5" rx="1"/><rect x="11" y="4" width="5" height="5" rx="1"/><rect x="18" y="4" width="2" height="5" rx="1" opacity=".4"/><rect x="4" y="11" width="5" height="5" rx="1"/><rect x="11" y="11" width="5" height="5" rx="1"/><rect x="18" y="11" width="2" height="5" rx="1" opacity=".4"/><rect x="4" y="18" width="5" height="2" rx="1" opacity=".4"/>',
		icon_text: '<rect x="3" y="5" width="6" height="14" rx="1" fill="currentColor" fill-opacity=".2"/><path d="M12 7h8" stroke-width="2.4" stroke-linecap="round"/><path d="M12 12h8" stroke-width="2.4" stroke-linecap="round"/><path d="M12 17h5" stroke-width="2.4" stroke-linecap="round"/>',
		icon_auto: '<rect x="3" y="8" width="18" height="8" rx="4" fill="none"/><circle cx="8" cy="12" r="2.4" fill="currentColor"/><path d="M14 9h4M14 12h4M14 15h2" stroke-linecap="round" opacity=".65"/>',
		// Basemap switcher icons — four distinct basemap modes.
		basemap_standard: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h6v6H3zM9 3h6v6H9zM15 9h6v6h-6zM9 15h6v6H9z" opacity=".55"/>',
		basemap_satellite: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="12" cy="12" r="4"/><path d="M4 7c2-2 4-3 8-3s6 1 8 3M4 17c2 2 4 3 8 3s6-1 8-3" opacity=".7"/>',
		basemap_hybrid: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="12" cy="12" r="4" opacity=".55"/><path d="M3 9h18M3 15h18M9 3v18M15 3v18" stroke-width="1.2" opacity=".75"/>',
		basemap_offline: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M5 13c2-3 5-5 7-5s5 2 7 5" fill="none"/><circle cx="12" cy="13" r="1.5" fill="currentColor"/><path d="M3 8l18 8" stroke-width="1.4" opacity=".5"/>',
	};

	// Server may have overridden/extended at boot time (future-proofing).
	const boot = (frappe.boot && frappe.boot.siraj_record_meta) || {};
	const colours = Object.assign({
		'Person':'#3577c0','Institution':'#8262b0','Place':'#188c7e','Siraj Event':'#d08733',
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

	function pin(doctype, color, size, opts) {
		// Professional teardrop map pin: a rounded body with a triangular point
		// at the bottom. Callers should use iconAnchor:[s/2, Math.round(s*1.15)]
		// so the point sits exactly on the geographic coordinate.
		const s = size || 36;
		const h = Math.round(s * 1.15);
		const bodyW = Math.round(s * 0.76);
		const bw = Math.max(2, Math.round(s / 14));
		// Triangle point dimensions scale with pin size.
		const pOuter = Math.round(s * 0.22);   // outer white triangle half-width
		const pInner = Math.round(s * 0.14);   // inner colored triangle half-width
		const pOuterH = Math.round(s * 0.34);  // outer triangle height
		const pInnerH = Math.round(s * 0.28);  // inner colored triangle height
		const c = color || colour(doctype);
		const o = opts || {};
		const glyph = svg(GLYPHS, doctype, {size: Math.round(bodyW * 0.55)});
		const stateCls = o.state === 'selected' ? ' is-selected'
		               : o.state === 'active'   ? ' is-active'
		               : o.state === 'inactive' ? ' is-inactive' : '';
		const dot = o.dot ? `<span class="siraj-pin-dot" style="width:${Math.max(8,Math.round(s*.28))}px;height:${Math.max(8,Math.round(s*.28))}px;background:${o.dot};top:${-Math.round(s*0.05)}px"></span>` : '';
		const ring = o.ring
			? (typeof o.ring === 'string'
				? `<span class="siraj-pin-ring" style="border-color:${o.ring}"></span>`
				: `<span class="siraj-pin-ring" style="border-color:${o.ring.color};border-style:${o.ring.style||'solid'}"></span>`)
			: '';
		const halo = o.halo ? `<span class="siraj-pin-halo" style="background:${o.halo}"></span>` : '';
		const pointStyle = `border-left-width:${pOuter}px;border-right-width:${pOuter}px;border-top-width:${pOuterH}px;`;
		const innerStyle = `left:-${pInner}px;top:-${pInnerH}px;border-left-width:${pInner}px;border-right-width:${pInner}px;border-top-width:${pInnerH}px;border-top-color:${c};`;
		return `<span class="sx-map-pin siraj-pin${stateCls}" data-doctype="${doctype}" style="--pin-color:${c};width:${s}px;height:${h}px">${halo}${ring}<span class="siraj-pin-body" style="width:${bodyW}px;background:${c};border-width:${bw}px">${glyph}</span>${dot}<span class="siraj-pin-point" style="${pointStyle}"><span style="${innerStyle}"></span></span></span>`;
	}

	function swatch(doctype, size) {
		const s = size || 14;
		return `<span class="siraj-swatch" data-doctype="${doctype}" style="display:inline-flex;align-items:center;justify-content:center;width:${s}px;height:${s}px;border-radius:3px;background:${colour(doctype)};color:#fff;vertical-align:-2px;margin-inline-end:4px">${svg(GLYPHS, doctype, {size: Math.round(s*0.7)})}</span>`;
	}

	// Per-DocType coordinate editor configuration — mirrors
	// record_icons.COORDINATE_DOCS on the server. Fallback defaults are
	// applied when boot metadata is not yet available (tests, print view).
	const COORDINATE_DOCS_FALLBACK = {
		'Person':                { lat_field:'latitude', lon_field:'longitude', uncertainty_field:'geo_uncertainty_m', linked_place_field:'birthplace',            silhouette:'bust' },
		'Institution':           { lat_field:'latitude', lon_field:'longitude', uncertainty_field:'geo_uncertainty_m', linked_place_field:'place',                  silhouette:'building' },
		'Place':                 { lat_field:'latitude', lon_field:'longitude', uncertainty_field:'geo_uncertainty_m', linked_place_field:'parent_place',           silhouette:'pin' },
		'Siraj Event':        { lat_field:'latitude', lon_field:'longitude', uncertainty_field:'geo_uncertainty_m', linked_place_field:'place',                  silhouette:'star' },
		'Military Unit':         { lat_field:'latitude', lon_field:'longitude', uncertainty_field:'geo_uncertainty_m', linked_place_field:'linked_place',           silhouette:'shield' },
		'Operational Deployment':{ lat_field:'latitude', lon_field:'longitude', uncertainty_field:'geo_uncertainty_m', linked_place_field:null,                     silhouette:'crosshair' },
	};
	const coordinateDocs = Object.assign({}, COORDINATE_DOCS_FALLBACK,
		(boot && boot.coordinate_docs) || {});

	window.sirajRecordMeta = boot;
	window.sirajColours = colours;
	window.sirajCoordinateDocs = coordinateDocs;
	window.sirajIcons = { types: GLYPHS, tools: TOOLS, svg: (n,o)=>svg(GLYPHS,n,o), toolSvg: (n,o)=>svg(TOOLS,n,o), pin, swatch, colour, coordinateDocs };
})();

// Build stamp — bump on every bundle change so stale caches are obvious in the console.
// Keep this string in lockstep with record_icons.py SIRAJ_BUILD.
window.SIRAJ_BUILD = '2026-11-20.hierarchy-ui.d.1';
try { console.info('%c[SIRAJ]', 'color:#0c5e5b;font-weight:bold', 'build', window.SIRAJ_BUILD, "| Full coordinate-to-hierarchy UI with isolated map setup."); } catch (_) {}

// ---------- Stale-bundle banner ----------
// Compare the JS-built stamp with the server stamp delivered at boot time.
// If they differ the browser is running a cached bundle against a newer
// server (most often the owner seeing old UI after a deploy). Show a
// non-blocking dismissible banner urging a hard reload, and never auto-
// reload (that can lose in-flight form edits).
(function showVersionBanner() {
	try {
		const serverBuild = (frappe.boot && frappe.boot.siraj_record_meta && frappe.boot.siraj_record_meta.build) || null;
		const localBuild = window.SIRAJ_BUILD;
		if (!serverBuild) return;
		const DISMISS_KEY = 'siraj_build_banner_dismissed';
		const prevDismiss = localStorage.getItem(DISMISS_KEY);
		if (serverBuild === localBuild) {
			// Matches — clear any prior dismissal so next mismatch shows again.
			if (prevDismiss) localStorage.removeItem(DISMISS_KEY);
			return;
		}
		if (prevDismiss === serverBuild) return;  // already dismissed for this target version
		// Mount banner once DOM is ready.
		const mount = () => {
			if (document.getElementById('siraj-build-banner')) return;
			const bar = document.createElement('div');
			bar.id = 'siraj-build-banner';
			bar.setAttribute('role', 'status');
			bar.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:9999;background:#fff3cd;color:#664d03;border-bottom:2px solid #ffecb5;padding:8px 16px;font-size:13px;display:flex;align-items:center;gap:12px;box-shadow:0 2px 8px rgba(0,0,0,.15);font-family:system-ui,sans-serif;direction:ltr;';
			bar.innerHTML = '<strong style="flex:0 0 auto">⟳ SIRAJ</strong>'
				+ '<span style="flex:1 1 auto">A new version of SIRAJ Research was just installed. Your browser is running build <code style="background:#00000010;padding:1px 5px;border-radius:3px">' + localBuild + '</code>; the server is at <code style="background:#00000010;padding:1px 5px;border-radius:3px">' + serverBuild + '</code>. Please hard-refresh (Ctrl/Cmd+Shift+R) to load the new maps, markers and autofill features.</span>'
				+ '<button type="button" id="siraj-build-reload" style="background:#0c5e5b;color:#fff;border:0;padding:6px 14px;border-radius:4px;cursor:pointer;font-weight:600">Reload now</button>'
				+ '<button type="button" id="siraj-build-dismiss" aria-label="Dismiss" style="background:transparent;border:0;font-size:18px;cursor:pointer;color:#664d03;padding:0 6px">×</button>';
			document.body.appendChild(bar);
			document.body.style.paddingTop = '36px';
			bar.querySelector('#siraj-build-reload').addEventListener('click', () => { location.reload(); });
			bar.querySelector('#siraj-build-dismiss').addEventListener('click', () => {
				localStorage.setItem(DISMISS_KEY, serverBuild);
				bar.remove();
				document.body.style.paddingTop = '';
			});
			console.warn('%c[SIRAJ]', 'color:#c3564b;font-weight:bold', 'stale bundle detected; local=' + localBuild + ' server=' + serverBuild);
		};
		if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, { once: true });
		else mount();
	} catch (e) { /* never break the page over the banner */ }
})();
