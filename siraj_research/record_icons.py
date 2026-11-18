# -*- coding: utf-8 -*-
"""Universal SIRAJ record-metadata registry.

Every DocType that can appear as a marker, graph node, list-row avatar, form
sidebar indicator, dashboard card, map tooltip, link-result glyph or Jinja
reference resolves through :data:`RECORDS`. Each entry holds the stable display
metadata (label, colour, icon glyph, category) so consumers never duplicate
colours or SVGs.

Keep this module free of Frappe imports at import-time; functions that touch
the database should take a ``frappe``-like argument or be called from request
context.
"""
from __future__ import annotations

from typing import Dict

#: Canonical palette. Keys match the SVG/JS colour dictionary and CSS custom
#: properties. All glyphs are drawn on white so colours must meet 4.5:1 contrast.
COLOURS: Dict[str, str] = {
	"Person":              "#3577c0",  # steel-blue — biography
	"Institution":         "#8262b0",  # purple — organisations
	"Place":               "#188c7e",  # teal — geography
	"Research Event":      "#d08733",  # ochre — events
	"Source":              "#aa6b85",  # plum — sources
	"Military Unit":       "#c3564b",  # brick-red — combat units (all echelons incl. Division)
	"Operational Deployment": "#867e45",  # olive — active ops
	"Training Exercise":   "#4f8a65",  # forest-green — training
	"Mission":             "#b56d2c",  # burnt-orange — named missions
	# Command Region removed 2026-11: command areas are now Place records with
	# place_type="Command Region" (Place already has a full lat/lon tree + Place
	# Type taxonomy and is already on the map).
	"Unit Classification": "#6f6a8a",  # muted violet — organisational taxonomy
	"Armament":            "#5b6c46",  # moss-green — equipment
	"Command Appointment": "#7b4c79",  # mauve — billets/appointments
	"Relationship":        "#53706b",  # slate — connections
	"Country":             "#2f6f83",  # blue-teal — polity
	"Governorate":         "#5c8699",  # soft blue — province
	"District":            "#82a2b0",  # powder — sub-province
	"Municipality":        "#a4bcc6",  # very pale blue — local
	"Village":             "#c4d6dd",  # paleest blue — settlement
	"Community":           "#dde8ec",  # near-white (use with outline)
}

#: 24x24 stroke-only SVG paths (no <svg> wrapper). Same as siraj-icons.js on
#: the client. Keep the two in lockstep; tests/test_form_integrity.py enforces
# that every doctype listed here has a matching JS entry.
GLYPHS: Dict[str, str] = {
	"Person":              '<circle cx="12" cy="8" r="3"/><path d="M5 19c0-4 3-6 7-6s7 2 7 6"/>',
	"Institution":         '<path d="M3 9h18L12 3 3 9Zm2 1v8m5-8v8m4-8v8m5-8v8M3 20h18"/>',
	"Place":               '<path d="M12 21s-6-6-6-11a6 6 0 0 1 12 0c0 5-6 11-6 11Z"/><circle cx="12" cy="10" r="2"/>',
	"Research Event":      '<path d="M12 2l2.5 6 6.5.5-5 4 1.5 6.5-5.5-3.5L6.5 19 8 12.5l-5-4L9.5 8Z"/>',
	"Source":              '<path d="M6 3h9l3 3v15H6Z"/><path d="M15 3v4h3"/><path d="M9 10h6M9 14h6M9 18h4"/>',
	"Military Unit":       '<path d="M12 2 20 5v6c0 5-3 8-8 11-5-3-8-6-8-11V5Z"/><path d="M12 7v10M7 12h10"/>',
	# Divisions are now Military Unit records (echelon='Division'); they use
	# the same shield glyph, no separate doctype or glyph.
	"Operational Deployment": '<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3"/>',
	"Training Exercise":   '<path d="M12 3l9 4-9 4-9-4Z"/><path d="M3 12l9 4 9-4M3 17l9 4 9-4"/>',
	"Mission":             '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
	# Command Region glyph removed — command areas are now Place records
	# (shield glyph for Place already covers them).
	"Unit Classification":'<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/>',
	"Armament":            '<path d="M3 14h6l3-3 7 1v3l-7-1-3 3H5Z"/><path d="M14 7l3-3 3 3-3 3"/>',
	"Command Appointment": '<path d="M6 8h12v3l-6 4-6-4Z"/><path d="M8 11v8h8v-8"/>',
	"Relationship":        '<path d="M4 12a4 4 0 0 1 4-4h3"/><circle cx="7" cy="12" r="1.5"/><path d="M20 12a4 4 0 0 0-4-4"/><path d="M13 12h4"/><circle cx="17" cy="12" r="1.5"/>',
	"Country":             '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
	"Governorate":         '<path d="M3 5l4-2 4 3 4-2 6 4v11l-5 3-5-2-4 2-4-3Z"/>',
	"District":            '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M9 4v16M15 4v16M4 9h16M4 15h16"/>',
	"Municipality":        '<path d="M3 21V10l9-6 9 6v11"/><path d="M9 21v-6h6v6"/>',
	"Village":             '<path d="M4 20 12 6l8 14"/><path d="M8 20v-5h8v5"/>',
	"Community":           '<circle cx="9" cy="10" r="2"/><circle cx="15" cy="10" r="2"/><circle cx="12" cy="15" r="2"/><path d="M9 12v2M15 12v2M10.5 14.5l1 1M13.5 14.5l-1 1"/>',
}


