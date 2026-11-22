"""Permission-gated document history for the SIRAJ audit view.

Surfaces Frappe's built-in ``Version`` history natively: human-readable
field labels, old → new values, actor and timestamp, with framework noise
filtered out.

Permission model (deliberate, documented in docs/decisions.md):

* **Record level** — ``frappe.has_permission(doctype, "read", doc=name)``
  must pass or the call raises. This is the governing DocType permission.
* **Field level** — every diff is filtered through the target DocType's
  permlevel rules (``has_permlevel_access_to``), including child-table
  fields. Callers only ever see fields they could read on the form.
* ``Version`` storage itself is a System-Manager-only doctype; reading it
  here never *grants* anything — the checks above are strictly on the
  audited record, so the four SIRAJ roles get history exactly where their
  record read already reaches, and nowhere else.
"""

from __future__ import annotations

import frappe
from frappe import _

from siraj_research.utils.audit_history import build_entries, filter_visible

MAX_LIMIT = 200
DEFAULT_LIMIT = 50


def _target_df(doc, fieldname: str):
	"""Resolve a (possibly child-prefixed) fieldname to its DocField + meta."""
	if "[" in fieldname and fieldname.endswith("]"):
		return None, None
	if "[" in fieldname:
		table, _, rest = fieldname.partition("[")
		row_part, _, child_field = rest.rstrip("]").partition(".")
		if not row_part or not child_field:
			return None, None
		parent_df = doc.meta.get_field(table)
		if not parent_df or parent_df.fieldtype not in ("Table", "Table MultiSelect"):
			return None, None
		try:
			child_meta = frappe.get_meta(parent_df.options)
		except Exception:
			return None, None
		return child_meta.get_field(child_field), child_meta
	return doc.meta.get_field(fieldname), doc.meta


def _can_read_field(doc, fieldname: str) -> bool:
	df, _meta = _target_df(doc, fieldname)
	if df is None:
		# Field no longer exists on the DocType: never disclose its history.
		return False
	permlevel = int(getattr(df, "permlevel", 0) or 0)
	if permlevel == 0:
		return True
	check_name = fieldname.split("[", 1)[0] or fieldname
	try:
		return bool(doc.has_permlevel_access_to(check_name, df, "read"))
	except Exception:  # pragma: no cover - defensive
		return False


def _field_label(doc, fieldname: str) -> str:
	if "[" in fieldname and not fieldname.endswith("]"):
		table, _, rest = fieldname.partition("[")
		row_part, _, child_field = rest.rstrip("]").partition(".")
		parent_df = doc.meta.get_field(table)
		parent_label = (getattr(parent_df, "label", None) or table) if parent_df else table
		try:
			child_meta = frappe.get_meta(parent_df.options) if parent_df else None
			child_df = child_meta.get_field(child_field) if child_meta else None
			child_label = (child_df.label if child_df else None) or child_field
		except Exception:
			child_label = child_field
		return f"{parent_label} · {child_label}" if row_part else f"{parent_label} · {child_label}"
	df = doc.meta.get_field(fieldname)
	return ((df.label if df else None) or fieldname).strip() or fieldname


def collect_history(doctype: str, name: str, limit: int = DEFAULT_LIMIT) -> dict:
	"""Build the formatted, field-filtered history for one record.

	Assumes nothing about the caller: the record-level check runs here, so
	every consumer (whitelisted API, profile drawer) inherits the same gate.
	"""
	if not isinstance(doctype, str) or not doctype or not frappe.db.exists("DocType", doctype):
		frappe.throw(_("Unknown DocType"), frappe.ValidationError)
	if not isinstance(name, str) or not name:
		frappe.throw(_("Unknown record"), frappe.ValidationError)
	if not frappe.has_permission(doctype, "read", doc=name):
		frappe.throw(
			_("Not permitted to read {0} {1}").format(doctype, name),
			frappe.PermissionError,
		)
	try:
		limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
	except (TypeError, ValueError):
		limit = DEFAULT_LIMIT
	try:
		rows = frappe.get_all(
			"Version",
			filters={"ref_doctype": doctype, "docname": name},
			fields=["name", "creation", "owner", "data"],
			order_by="creation desc",
			limit=limit,
		)
	except Exception:  # pragma: no cover - never break the host surface
		rows = []
	try:
		doc = frappe.get_doc(doctype, name)
	except frappe.DoesNotExistError:
		return {"doctype": doctype, "name": name, "history": []}
	entries = build_entries(rows)
	entries = filter_visible(entries, lambda field: _can_read_field(doc, field))
	for entry in entries:
		for change in entry["changes"]:
			change["label"] = _field_label(doc, change["field"])
	return {"doctype": doctype, "name": name, "history": entries}


@frappe.whitelist()
def document_history(doctype: str, name: str, limit: int = DEFAULT_LIMIT) -> dict:
	"""Whitelisted entry point for the audit dialog / Explorer inspector."""
	return collect_history(doctype, name, limit)
