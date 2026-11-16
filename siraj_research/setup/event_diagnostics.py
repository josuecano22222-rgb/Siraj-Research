"""Read-only bench diagnostics for the SIRAJ/Frappe Event collision.

No row contents, names, credentials, file paths, or schema changes are returned.
These aggregate counts do not prove what committed during a failed operation.
"""
import frappe

from siraj_research.setup.test_data import OPERATIONAL_TYPES


EVENT_FIELDS = ("title_ar", "display_name", "event_type", "subject", "starts_on",
                "sync_with_google_calendar", "google_calendar")


def inspect_event_collision():
    """Report site metadata and counts; never change data or expose record names."""
    meta = frappe.get_meta("Event")
    event_table = frappe.db.table_exists("Event")
    fields = {field: {"metadata": bool(meta.get_field(field)),
                      "column": bool(event_table and frappe.db.has_column("Event", field))} for field in EVENT_FIELDS}
    counts = {}
    for doctype in OPERATIONAL_TYPES:
        if (frappe.db.table_exists(doctype) and frappe.get_meta(doctype).get_field("researcher_notes")
                and frappe.db.has_column(doctype, "researcher_notes")):
            counts[doctype] = frappe.db.count(doctype, {"researcher_notes": ["like", "TEST SAMPLE%"]})
    return {"event_module": meta.module, "event_fields": fields,
            "event_total": frappe.db.count("Event") if event_table else None, "test_sample_marker_counts": counts,
            "note": "Marker counts are not proof of rollback or ownership; rows may have been edited or pre-existed. This diagnostic makes no changes."}

# This deliberately fixed scope cannot discover custom tables or arbitrary text
# and must not be used as an automatic migration eligibility check.
EVENT_REFERENCE_FIELDS = (
    ("Relationship", "subject_type"), ("Relationship", "object_type"),
    ("Evidence", "parenttype"), ("External Identifier", "parenttype"),
    ("Event Participants", "parenttype"), ("Event Participants", "reference_doctype"),
    ("File", "attached_to_doctype"), ("Comment", "reference_doctype"),
    ("ToDo", "reference_type"), ("Version", "ref_doctype"),
    ("Notification Log", "document_type"), ("Activity Log", "reference_doctype"),
    ("DocShare", "share_doctype"),
    ("Custom Field", "dt"), ("Property Setter", "doc_type"),
    ("Client Script", "dt"), ("Server Script", "reference_doctype"),
    ("Workflow", "document_type"),
)


def inspect_known_event_references():
    """Count a fixed selection of Event-typed references; no row data is returned.

    This is an administrator-run diagnostic, not a complete dependency scan.
    Missing tables or columns are reported as unknown, never as zero. Each
    count is independent, so one row may contribute to more than one count.
    """
    results = []
    for doctype, field in EVENT_REFERENCE_FIELDS:
        if not frappe.db.table_exists(doctype) or not frappe.db.has_column(doctype, field):
            count = None
        else:
            count = frappe.db.count(doctype, {field: "Event"})
        results.append({"doctype": doctype, "field": field, "count": count})
    return {
        "references": results,
        "note": ("Counts cover only the listed fields, can overlap, and may include orphaned or ambiguous "
                 "references. Null means table or column absent, not zero. They do not identify ownership, "
                 "references in custom fields, other apps, external systems, free text or all dependencies; this is not "
                 "an authorization or readiness check for migration or deletion."),
    }