#: Toolbar glyphs. Mirrors the JS TOOLS dict in siraj-record-meta.js.
TOOLS: Dict[str, str] = {
	"search":     '<circle cx="11" cy="11" r="6"/><path d="m16 16 4 4"/>',
	"layers":     '<path d="M12 3 2 8l10 5 10-5Z"/><path d="m4 12 8 4 8-4M4 16l8 4 8-4"/>',
	"zoom_in":    '<circle cx="12" cy="12" r="9"/><path d="M12 8v8M8 12h8"/>',
	"zoom_out":   '<circle cx="12" cy="12" r="9"/><path d="M8 12h8"/>',
	"fit":        '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/><path d="m9 9 6 6"/>',
	"locate":     '<circle cx="12" cy="12" r="3"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3"/>',
	"ruler":      '<path d="m3 17 6-6 4 4 8-8"/><path d="m15 7h4v4"/>',
	"area":       '<path d="m3 14 5-8 5 5 7-6 1 10H3Z"/>',
	"clear":      '<path d="M6 6l12 12M18 6 6 18"/>',
	"download":   '<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/>',
	"export":     '<path d="M12 16V4"/><path d="m7 9 5-5 5 5"/>',
	"cluster":    '<circle cx="8" cy="8" r="3"/><circle cx="16" cy="8" r="3"/><circle cx="12" cy="16" r="3"/>',
	"lines":      '<path d="m4 8 5-3 6 6 5-5"/><circle cx="4" cy="8" r="1.5" fill="currentColor"/><circle cx="9" cy="5" r="1.5" fill="currentColor"/><circle cx="15" cy="11" r="1.5" fill="currentColor"/><circle cx="20" cy="6" r="1.5" fill="currentColor"/>',
	"panel_left": '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M4 9h5v11H4"/>',
	"panel_right":'<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M20 9h-5v11h5"/>',
	"coordinates":'<path d="M12 21s-6-6-6-11a6 6 0 0 1 12 0c0 5-6 11-6 11Z"/><circle cx="12" cy="10" r="1.5" fill="currentColor"/>',
	"info":       '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 8v.01"/>',
	"home":       '<path d="m3 11 9-8 9 8"/><path d="M5 10v10h14V10"/>',
	"menu":       '<path d="M4 6h16M4 12h16M4 18h16"/>',
	"chevron":    '<path d="m9 6 6 6-6 6"/>',
	"check":      '<path d="m5 12 5 5 9-11"/>',
	"warning":    '<path d="M12 3 2 20h20Z"/><path d="M12 10v4M12 18v.01"/>',
	"online":     '<circle cx="12" cy="12" r="3"/><path d="M2 12a10 10 0 0 1 20 0M5 12a7 7 0 0 1 14 0"/>',
	"offline":    '<circle cx="12" cy="12" r="3"/><path d="M3 6l18 12"/>',
	"locate_me":  '<circle cx="12" cy="12" r="3"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3"/><path d="M7 7l-3-4M17 7l3-4M7 17l-3 4M17 17l3 4"/>',
	"radius":     '<circle cx="12" cy="12" r="9"/><path d="M12 12l6-3"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/><path d="M18 9l-1.5-1M18 9l.5 1.8"/>',
	"bearing":    '<path d="M4 20l14-8-14-2 5 2Z"/>',
	"pick":       '<path d="M12 21s-6-6-6-11a6 6 0 0 1 12 0c0 5-6 11-6 11Z"/><path d="M12 10l2 2"/><path d="M8 14l-2 4 4-2"/>',
	# Goal 2/3 — ego network, linking, panel, time, filter, legend, help, undo, link-chain, add.
	"ego":        '<circle cx="12" cy="12" r="2.5" fill="currentColor"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1"/>',
	"link_add":   '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 1 0-5.7-5.7L11.5 7"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 1 0 5.7 5.7L12.5 17"/><path d="M18 6l-4 4"/><path d="M15 6h3v3"/>',
	"link_chain": '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 1 0-5.7-5.7L11.5 7"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 1 0 5.7 5.7L12.5 17"/>',
	"path":       '<circle cx="5" cy="17" r="1.5" fill="currentColor"/><circle cx="12" cy="7" r="1.5" fill="currentColor"/><circle cx="19" cy="14" r="1.5" fill="currentColor"/><path d="M5 17c3-5 4-5 7-10s4 7 7 7"/>',
	"hop1":       '<circle cx="12" cy="12" r="2" fill="currentColor"/><circle cx="12" cy="12" r="7" fill="none"/><text x="12" y="22" font-size="5" text-anchor="middle" fill="currentColor" stroke="none">1</text>',
	"hop2":       '<circle cx="12" cy="12" r="2" fill="currentColor"/><circle cx="12" cy="12" r="5" fill="none"/><circle cx="12" cy="12" r="9" fill="none"/><text x="12" y="24" font-size="5" text-anchor="middle" fill="currentColor" stroke="none">2</text>',
	"hop3":       '<circle cx="12" cy="12" r="2" fill="currentColor"/><circle cx="12" cy="12" r="4" fill="none"/><circle cx="12" cy="12" r="7" fill="none"/><circle cx="12" cy="12" r="10" fill="none"/><text x="12" y="24" font-size="5" text-anchor="middle" fill="currentColor" stroke="none">3</text>',
	"isolate":    '<circle cx="12" cy="12" r="3" fill="currentColor"/><path d="M3 3l4 4M21 3l-4 4M3 21l4-4M21 21l-4-4" opacity=".6"/>',
	"pin_sel":    '<path d="M12 21s-6-6-6-11a6 6 0 0 1 12 0c0 5-6 11-6 11Z"/><path d="M9 8l6 8M15 8l-6 8"/>',
	"arrow":      '<path d="M5 12h13M13 7l5 5-5 5"/>',
	"inferred":   '<circle cx="12" cy="12" r="5" fill="none" stroke-dasharray="2 2"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/>',
	"halo":       '<circle cx="12" cy="12" r="3"/><circle cx="12" cy="12" r="8" fill="none" stroke-dasharray="2 3" opacity=".7"/>',
	"edge_filter":'<path d="m4 7 4 5 4-5M12 7h8M4 12h8m4 0l4-5-4-5M4 17l4-5 4 5M12 17h8"/>',
	"edges_off":  '<path d="m4 7 5 5 5-7 6 8"/><path d="M3 3l18 18" opacity=".7"/>',
	"edge_expand":'<circle cx="7" cy="12" r="2"/><circle cx="17" cy="12" r="2"/><path d="M9 12h6M4 20l3-3M20 20l-3-3"/>',
	"undo":       '<path d="M9 14L4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/>',
	"time":       '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2"/>',
	"funnel":     '<path d="M3 4h18l-7 9v6l-4-2v-4Z"/>',
	"help":       '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 0 1 5 0c0 1.5-2.5 2-2.5 3.5"/><circle cx="12" cy="17" r="0.8" fill="currentColor"/>',
	"list":       '<path d="M4 6h16M4 12h16M4 18h16"/><circle cx="4" cy="6" r="1" fill="currentColor"/><circle cx="4" cy="12" r="1" fill="currentColor"/><circle cx="4" cy="18" r="1" fill="currentColor"/>',
	"card":       '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M8 4v16M4 9h16"/>',
	"eraser":     '<path d="M14 3a2 2 0 0 1 3 3l-9 12H4l-1-5Z"/><path d="M10 13l6-6"/><path d="M4 20h12"/>',
	"back":       '<path d="M15 6l-6 6 6 6"/>',
	"spinner":    '<path d="M12 3a9 9 0 0 1 9 9" fill="none"/>',
}


