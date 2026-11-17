# siraj_research.api.relationship_profile — whitelisted relationship profile endpoint.
#
# Returns a rich, permission-filtered dossier for a single Relationship record,
# mirroring the shape of api.entity_profile.get_entity_profile so the Explorer's
# details drawer can render edges with the same sophisticated layout used for
# map pins (header with glyph/chip, tabs for Overview / Evidence / Endpoints,
# quick actions, and network summary). No raw SQL; all reads go through frappe.

import frappe
from frappe import _
from frappe.model.meta import get_meta


# Fieldtypes we render directly (everything structural/break/button is skipped).
SKIP_FIELDTYPES = {
	"Section Break", "Column Break", "Tab Break", "HTML", "Button",
	"Table MultiSelect",
}
VALUE_FIELDTYPES = {
	"Data", "Int", "Float", "Currency", "Percent", "Check", "Date",
	"Datetime", "Time", "Text", "Small Text", "Long Text", "Text Editor",
	"Code", "Link", "Dynamic Link", "Select", "Rating", "Attach",
	"Attach Image", "Image", "Barcode", "Duration", "Phone", "Email",
}
PASSWORD_PLACEHOLDER = "••••••"

# Title fields for the DocTypes that can appear as endpoints of a Relationship.
# Falls back to "name" when a DocType isn't listed or its title is unknown.
_ENDPOINT_TITLES = {
	"Person": "display_name",
	"Institution": "display_name",
	"Place": "display_name",
	"Research Event": "display_name",
	"Source": "display_name",
	"Military Unit": "unit_name",
	"Operational Deployment": "deployment_name",
}


def _fmt_value(doc, f):
	fn = f.fieldname
	ft = f.fieldtype
	val = doc.get(fn)
	if val in (None, "", []):
		return None
	if ft == "Password":
		return PASSWORD_PLACEHOLDER
	if ft == "Check":
		return _("Yes") if val else _("No")
	if ft in ("Attach", "Attach Image", "Image"):
		return {"type": "attach", "url": val}
	if ft == "Link":
		try:
			if frappe.has_permission(f.options, "read"):
				title_field = frappe.get_meta(f.options).get_title_field() or "name"
				title = frappe.db.get_value(f.options, val, title_field) or val
				return {"type": "link", "doctype": f.options, "name": val, "title": title}
		except Exception:
			pass
		return {"type": "link", "doctype": f.options, "name": val, "title": val}
	if ft == "Dynamic Link":
		target_doctype = doc.get(f.options)
		if not target_doctype:
			return val
		try:
			if frappe.has_permission(target_doctype, "read"):
				title_field = frappe.get_meta(target_doctype).get_title_field() or "name"
				title = frappe.db.get_value(target_doctype, val, title_field) or val
				return {"type": "link", "doctype": target_doctype, "name": val, "title": title}
		except Exception:
			pass
		return {"type": "link", "doctype": target_doctype, "name": val, "title": val}
	if ft == "Select":
		return _(val)
	return val


def _resolve_endpoint(doctype, name):
	"""Return {doctype,name,title,readable} for an endpoint, respecting perms."""
	if not doctype or not name:
		return None
	readable = False
	title = name
	try:
		readable = bool(frappe.has_permission(doctype, "read", name))
		if readable:
			title_field = _ENDPOINT_TITLES.get(doctype) or (
				frappe.get_meta(doctype).get_title_field() or "name"
			)
			v = frappe.db.get_value(doctype, name, title_field)
			if v:
				title = v
	except Exception:
		readable = False
	return {"doctype": doctype, "name": name, "title": title, "readable": readable}


