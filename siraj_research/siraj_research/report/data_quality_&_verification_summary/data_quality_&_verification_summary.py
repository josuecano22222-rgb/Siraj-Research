# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
from __future__ import annotations

import frappe
from frappe import _

from siraj_research.report_access import readable_rows

CORE_DOCTYPES = ("Person", "Institution", "Place", "Event", "Relationship", "Source", "Military Unit")


def execute(filters=None):
	columns = [
		{"fieldname": "doctype_name", "label": _("Entity Type"), "fieldtype": "Data", "width": 160},
		{"fieldname": "total_records", "label": _("Total Records"), "fieldtype": "Int", "width": 120},
		{"fieldname": "draft_count", "label": _("Draft"), "fieldtype": "Int", "width": 100},
		{"fieldname": "in_review_count", "label": _("In Review"), "fieldtype": "Int", "width": 110},
		{"fieldname": "verified_count", "label": _("Verified / Approved"), "fieldtype": "Int", "width": 150},
	]
	data = []
	for dt in CORE_DOCTYPES:
		if not frappe.has_permission(dt, "read"):
			continue
		entry = {"doctype_name": dt, "total_records": 0, "draft_count": 0, "in_review_count": 0, "verified_count": 0}
		for row in readable_rows(dt, ["workflow_state"]):
			state = row.get("workflow_state") or ""
			entry["total_records"] += 1
			entry["draft_count"] += int(state in ("", "Draft"))
			entry["in_review_count"] += int("review" in state.lower())
			entry["verified_count"] += int(state in ("Verified", "Approved", "Published"))
		data.append(entry)
	return columns, data
