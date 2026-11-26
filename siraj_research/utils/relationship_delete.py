# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
"""Delete-block guard for endpoint records referenced by a `Relationship` (§8).

A `Relationship` row is a sourced, evidence-backed research claim. Silently
cascading its deletion when an endpoint is deleted would destroy provenance
without review, so endpoint deletion is **blocked** (fail closed) when any
`Relationship` references the record from either end.

The rare legitimate case is an explicit admin override: set
``frappe.local.flags.relationship_delete_guard_bypass = True`` before deleting
(mirroring the ``delete_research_event.py`` force-delete precedent). A plain
``force=True`` delete does **not** bypass the guard.
"""

from __future__ import annotations

import frappe

BYPASS_FLAG = "relationship_delete_guard_bypass"


def block_delete_if_referenced(doctype: str, name: str) -> None:
	"""Raise ``ValidationError`` if any `Relationship` references this endpoint.

	Checks both ends: a row where ``(subject_type, subject)`` matches the
	deleted record, or where ``(object_type, object)`` matches.
	"""
	if getattr(frappe.local, "flags", None) and getattr(frappe.local.flags, BYPASS_FLAG, False):
		return

	referenced = frappe.db.exists(
		"Relationship",
		{
			"subject_type": doctype,
			"subject": name,
		},
	) or frappe.db.exists(
		"Relationship",
		{
			"object_type": doctype,
			"object": name,
		},
	)
	if referenced:
		frappe.throw(
			frappe._(
				"Cannot delete {0} {1}: it is referenced by a Relationship. "
				"Remove or reassign those relationships first."
			).format(frappe._(doctype), name),
			frappe.ValidationError,
			title=frappe._("Delete blocked"),
		)
