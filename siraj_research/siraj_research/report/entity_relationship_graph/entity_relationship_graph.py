# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
from __future__ import annotations

from frappe import _

from siraj_research.report_access import can_read_link, readable_rows

ENTITY_TYPES = (
	"Person",
	"Institution",
	"Place",
	"Siraj Event",
	"Source",
	"Military Unit",
	"Operational Deployment",
)


def execute(filters=None):
	filters = filters or {}
	columns = [
		{"fieldname": "name", "label": _("ID"), "fieldtype": "Link", "options": "Relationship", "width": 130},
		{"fieldname": "subject_type", "label": _("Subject type"), "fieldtype": "Data", "width": 120},
		{
			"fieldname": "subject",
			"label": _("Subject"),
			"fieldtype": "Dynamic Link",
			"options": "subject_type",
			"width": 180,
		},
		{
			"fieldname": "relationship_type",
			"label": _("Relationship Type"),
			"fieldtype": "Link",
			"options": "Relationship Type",
			"width": 160,
		},
		{"fieldname": "object_type", "label": _("Object type"), "fieldtype": "Data", "width": 120},
		{
			"fieldname": "object",
			"label": _("Object"),
			"fieldtype": "Dynamic Link",
			"options": "object_type",
			"width": 180,
		},
		{"fieldname": "workflow_state", "label": _("Review State"), "fieldtype": "Data", "width": 120},
	]
	conditions = {
		field: filters[field]
		for field in ("subject_type", "object_type", "relationship_type")
		if filters.get(field)
	}
	fields = [column["fieldname"] for column in columns]
	access = {}

	def allowed(doctype, name):
		key = (doctype, name)
		if key not in access:
			access[key] = can_read_link(doctype, name, ENTITY_TYPES)
		return access[key]

	data = []
	for row in readable_rows("Relationship", fields, conditions):
		if allowed(row.get("subject_type"), row.get("subject")) and allowed(
			row.get("object_type"), row.get("object")
		):
			data.append(row)
	return columns, data
