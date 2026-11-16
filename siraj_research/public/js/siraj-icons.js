/* SIRAJ shared icon registry.
 *
 * Every map, graph, structure and form view in SIRAJ uses these SVG glyphs so
 * that a Person always looks like a Person, a Place like a Place, and every
 * tool button has the same shape. All paths are drawn on a 24×24 viewBox with
 * stroke styling controlled by CSS (stroke="currentColor", stroke-width 1.8,
 * round caps/joins, fill none) so the consumer can size and colour them freely.
 */
window.sirajIcons = (function () {
	'use strict';
	/* --- Record-type glyphs (used as pins / nodes / legend swatches) --- */
	const types = {
		'Person':
			'<circle cx="12" cy="8" r="3"/><path d="M5 19c0-4 3-6 7-6s7 2 7 6"/>',
		'Institution':
			'<path d="M3 9h18L12 3 3 9Zm2 1v8m5-8v8m4-8v8m5-8v8M3 20h18"/>',
		'Place':
			'<path d="M12 21s-6-6-6-11a6 6 0 0 1 12 0c0 5-6 11-6 11Z"/><circle cx="12" cy="10" r="2"/>',
		'Research Event':
			'<path d="M12 2l2.5 6 6.5.5-5 4 1.5 6.5-5.5-3.5L6.5 19 8 12.5l-5-4L9.5 8Z"/>',
		'Source':
			'<path d="M6 3h9l3 3v15H6Z"/><path d="M15 3v4h3"/><path d="M9 10h6M9 14h6M9 18h4"/>',
		'Military Unit':
			'<path d="M12 2 20 5v6c0 5-3 8-8 11-5-3-8-6-8-11V5Z"/><path d="M12 7v10M7 12h10"/>',
		'Military Division':
			'<path d="M4 20V4l8 3 8-3v16"/><path d="M4 20h16"/>',
		'Operational Deployment':
			'<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3"/>',
		'Training Exercise':
			'<path d="M12 3l9 4-9 4-9-4Z"/><path d="M3 12l9 4 9-4M3 17l9 4 9-4"/>',
		'Mission':
			'<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
		'Command Region':
			'<path d="M12 2 3 7v5c0 5 4 8 9 10 5-2 9-5 9-10V7Z"/><circle cx="12" cy="12" r="2"/>',
		'Unit Classification':
			'<path d="M4 7h16v3H4Z"/><path d="M7 10v10M12 10v10M17 10v10M5 20h14"/>',
		'Armament':
			'<path d="M3 14h6l3-3 7 1v3l-7-1-3 3H5Z"/><path d="M14 7l3-3 3 3-3 3"/>',
		'Relationship':
			'<path d="M4 12a4 4 0 0 1 4-4h3"/><circle cx="7" cy="12" r="1.5"/><path d="M20 12a4 4 0 0 0-4-4"/><path d="M13 12h4"/><circle cx="17" cy="12" r="1.5"/>',
		'Country':
			'<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
		'Governorate':
			'<path d="M3 5l4-2 4 3 4-2 6 4v11l-5 3-5-2-4 2-4-3Z"/>',
		'District':
			'<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M9 4v16M15 4v16M4 9h16M4 15h16"/>',
	};
	/* --- Tool glyphs (used inside the map toolbar) --- */
	const tools = {
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
		export:     '<path d="M12 16V4"/><path d="m7 9 5-5 5 5"/><path d="M5 20h14"/>',
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
		measure:    '<path d="M3 17 21 7"/><path d="M6 14l3 3m3-9 3 3"/>',
	};

	function svg(type, opts) {
		const defs = types[type] || tools[type];
		if (!defs) return '';
		const size = (opts && opts.size) || 24;
		const cls = (opts && opts.cls) || '';
		const aria = (opts && opts.ariaLabel) ? ` role="img" aria-label="${opts.ariaLabel}"` : ' aria-hidden="true"';
		const fw = (opts && opts.fill) ? ` fill="${opts.fill}"` : ' fill="none"';
		return `<svg class="${cls}" viewBox="0 0 24 24" width="${size}" height="${size}"${aria}${fw} stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${defs}</svg>`;
	}

	function pin(type, color, size) {
		const s = size || 36, i = Math.round(s * 0.58), inner = Math.round(s * 0.5);
		return (
			`<span class="sx-map-pin" style="background:${color || '#777'};width:${s}px;height:${s}px;border-width:${Math.max(2, Math.round(s/12))}px">` +
			svg(type, { size: i }) +
			'</span>'
		);
	}

	return { types, tools, svg, pin };
})();
