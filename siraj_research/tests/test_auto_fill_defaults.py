# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
"""Coordinate auto-fill must override site-default-stamped levels (Phase 4).

A global ``country`` default used to stamp every new record with a country
Link before validate ran (Frappe ``_set_defaults``), so auto-fill — which
never overwrites — kept the default instead of the derived chain. These
tests set a live global default and assert:

* an in-dataset point derives the resolver's country (not the default);
* an open-water point stays empty instead of inheriting the default.

Run with:
    bench --site frappe.com run-tests --module siraj_research.tests.test_auto_fill_defaults
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from siraj_research.api.geo_resolve import resolve_point
from siraj_research.geo_hierarchy import resolve_and_link

PROBE_TAG = "AF Probe"


def _place_type() -> str:
    return (
        frappe.db.get_value("Place Type", {"code": "natural_site"}, "name")
        or frappe.db.get_value("Place Type", {}, "name")
    )


def _resolving_point():
    """A stored boundary centroid whose chain resolves a linked country."""
    rows = frappe.get_all(
        "Admin Boundary",
        filters={"level": ["<=", 2]},
        fields=["centroid_lat", "centroid_lon"],
        limit_page_length=300,
    )
    for row in rows:
        if row.centroid_lat is None or row.centroid_lon is None:
            continue
        resolution = resolve_point(row.centroid_lat, row.centroid_lon, 0)
        if not (resolution.get("admin_chain") or {}).get("country"):
            continue
        linked = resolve_and_link(
            row.centroid_lat, row.centroid_lon, create_missing=False
        )
        country = (linked.get("country") or {}).get("name")
        if country and country != "United States":
            return (row.centroid_lat, row.centroid_lon), country
    return None, None


class TestAutoFillDefaults(FrappeTestCase):
    @staticmethod
    def _reset_new_doc_templates():
        """Drop cached default templates so they re-read live defaults.

        Without this the process-wide ``new_doc_templates`` cache can hold a
        template built before the default was set (test proves nothing) — or
        after it (poisons later test modules in the same bench run).
        """
        try:
            frappe.local.new_doc_templates.clear()
        except Exception:
            pass

    def tearDown(self):
        for name in frappe.get_all(
            "Place",
            filters={"name_en": ["like", f"%{PROBE_TAG}%"]},
            pluck="name",
            limit_page_length=0,
        ):
            try:
                frappe.delete_doc("Place", name, force=True, ignore_permissions=True)
            except Exception:
                pass
        try:
            frappe.defaults.clear_default("country")
        except Exception:
            pass
        self._reset_new_doc_templates()
        frappe.clear_cache()
        frappe.db.commit()

    def _set_country_default(self):
        frappe.defaults.set_global_default("country", "United States")
        self._reset_new_doc_templates()
        frappe.clear_cache()
        self.assertEqual(
            (frappe.defaults.get_defaults() or {}).get("country"),
            "United States",
            "global country default must be live for the insert under test",
        )

    def _insert_probe(self, lat, lon, suffix):
        doc = frappe.get_doc(
            {
                "doctype": "Place",
                "display_name": f"{PROBE_TAG} {suffix}",
                "name_en": f"{PROBE_TAG} {suffix}",
                "name_ar": f"{PROBE_TAG} {suffix}",
                "place_type": _place_type(),
                # Exact literals — never rounded (standing precision rule).
                "latitude": lat,
                "longitude": lon,
            }
        )
        doc.insert(ignore_permissions=True)
        return frappe.get_doc("Place", doc.name)

    def test_derived_country_overrides_global_default(self):
        self._set_country_default()
        point, expected_country = _resolving_point()
        if not point:
            self.skipTest("active dataset resolves no country from stored centroids")
        place = self._insert_probe(point[0], point[1], "derived")
        self.assertEqual(
            place.country,
            expected_country,
            "derived chain must override the default-stamped country",
        )
        self.assertNotEqual(place.country, "United States")

    def test_open_water_stays_empty_with_default_live(self):
        self._set_country_default()
        place = self._insert_probe(31.6, 33.8, "ocean")
        self.assertFalse(
            place.country,
            "open water must not inherit the global country default",
        )
        self.assertFalse(place.governorate)
