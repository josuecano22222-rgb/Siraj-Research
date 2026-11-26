"""Permission-aware report helpers, including custom per-document permission hooks."""

from __future__ import annotations

import frappe


def _can_read_doctype(doctype: str) -> bool:
	does_not_exist = getattr(getattr(frappe, "exceptions", None), "DoesNotExistError", ())
	try:
		return bool(frappe.has_permission(doctype, "read"))
	except does_not_exist:
		return False


def readable_rows(doctype, fields, filters=None, page_size=200):
	"""Iterate permitted documents without an implicit 20-row limit.

	Frappe's list query enforces role, owner, user and query permissions. The
	additional document check enforces custom has_permission hooks as well.
	"""
	if not _can_read_doctype(doctype):
		return
	start = 0
	fields = list(dict.fromkeys(["name", *fields]))
	while True:
		rows = frappe.get_list(
			doctype,
			fields=fields,
			filters=filters or {},
			order_by="name asc",
			limit_start=start,
			limit_page_length=page_size,
		)
		for row in rows:
			if frappe.has_permission(doctype, "read", doc=row["name"], throw=False):
				yield row
		if len(rows) < page_size:
			break
		start += len(rows)


def can_read_link(doctype, name, allowed_types):
	"""Don't expose a Dynamic Link to an inaccessible or deleted document."""
	if not name or doctype not in allowed_types:
		return False
	if not frappe.has_permission(doctype, "read") or not frappe.db.exists(doctype, name):
		return False
	if not frappe.has_permission(doctype, "read", doc=name, throw=False):
		return False
	# A custom permission_query_conditions hook can hide a record from list
	# queries even when document-level checks alone return true. Require both.
	rows = frappe.get_list(
		doctype,
		fields=["name"],
		filters={"name": name},
		order_by="name asc",
		limit_start=0,
		limit_page_length=1,
	)
	return any(row.get("name") == name for row in rows)
