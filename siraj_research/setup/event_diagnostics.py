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
