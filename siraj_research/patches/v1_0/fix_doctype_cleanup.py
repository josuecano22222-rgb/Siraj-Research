"""Idempotent cleanup patch (v1.0): reconcile DB with current JSON.

- Removes Custom Fields whose dt is a SIRAJ DocType and whose fieldname belonged
  to a Table field that no longer exists in the JSON (relation DocTypes are now
  standalone, so parent Table fields pointing at them are gone).
- Removes Property Setters that set default_print_format on standard SIRAJ DocTypes.
- Backs up every deleted row to a JSON file in the site's private folder.
- Safe to run multiple times.
"""
import json
import frappe
from pathlib import Path


SIRAJ_MODULE = "Siraj Research"
REMOVED_TABLE_FIELDS = {
    "Person":          {"positions", "institutions", "military_units", "events_table", "locations_table"},
    "Institution":     {"events_table", "military_units", "locations_table", "people"},
    "Military Unit":   {"institutions", "events_table", "locations_table", "command_personnel"},
    "Place":           {"people", "institutions", "military_units", "events"},
    "Siraj Event":     {"people", "institutions", "military_units", "places"},
}
STANDARD_RELATIONS = [
    "Person Position", "Person Institution", "Person Event", "Person Military Unit",
    "Person Location", "Institution Event", "Institution Military Unit", "Institution Location",
    "Military Unit Event", "Military Unit Institution", "Military Unit Location",
    "Siraj Event Person", "Siraj Event Institution", "Siraj Event Military Unit",
    "Siraj Event Location",
]


def execute():
    backups = []

    # 1. Remove stale Custom Fields that mirror old Table fields
    for parent_dt, old_fields in REMOVED_TABLE_FIELDS.items():
        for fn in old_fields:
            cf_name = f"{parent_dt}-{fn}"
            if frappe.db.exists("Custom Field", cf_name):
                doc = frappe.get_doc("Custom Field", cf_name)
                backups.append({"doctype": "Custom Field", "name": cf_name, "data": doc.as_dict()})
                frappe.delete_doc("Custom Field", cf_name, force=True, ignore_permissions=True)

    # 2. Remove any Custom Field that still holds a snake_case Table options value
    for cf in frappe.get_all("Custom Field",
            filters={"dt": ["in", list(REMOVED_TABLE_FIELDS.keys())]},
            fields=["name", "dt", "fieldname", "fieldtype", "options"]):
        if cf.fieldtype == "Table" and cf.options and "_" in cf.options and cf.options[0].islower():
            doc = frappe.get_doc("Custom Field", cf.name)
            backups.append({"doctype": "Custom Field", "name": cf.name, "data": doc.as_dict()})
            frappe.delete_doc("Custom Field", cf.name, force=True, ignore_permissions=True)

    # 3. Remove default_print_format Property Setters on standard SIRAJ DocTypes
    all_standard = list(REMOVED_TABLE_FIELDS.keys()) + STANDARD_RELATIONS
    for ps in frappe.get_all("Property Setter",
            filters={"doc_type": ["in", all_standard], "property": "default_print_format"},
            fields=["name", "doc_type"]):
        doc = frappe.get_doc("Property Setter", ps.name)
        backups.append({"doctype": "Property Setter", "name": ps.name, "data": doc.as_dict()})
        frappe.delete_doc("Property Setter", ps.name, force=True, ignore_permissions=True)

    # 4. Backup
    if backups:
        backup_dir = Path(frappe.get_site_path("private", "files"))
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / "siraj_doctype_cleanup_backup.json"
        backup_path.write_text(json.dumps(backups, indent=2, default=str))
        print(f"Removed {len(backups)} stale rows; backup at {backup_path}")
    else:
        print("No stale Custom Field / Property Setter rows found — DB clean.")

    frappe.db.commit()