def record_meta(doctype: str) -> dict:
	"""Return display metadata for ``doctype``.

	Always returns *a* dict (defaulting to "Other" grey + generic-document
	glyph) so call sites never have to KeyError-check.
	"""
	spec = RECORDS.get(doctype)
	if spec:
		return {**spec, "doctype": doctype}
	return {
		"doctype": doctype,
		"colour": "#6a7a7e",
		"glyph": '<path d="M6 3h9l3 3v15H6Z"/><path d="M9 10h6M9 14h6"/>',
		"category": "other",
	}


def svg(doctype: str, *, size: int = 16, colour: str | None = None) -> str:
	"""Render a standalone SVG for ``doctype`` suitable for inline HTML."""
	meta = record_meta(doctype)
	c = colour or meta["colour"]
	return (
		f'<svg class="siraj-doctype-glyph" viewBox="0 0 24 24" width="{size}" height="{size}"'
		f' aria-hidden="true" fill="none" stroke="{c}" stroke-width="1.8"'
		f' stroke-linecap="round" stroke-linejoin="round">{meta["glyph"]}</svg>'
	)


#: Per-doctype metadata. ``category`` drives grouping on dashboards.
RECORDS: Dict[str, dict] = {
	"Person":               {"colour": COLOURS["Person"],              "glyph": GLYPHS["Person"],              "category": "actor"},
	"Institution":          {"colour": COLOURS["Institution"],         "glyph": GLYPHS["Institution"],         "category": "actor"},
	"Place":                {"colour": COLOURS["Place"],               "glyph": GLYPHS["Place"],               "category": "geo"},
	"Research Event":       {"colour": COLOURS["Research Event"],      "glyph": GLYPHS["Research Event"],      "category": "event"},
	"Source":               {"colour": COLOURS["Source"],              "glyph": GLYPHS["Source"],              "category": "evidence"},
	"Military Unit":        {"colour": COLOURS["Military Unit"],       "glyph": GLYPHS["Military Unit"],       "category": "unit"},
	"Operational Deployment": {"colour": COLOURS["Operational Deployment"], "glyph": GLYPHS["Operational Deployment"], "category": "operation"},
	"Training Exercise":    {"colour": COLOURS["Training Exercise"],   "glyph": GLYPHS["Training Exercise"],   "category": "operation"},
	"Mission":              {"colour": COLOURS["Mission"],             "glyph": GLYPHS["Mission"],             "category": "operation"},
	# Military Division and Command Region removed 2026-11 (see comments above).
	"Unit Classification":  {"colour": COLOURS["Unit Classification"], "glyph": GLYPHS["Unit Classification"],"category": "taxonomy"},
	"Armament":             {"colour": COLOURS["Armament"],            "glyph": GLYPHS["Armament"],            "category": "equipment"},
	"Command Appointment":  {"colour": COLOURS["Command Appointment"], "glyph": GLYPHS["Command Appointment"], "category": "billet"},
	"Relationship":         {"colour": COLOURS["Relationship"],        "glyph": GLYPHS["Relationship"],        "category": "connection"},
	"Country":              {"colour": COLOURS["Country"],             "glyph": GLYPHS["Country"],             "category": "geo"},
	"Governorate":          {"colour": COLOURS["Governorate"],         "glyph": GLYPHS["Governorate"],         "category": "geo"},
	"District":             {"colour": COLOURS["District"],            "glyph": GLYPHS["District"],            "category": "geo"},
	"Municipality":         {"colour": COLOURS["Municipality"],        "glyph": GLYPHS["Municipality"],        "category": "geo"},
	"Village":              {"colour": COLOURS["Village"],             "glyph": GLYPHS["Village"],             "category": "geo"},
	"Community":            {"colour": COLOURS["Community"],           "glyph": GLYPHS["Community"],           "category": "geo"},
}


