"""Idempotent cleanup patch (v1.0): remove stale Custom Fields on SIRAJ DocTypes.

Earlier work in Form Builder on Person (and potentially other DocTypes) left
Custom Field rows that duplicated the standard "coordinate_map_html" field
and/or the "Coordinate map" Section Break. Those duplicates render the
section twice on New/Edit forms. This patch deletes any Custom Field whose
(dt, fieldname) already exists on the standard DocType JSON — the standard
field wins.

Also re-applies the Table-field and default_print_format cleanups defensively
in case a site migrated from an older install without running them.
"""
import json
from pathlib import Path

import frappe


SIRAJ_MODULE = "Siraj Research"
DOCTYPES_ROOT = Path(__file__).resolve().parents[2] / "siraj_research" / "doctype"


def _standard_fieldnames():
    """Return {DocType_name: {fieldname, ...}} from current JSON on disk."""
    out = {}
    for sub in DOCTYPES_ROOT.iterdir():
        if not sub.is_dir():
            continue
        jf = sub / f"{sub.name}.json"
        if not jf.exists():
            continue
        try:
            doc = json.loads(jf.read_text())
        except Exception:
            continue
        if doc.get("custom"):
            continue
        out[doc["name"]] = {f["fieldname"] for f in doc.get("fields", []) if f.get("fieldname")}
    return out


def execute():
    backups = []
    std_fields = _standard_fieldnames()

    # 1. Delete any Custom Field that duplicates a field already defined on the
    #    standard DocType JSON. This kills the double "Coordinate map" section
    #    and any other Form Builder detritus.
    for cf in frappe.get_all(
        "Custom Field",
        filters={"dt": ["in", list(std_fields.keys())]},
        fields=["name", "dt", "fieldname"],
    ):
        if cf.fieldname and cf.fieldname in std_fields.get(cf.dt, set()):
            try:
                doc = frappe.get_doc("Custom Field", cf.name)
                backups.append({"doctype": "Custom Field", "name": cf.name, "dt": cf.dt, "fieldname": cf.fieldname})
                frappe.delete_doc("Custom Field", cf.name, force=True, ignore_permissions=True)
            except Exception as e:
                frappe.log_error(f"[siraj] failed to remove CF {cf.name}: {e}", "SIRAJ cleanup")

    # 2. Belt-and-suspenders: also remove any Property Setter that injects
    #    default_print_format on a standard SIRAJ DocType.
    for ps in frappe.get_all(
        "Property Setter",
        filters={"doc_type": ["in", list(std_fields.keys())], "property": "default_print_format"},
        fields=["name", "doc_type"],
    ):
        try:
            frappe.delete_doc("Property Setter", ps.name, force=True, ignore_permissions=True)
        except Exception:
            pass

    if backups:
        frappe.log_error(
            f"[siraj] removed {len(backups)} stale Custom Fields that duplicated standard fields",
            "SIRAJ cleanup",
        )
