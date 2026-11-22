"""Recompute the derived family fields on existing Person records.

``Person.is_grandparent`` and ``Person.family_summary`` are derived on
every save (``Person.validate_family``). Persons saved before the Family
tab existed keep the default/empty values until their next edit, which
would make search and the Explorer profile under-report families.

This patch recomputes ONLY those two derived columns from the stored
family rows — it never touches user-entered data. Idempotent: a second
run finds nothing to change.
"""

from __future__ import annotations

import frappe


def execute():
	from siraj_research.utils.family import build_family_summary, derive_is_grandparent

	changed = 0
	for name in frappe.get_all("Person", pluck="name", order_by="name"):
		doc = frappe.get_doc("Person", name)
		children = doc.get("children") or []
		is_grandparent = derive_is_grandparent(
			row.number_of_children for row in children
		)
		summary = build_family_summary(
			{
				"marital_status": doc.marital_status,
				"spouse_name": doc.spouse_name,
				"children_count": len(children),
				"grandchildren_count": len(doc.get("grandchildren") or []),
				"siblings_count": len(doc.get("siblings") or []),
			},
			translate=frappe._,
		)
		updates = {}
		if int(doc.is_grandparent or 0) != is_grandparent:
			updates["is_grandparent"] = is_grandparent
		if (doc.family_summary or "") != summary:
			updates["family_summary"] = summary
		if updates:
			# Derived columns only; keep the record's modified timestamp.
			frappe.db.set_value("Person", name, updates, update_modified=False)
			changed += 1
	frappe.db.commit()
	print(f"SIRAJ family derived backfill: {changed} person(s) updated")
	return changed
