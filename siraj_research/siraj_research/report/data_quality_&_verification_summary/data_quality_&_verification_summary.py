# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
from __future__ import annotations

import frappe
from frappe import _

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
		total = frappe.db.count(dt)
		draft = frappe.db.count(dt, {"workflow_state": ["in", ["Draft", "", None]]})
		in_review = frappe.db.count(dt, {"workflow_state": ["like", "%Review%"]})
		verified = frappe.db.count(dt, {"workflow_state": ["in", ["Verified", "Approved", "Published"]]})
		data.append({
			"doctype_name": dt,
			"total_records": total,
			"draft_count": draft,
			"in_review_count": in_review,
			"verified_count": verified,
		})

	return columns, data
