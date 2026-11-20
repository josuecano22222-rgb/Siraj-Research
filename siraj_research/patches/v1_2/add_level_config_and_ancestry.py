"""v1.2 — per-country level configuration, ancestry paths, reusable GA link.

Idempotent: every step checks first, and any failure is reported rather than
aborting the migrate. Order matters:

1. ``Admin Level`` catalogue (global).
2. ``Country Level Config`` rows from the shipped reference file.
3. Denormalised ancestry for existing hierarchy rows.
4. ``geographic_administration`` Custom Field on coordinate-bearing DocTypes.
5. PostGIS schema/backfill when the site is PostgreSQL + PostGIS (best effort).

Run manually any time::

    bench --site <site> execute siraj_research.patches.v1_2.add_level_config_and_ancestry.execute
"""

from __future__ import annotations

import frappe

COORDINATE_DOCTYPES = (
    "Place",
    "Person",
    "Institution",
    "Research Event",
    "Siraj Event",
    "Military Unit",
    "Operational Deployment",
)


def _add_ga_field() -> list[str]:
    """Expose the reusable Link target on coordinate-bearing DocTypes."""
    added: list[str] = []
    for doctype in COORDINATE_DOCTYPES:
        if not frappe.db.exists("DocType", doctype):
            continue
        if frappe.get_meta(doctype).has_field("geographic_administration"):
            continue
        from frappe.custom.doctype.custom_field.custom_field import create_custom_field

        create_custom_field(
            doctype,
            {
                "fieldname": "geographic_administration",
                "fieldtype": "Link",
                "options": "Geographic Administration",
                "label": "Geographic administration",
                "insert_after": "country",
                "search_index": 1,
                "description": (
                    "Single linkable handle for this record's Country → Community chain. "
                    "Created/updated automatically on save when the hierarchy is resolved."
                ),
            },
        )
        added.append(doctype)
    return added


def execute():
    report: dict[str, object] = {}
    try:
        from siraj_research.geo_seeding import (
            backfill_ancestry,
            seed_admin_levels,
            seed_country_level_configs,
        )

        report["levels"] = seed_admin_levels()
        report["configs"] = seed_country_level_configs()
        report["ancestry"] = backfill_ancestry()
    except Exception as exc:  # pragma: no cover - migrate must continue
        frappe.log_error(title="SIRAJ v1_2 hierarchy patch", message=str(exc))
        report["error"] = str(exc)

    try:
        report["ga_field_added"] = _add_ga_field()
    except Exception as exc:  # pragma: no cover
        frappe.log_error(title="SIRAJ v1_2 GA custom field", message=str(exc))
        report["ga_field_error"] = str(exc)

    try:
        from siraj_research import geo_postgis

        if geo_postgis.available():
            report["postgis"] = {
                "schema": geo_postgis.ensure_schema(),
                "backfill": geo_postgis.backfill_geometries(),
            }
        else:
            report["postgis"] = {"ok": False, "reason": "unavailable_or_not_postgres"}
    except Exception as exc:  # pragma: no cover
        report["postgis_error"] = str(exc)

    frappe.db.commit()
    print("SIRAJ v1.2 hierarchy patch:", report)
    return report
