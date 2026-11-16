"""Read-only, permission-aware tree navigation for SIRAJ hierarchies.

Use each DocType's declared research parent, independent of any legacy nested-set
indices. Tree mutations and repair are deliberately not performed here.
"""

import frappe
from frappe import _

from siraj_research.report_access import can_read_link, readable_rows

TREE_FIELDS = {
	"Place": ("parent_place", "display_name"),
	"Military Unit": ("parent_unit", "unit_name"),
	"Command Region": ("parent_region", "region_name"),
}


@frappe.whitelist()
def get_children(doctype, parent="", **kwargs):
	if doctype not in TREE_FIELDS:
		frappe.throw(_("Unsupported tree type"), frappe.ValidationError)
	if not frappe.has_permission(doctype, "read"):
		frappe.throw(_("Not permitted to read {0}").format(_(doctype)), frappe.PermissionError)
	if parent and not can_read_link(doctype, parent, (doctype,)):
		frappe.throw(_("Not permitted to read this tree node"), frappe.PermissionError)
	parent_field, title_field = TREE_FIELDS[doctype]
	filters = {parent_field: parent if parent else ["is", "not set"], "docstatus": ["<", 2]}
	details = ("unit_code", "echelon", "status", "direct_personnel") if doctype == "Military Unit" else ()
	rows = readable_rows(doctype, [title_field, "is_group", *details], filters)
	result = []
	for row in rows:
		node = {
			"value": row["name"],
			"title": row.get(title_field) or row["name"],
			"expandable": bool(row.get("is_group")),
		}
		# get_list strips fields the current user cannot read. Never fill them
		# via get_all or fetch linked documents here.
		node.update({field: row[field] for field in details if field in row})
		result.append(node)
	return result