# DocTypes that are *internal* (lookups, child tables, settings). They don't
# appear as first-class search results or pins, but still get a glyph so any
# link autocomplete or breadcrumb stays consistent.
INTERNAL = {
	"Person Classification",  "Person Status",          "Person Category",
	"Place Type",              "Institution Type",       "Institution Subcategory",
	"Source Type",             "Source Reliability",     "Event Type",
	"Relationship Type",       "Leadership Quality",     "Leadership Level",
	"Military Branch",         "Military Service Status","Governance System",
	"Language",                "Documentation Level",    "Authentication Level",
	"Social Platform",         "External ID Scheme",     "Expertise Area",
	"Specialization",          "SIRAJ Settings",
}


#: Build stamp — bump with every JS/CSS bundle change. The server stamp is
#: delivered in bootinfo.siraj_record_meta.build; the client compares its
#: window.SIRAJ_BUILD against this value on boot and shows a reload banner
#: when they differ (catches stale bundles after bench build).
SIRAJ_BUILD = "2026-11-17.coord-field-slice-a.55"


#: DocTypes that carry coordinate fields and a per-form map editor.
#: Each entry declares the latitude/longitude/uncertainty fields (overridable
#: if a DocType uses non-default names), the linked Place field whose
#: coordinates the editor can copy via "use linked place", and the glyph
#: silhouette used for the editor pin. Keys are exact DocType names.
COORDINATE_DOCS: Dict[str, dict] = {
	"Person": {
		"lat_field": "latitude",
		"lon_field": "longitude",
		"uncertainty_field": "geo_uncertainty_m",
		"linked_place_field": "birthplace",
		"silhouette": "bust",
	},
	"Institution": {
		"lat_field": "latitude",
		"lon_field": "longitude",
		"uncertainty_field": "geo_uncertainty_m",
		"linked_place_field": "place",
		"silhouette": "building",
	},
	"Place": {
		"lat_field": "latitude",
		"lon_field": "longitude",
		"uncertainty_field": "geo_uncertainty_m",
		"linked_place_field": "parent_place",
		"silhouette": "pin",
	},
	"Research Event": {
		"lat_field": "latitude",
		"lon_field": "longitude",
		"uncertainty_field": "geo_uncertainty_m",
		"linked_place_field": "place",
		"silhouette": "star",
	},
	"Military Unit": {
		"lat_field": "latitude",
		"lon_field": "longitude",
		"uncertainty_field": "geo_uncertainty_m",
		"linked_place_field": "linked_place",
		"silhouette": "shield",
	},
	"Operational Deployment": {
		"lat_field": "latitude",
		"lon_field": "longitude",
		"uncertainty_field": "geo_uncertainty_m",
		"linked_place_field": None,   # free-text `location` only
		"silhouette": "crosshair",
	},
}


def boot_session(bootinfo):
	"""Attach JS-ready record-metadata to ``bootinfo`` so every page sees it.

	Hooks calls this at ``on_session_creation`` (with ``bootinfo`` as the
	sole positional argument) so every Desk page, Explorer view and print
	format can rely on ``frappe.boot.siraj_record_meta`` existing.
	"""
	bootinfo.siraj_record_meta = {
		"colours": COLOURS,
		"glyphs": GLYPHS,
		"tools": TOOLS,
		"records": {dt: {"colour": v["colour"], "category": v["category"]} for dt, v in RECORDS.items()},
		"coordinate_docs": COORDINATE_DOCS,
		"build": SIRAJ_BUILD,
	}
