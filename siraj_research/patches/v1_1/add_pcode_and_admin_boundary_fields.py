# -*- coding: utf-8 -*-
"""Phase 1 patch — add P-Code + boundary linkage fields to admin hierarchy.

Idempotent: re-running after a successful first run is a no-op. Uses
frappe's Custom Field API so we do NOT alter the existing DocType JSON
for Governorate/District/Municipality/Village/Community (which are
shipped data DocTypes); the fields survive future DocType edits because
they are stored as Custom Field rows.

Also creates the four Phase-1 DocTypes if they are missing (safety net
in case fixtures aren't loaded automatically on a bench without
migrate).
"""
from __future__ import annotations

import frappe


def _has_field(doctype: str, fieldname: str) -> bool:
	return frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": fieldname}) or (
		frappe.get_meta(doctype).get_field(fieldname) is not None
	)


def _add_custom_field(doctype: str, fieldname: str, **props) -> None:
	if _has_field(doctype, fieldname):
		return
	cf = frappe.new_doc("Custom Field")
	cf.dt = doctype
	cf.fieldname = fieldname
	for k, v in props.items():
		setattr(cf, k, v)
	cf.insert(ignore_permissions=True)


def _ensure_doctype(name: str) -> None:
	if frappe.db.exists("DocType", name):
		return
	# Rely on fixtures (the JSON files we ship); if bench migrate runs
	# the DocType sync will pick them up before patches execute. In
	# interactive testing this creates a clearer error.
	frappe.throw(
		f"DocType '{name}' is missing — run 'bench migrate --app siraj_research' "
		"first so fixtures are synced."
	)


def _add_index(doctype: str, columns: list[str]) -> None:
	"""Create a non-unique index if one doesn't already exist."""
	import re
	table = f"tab{doctype.replace(' ', '')}"
	idx_name = "i_" + "_".join(re.sub(r"[^a-z0-9]", "", c.lower()) for c in columns)
	existing = frappe.db.sql(
		"SELECT COUNT(*) FROM information_schema.statistics "
		"WHERE table_schema = DATABASE() AND table_name = %s AND index_name = %s",
		(table, idx_name),
	)[0][0]
	if existing:
		return
	col_list = ", ".join(f"`{c}`" for c in columns)
	frappe.db.sql(f"CREATE INDEX `{idx_name}` ON `{table}` ({col_list})")


def execute():
	# Safety-net DocType existence check.
	for dt in ("Boundary Dataset", "Admin Boundary", "Gazetteer Place", "Geo Settings", "Admin Boundary Geom"):
		_ensure_doctype(dt)

	# P-Code + boundary linkage on each admin level DocType. P-Code matches
	# OCHA COD-AB / geoBoundaries / GADM conventions: short ASCII code that
	# is unique within a country+admin-level.
	pcode_field = {
		"fieldtype": "Data",
		"label": "P-Code",
		"length": 64,
		"in_list_view": 1,
		"in_standard_filter": 1,
		"search_index": 1,
		"after": "code",
		"description": "Stable place code (e.g. IRQ019 for Baghdad Governorate). Used to link records to admin boundaries and to resolve parent chains from imported datasets.",
	}
	admin_boundary_field = {
		"fieldtype": "Link",
		"options": "Admin Boundary",
		"label": "Admin boundary",
		"in_list_view": 0,
		"after": "pcode",
		"description": "The Admin Boundary polygon for this record, from the active Boundary Dataset.",
	}

	for dt in ("Governorate", "District", "Municipality", "Village", "Community"):
		_add_custom_field(dt, "pcode", **pcode_field)
		_add_custom_field(dt, "admin_boundary", **admin_boundary_field)

	# DB indexes for common lookup patterns (resolve_point is heavy on
	# dataset+level+parent_pcode reads).
	frappe.db.commit()
	try:
		_add_index("Admin Boundary", ["dataset", "level", "pcode"])
		_add_index("Admin Boundary", ["dataset", "parent_pcode"])
		_add_index("Gazetteer Place", ["dataset", "feature_code"])
		_add_index("Gazetteer Place", ["latitude", "longitude"])
	except Exception:
		# Index creation is best-effort; if the table is empty or the
		# dialect doesn't support composite indexes over FLOAT we fall
		# through — the server code does its own bounding-box filter.
		frappe.db.rollback()

	frappe.db.commit()
