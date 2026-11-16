# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
from __future__ import annotations

from frappe import _

from siraj_research.report_access import can_read_link, readable_rows


def execute(filters=None):
	filters = filters or {}
	columns = [
		{"fieldname": "name", "label": _("Unit ID"), "fieldtype": "Link", "options": "Military Unit", "width": 140},
		{"fieldname": "unit_name", "label": _("Unit name"), "fieldtype": "Data", "width": 220},
		{"fieldname": "parent_unit", "label": _("Parent Unit"), "fieldtype": "Link", "options": "Military Unit", "width": 150},
		{"fieldname": "workflow_state", "label": _("Review State"), "fieldtype": "Data", "width": 120},
	]
	conditions = {"name": filters["unit"]} if filters.get("unit") else {}
	data = list(readable_rows("Military Unit", ["unit_name", "parent_unit", "workflow_state"], conditions))
	# Parent links are themselves potentially sensitive. Do not disclose an
	# inaccessible parent merely because the child is readable.
	for row in data:
		if not can_read_link("Military Unit", row.get("parent_unit"), ("Military Unit",)):
			row["parent_unit"] = None
	return columns, data
