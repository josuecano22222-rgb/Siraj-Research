"""Read-only bench diagnostics for the SIRAJ/Frappe Event collision.

No row contents, names, credentials, file paths, or schema changes are returned.
These aggregate counts do not prove what committed during a failed operation.
"""

import frappe

from siraj_research.setup.test_data import OPERATIONAL_TYPES

CORE_EVENT_FIELDS = (
	"subject",
	"starts_on",
	"event_type",
	"event_participants",
	"sync_with_google_calendar",
	"google_calendar",
)

RESEARCH_EVENT_FIELDS = (
	"title_ar",
	"title_en",
	"display_name",
	"event_type",
	"place",
	"latitude",
	"longitude",
	"workflow_state",
	"evidence",
	"external_identifiers",
)


def _inspect_one(doctype_name, fields_of_interest):
	"""Return field metadata/column existence + total count for one doctype.

	Counts/fields are None if the table or doctype is absent so the report
	never implies zero on a missing/renamed type.
	"""
	try:
		meta = frappe.get_meta(doctype_name)
		module = meta.module
	except Exception:
		return {
			"present": False,
			"module": None,
			"fields": {f: {"metadata": False, "column": False} for f in fields_of_interest},
			"total": None,
		}
	table_exists = frappe.db.table_exists(doctype_name)
	fields = {
		field: {
			"metadata": bool(meta.get_field(field)),
			"column": bool(table_exists and frappe.db.has_column(doctype_name, field)),
		}
		for field in fields_of_interest
	}
	total = frappe.db.count(doctype_name) if table_exists else None
	return {"present": True, "module": module, "fields": fields, "total": total}


def inspect_event_collision():
	"""Report metadata and counts for both the Frappe core Event and the SIRAJ Research Event.

	Makes no data changes and returns no record names.
	"""
	core = _inspect_one("Event", CORE_EVENT_FIELDS)
	research = _inspect_one("Research Event", RESEARCH_EVENT_FIELDS)

	counts = {}
	for doctype in OPERATIONAL_TYPES:
		if (
			frappe.db.table_exists(doctype)
			and frappe.get_meta(doctype).get_field("researcher_notes")
			and frappe.db.has_column(doctype, "researcher_notes")
		):
			counts[doctype] = frappe.db.count(doctype, {"researcher_notes": ["like", "TEST SAMPLE%"]})

	return {
		"core_event": core,
		"research_event": research,
		"collision_detected": core["present"] and core.get("module") == "Siraj Research",
		"test_sample_marker_counts": counts,
		"note": (
			"Marker counts are not proof of rollback or ownership; rows may have been edited or pre-existed. "
			"A collision is reported when the Event doctype is owned by Siraj Research instead of Desk. "
			"This diagnostic makes no changes."
		),
	}


# This deliberately fixed scope cannot discover custom tables or arbitrary text
# and must not be used as an automatic migration eligibility check.
EVENT_REFERENCE_FIELDS = (
	("Relationship", "subject_type"),
	("Relationship", "object_type"),
	("Evidence", "parenttype"),
	("External Identifier", "parenttype"),
	("Event Participants", "parenttype"),
	("Event Participants", "reference_doctype"),
	("File", "attached_to_doctype"),
	("Comment", "reference_doctype"),
	("ToDo", "reference_type"),
	("Version", "ref_doctype"),
	("Notification Log", "document_type"),
	("Activity Log", "reference_doctype"),
	("DocShare", "share_doctype"),
	("Custom Field", "dt"),
	("Property Setter", "doc_type"),
	("Client Script", "dt"),
	("Server Script", "reference_doctype"),
	("Workflow", "document_type"),
)


def inspect_known_event_references():
	"""Count a fixed selection of Link/Dynamic-Link references to Event or Research Event.

	Administrator-run diagnostic; not a complete dependency scan. Counts each
	Event and Research Event reference separately so the operator can see how
	many target the core calendar vs. the research type.
	"""
	results = []
	targets = ("Event", "Research Event")
	for doctype, field in EVENT_REFERENCE_FIELDS:
		if not frappe.db.table_exists(doctype) or not frappe.db.has_column(doctype, field):
			results.append({"doctype": doctype, "field": field, "target": None, "count": None})
			continue
		for target in targets:
			count = frappe.db.count(doctype, {field: target})
			results.append({"doctype": doctype, "field": field, "target": target, "count": count})
	return {
		"references": results,
		"note": (
			"Counts cover only the listed fields, can overlap, and may include orphaned or ambiguous "
			"references. Null means table or column absent, not zero. They do not identify ownership, "
			"references in custom fields, other apps, external systems, free text or all dependencies; this is not "
			"an authorization or readiness check for migration or deletion."
		),
	}
