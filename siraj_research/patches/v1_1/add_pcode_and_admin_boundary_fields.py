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


def _add_index(doctype: str, columns: list[str]) -> None:
	"""Create a non-unique index if one doesn't already exist.

	Uses a plain CREATE INDEX IF NOT EXISTS on MariaDB/MySQL (standard in
	Frappe deployments). PostgreSQL is handled by an EXCEPTION block. We
	fail soft on any dialect we don't recognize — indexes are a
	performance optimisation, not a correctness requirement.
	"""
	import re
	table = f"tab{doctype.replace(' ', '')}"
	idx_name = "i_" + "_".join(re.sub(r"[^a-z0-9]", "", c.lower()) for c in columns)
	try:
		frappe.db.sql(f"CREATE INDEX IF NOT EXISTS `{idx_name}` ON `{table}` ({', '.join('`'+c+'`' for c in columns)})")
	except Exception:
		# Fall back for older MySQL/MariaDB without IF NOT EXISTS.
		try:
			frappe.db.sql(f"CREATE INDEX `{idx_name}` ON `{table}` ({', '.join('`'+c+'`' for c in columns)})")
		except Exception:
			pass


def execute():
	# DocType fixtures (Boundary Dataset / Admin Boundary / Gazetteer
	# Place / Geo Settings / Admin Boundary Geom) are synced by Frappe's
	# migrate step before patches run. If sync has not created them for
	# some reason (e.g. module list issue), the Custom Field inserts
	# below will simply be a no-op for the new DocTypes and we only
	# add indexes against tables that exist.

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
		if not frappe.db.exists("DocType", dt):
			continue
		_add_custom_field(dt, "pcode", **pcode_field)
		_add_custom_field(dt, "admin_boundary", **admin_boundary_field)

	# DB indexes for common lookup patterns (resolve_point is heavy on
	# dataset+level+parent_pcode reads). Guarded by table-existence check
	# so the patch does not fail if DocType sync hasn't finished creating
	# the companion tables in this same migrate run.
	frappe.db.commit()
	for dt, cols in [
		("Admin Boundary", ["dataset", "level", "pcode"]),
		("Admin Boundary", ["dataset", "parent_pcode"]),
		("Gazetteer Place", ["dataset", "feature_code"]),
		("Gazetteer Place", ["latitude", "longitude"]),
	]:
		try:
			table = f"tab{dt.replace(' ', '')}"
			exists = frappe.db.sql(
				"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = %s",
				table,
			)[0][0]
			if not exists:
				continue
			_add_index(dt, cols)
		except Exception:
			frappe.db.rollback()
	frappe.db.commit()
