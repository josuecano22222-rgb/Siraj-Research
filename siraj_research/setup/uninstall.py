"""Clean uninstall hooks for Siraj Research.

Frappe drops the app's DocTypes and their tables on ``uninstall-app``. Two
things live outside those tables and must be removed explicitly:

* the ``geographic_administration`` Custom Field added by the v1_2 patch on
  seven coordinate-bearing DocTypes (otherwise the field survives with a
  dangling Link option);
* cached level configurations in Redis.

The PostGIS geometry column lives on ``tabAdmin Boundary Geom``, an app table,
so PostgreSQL drops it with the table. Nothing here touches other apps.
"""

from __future__ import annotations

import frappe

CUSTOM_FIELD_DOCTYPES = (
    "Place",
    "Person",
    "Institution",
    "Research Event",
    "Siraj Event",
    "Military Unit",
    "Operational Deployment",
)


def before_uninstall():
    removed: list[str] = []
    for doctype in CUSTOM_FIELD_DOCTYPES:
        name = f"{doctype}-geographic_administration"
        try:
            if frappe.db.exists("Custom Field", name):
                frappe.delete_doc("Custom Field", name, force=True, ignore_permissions=True)
                removed.append(name)
        except Exception:
            frappe.log_error(title="SIRAJ uninstall: custom field", message=name)
    try:
        from siraj_research.geo_levels import clear_cache

        clear_cache()
    except Exception:
        pass
    frappe.db.commit()
    print(f"SIRAJ uninstall: removed {len(removed)} custom field(s)")


def after_uninstall():
    try:
        frappe.cache.delete_keys("siraj:")
    except Exception:
        pass
