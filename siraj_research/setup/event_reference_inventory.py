"""Read-only, best-effort inventory of metadata-defined references to Event.

Administrator-run, potentially expensive on large sites. This does not perform
or authorize migration and does not inspect arbitrary code, text, or external
systems. Do not publish its output without reviewing operational metadata.
"""
import frappe


def inspect_metadata_event_references():
    """Count fixed and dynamic Event references in non-single SQL DocTypes.

    A dynamic selector is counted even if its associated target is empty;
    this conservatively reports possible references, not ownership. Counts
    are per field and can overlap. Unknown/skipped fields are never zero.
    """
    results, skipped = [], []
    checked_fields = 0
    doctypes = frappe.get_all("DocType", fields=["name", "issingle", "is_virtual"],
                             order_by="name asc", limit_page_length=0)
    for row in doctypes:
        name = row["name"]
        if row.get("issingle") or row.get("is_virtual"):
            skipped.append({"doctype": name, "reason": "single or virtual DocType"})
            continue
        if not frappe.db.table_exists(name):
            skipped.append({"doctype": name, "reason": "table absent"})
            continue
        try:
            meta = frappe.get_meta(name)
            fields = list(meta.fields or [])
        except Exception:
            # Keep the report usable while surfacing incompleteness. Do not
            # return tracebacks, which may contain sensitive metadata.
            skipped.append({"doctype": name, "reason": "metadata unavailable"})
            continue
        selectors = set()
        direct = set()
        for df in fields:
            field = df.get("fieldname")
            kind, options = df.get("fieldtype"), df.get("options") or ""
            if not field:
                continue
            if kind == "Link" and options == "Event":
                direct.add(field)
            if (kind == "Link" and options == "DocType") or (kind == "Select" and "Event" in options.splitlines()):
                selectors.add(field)
            if kind == "Dynamic Link" and options:
                selectors.add(options)
        for field, kind in [(f, "direct") for f in sorted(direct)] + [(f, "selector") for f in sorted(selectors)]:
            if not frappe.db.has_column(name, field):
                skipped.append({"doctype": name, "field": field, "reason": "column absent"})
                continue
            try:
                filters = {field: ["is", "set"] if kind == "direct" else "Event"}
                count = frappe.db.count(name, filters)
            except Exception:
                skipped.append({"doctype": name, "field": field, "reason": "count unavailable"})
                continue
            checked_fields += 1
            if count:
                results.append({"doctype": name, "field": field, "kind": kind, "count": count})
    return {
        "checked_fields": checked_fields,
        "nonzero_counts": results,
        "skipped": skipped,
        "note": ("Best-effort metadata scan, not proof of safety or ownership. Zeros are omitted; "
                 "skipped entries are unknown. Counts may overlap, and selectors can be set without "
                 "a target. Single and virtual doctypes, free text, scripts, unmodeled tables, "
                 "external systems and other dependencies require separate review."),
    }
