# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
from __future__ import annotations

import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	columns = [
		{"fieldname": "name", "label": _("ID"), "fieldtype": "Link", "options": "Relationship", "width": 130},
		{"fieldname": "source_doctype", "label": _("Source Type"), "fieldtype": "Data", "width": 120},
		{"fieldname": "source_docname", "label": _("Source Record"), "fieldtype": "Dynamic Link", "options": "source_doctype", "width": 180},
		{"fieldname": "relationship_type", "label": _("Relationship Type"), "fieldtype": "Link", "options": "Relationship Type", "width": 160},
		{"fieldname": "target_doctype", "label": _("Target Type"), "fieldtype": "Data", "width": 120},
		{"fieldname": "target_docname", "label": _("Target Record"), "fieldtype": "Dynamic Link", "options": "target_doctype", "width": 180},
		{"fieldname": "workflow_state", "label": _("Review State"), "fieldtype": "Data", "width": 120},
	]

	conditions = {}
	if filters.get("source_doctype"):
		conditions["source_doctype"] = filters["source_doctype"]
	if filters.get("target_doctype"):
		conditions["target_doctype"] = filters["target_doctype"]
	if filters.get("relationship_type"):
		conditions["relationship_type"] = filters["relationship_type"]

	data = frappe.get_all(
		"Relationship",
		filters=conditions,
		fields=[
			"name",
			"source_doctype",
			"source_docname",
			"relationship_type",
			"target_doctype",
			"target_docname",
			"workflow_state",
		],
		order_by="modified desc",
		limit=500,
	)
	return columns, data