@frappe.whitelist()
def get_relationship_profile(name, **kwargs):
	"""Return a rich profile dict for a single Relationship record.

	Keys: header, sections (field groups), children (evidence + external IDs),
	endpoints (subject/object with readable titles), counters (evidence count,
	external IDs), permissions.
	"""
	if not name or not isinstance(name, str):
		frappe.throw(_("Relationship name is required"))

	try:
		doc = frappe.get_doc("Relationship", name)
	except frappe.DoesNotExistError:
		frappe.throw(_("Relationship {0} not found").format(name))

	doc.check_permission("read")
	meta = get_meta("Relationship")

	# ---- Header ----
	header = {
		"doctype": "Relationship",
		"name": doc.name,
		"title": doc.get("relationship_type") or doc.get("display_name") or doc.name,
		"subtitle": doc.get("role_as_stated") or "",
		"status": doc.get("workflow_state") or "",
		"is_current": bool(doc.get("is_current")),
		"direction": doc.get("direction") or "",
		"owner": doc.owner,
		"modified": doc.modified,
		"docstatus": doc.docstatus,
	}

	# ---- Fields grouped by section ----
	sections = []
	cur = {"heading": _("Relationship"), "fields": []}

	for f in meta.fields:
		if f.fieldtype in SKIP_FIELDTYPES:
			if f.fieldtype == "Section Break":
				if cur["fields"]:
					sections.append(cur)
				cur = {"heading": (f.label or _("Relationship")), "fields": []}
			continue
		# Skip internal/technical fields and child-table pointers.
		if f.fieldtype in ("Table",):
			continue
		if f.hidden or f.get("is_system_field"):
			# Still include explicit business fields even if hidden from the form.
			if f.fieldname in ("display_name", "naming_series"):
				continue
		if not f.permlevel and f.fieldname in (
			"subject", "object", "subject_type", "object_type",
		):
			# Endpoints are rendered separately in the endpoints tab.
			continue
		val = _fmt_value(doc, f)
		if val is None:
			continue
		cur["fields"].append({
			"fieldname": f.fieldname,
			"label": (f.label or f.fieldname).strip(),
			"value": val,
			"fieldtype": f.fieldtype,
		})
	if cur["fields"]:
		sections.append(cur)

	# ---- Child tables (evidence + external identifiers) ----
	children = {}
	for table_meta in meta.get_table_fields():
		fn = table_meta.fieldname
		rows = doc.get(fn) or []
		if not rows:
			continue
		child_meta = get_meta(table_meta.options)
		child_fields = [
			cf for cf in child_meta.fields
			if cf.fieldtype not in SKIP_FIELDTYPES
			and cf.fieldtype != "Table"
			and not cf.hidden
		]
		out_rows = []
		for row in rows:
			r = {}
			for cf in child_fields:
				v = _fmt_value(row, cf)
				if v is not None:
					r[cf.fieldname] = {
						"label": (cf.label or cf.fieldname).strip(),
						"value": v,
					}
			if r:
				out_rows.append(r)
		if out_rows:
			children[fn] = {
				"label": table_meta.label or fn,
				"total": len(out_rows),
				"rows": out_rows[:50],
				"truncated": len(out_rows) > 50,
			}

	# ---- Endpoints ----
	subject = _resolve_endpoint(doc.get("subject_type"), doc.get("subject"))
	object_ = _resolve_endpoint(doc.get("object_type"), doc.get("object"))
	endpoints = {"subject": subject, "object": object_}

	# ---- Counters ----
	evidence_count = len(doc.get("evidence") or []) if doc.meta.get_field("evidence") else 0
	external_id_count = len(doc.get("external_identifiers") or []) if doc.meta.get_field("external_identifiers") else 0
	counters = {
		"evidence": evidence_count,
		"external_identifiers": external_id_count,
	}

	# ---- Permissions ----
	# frappe.has_permission signature: (doctype, ptype="read", doc=None,
	# user=None, ...) — pass the doc as a positional arg (entity_profile uses the
	# same shape; v15 does NOT accept a `name=` kwarg).
	permissions = {
		"can_write": bool(frappe.has_permission("Relationship", "write", doc)),
		"can_create": bool(frappe.has_permission("Relationship", "create")),
	}

	return {
		"header": header,
		"sections": sections,
		"children": children,
		"endpoints": endpoints,
		"counters": counters,
		"permissions": permissions,
	}
