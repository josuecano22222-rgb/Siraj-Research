# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
from __future__ import annotations

import frappe
from frappe import _


def execute(filters=None):
	columns = [
		{"fieldname": "name", "label": _("Unit ID"), "fieldtype": "Link", "options": "Military Unit", "width": 140},
		{"fieldname": "unit_name_en", "label": _("Unit Name (EN)"), "fieldtype": "Data", "width": 200},
		{"fieldname": "unit_name_ar", "label": _("Unit Name (AR)"), "fieldtype": "Data", "width": 200},
		{"fieldname": "parent_military_unit", "label": _("Parent Unit"), "fieldtype": "Link", "options": "Military Unit", "width": 150},
		{"fieldname": "workflow_state", "label": _("Review State"), "fieldtype": "Data", "width": 120},
	]

	data = frappe.get_all(
		"Military Unit",
		fields=["name", "unit_name_en", "unit_name_ar", "parent_military_unit", "workflow_state"],
		order_by="lft asc",
		limit=500,
	)
	return columns, data
