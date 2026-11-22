# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
"""Bench-side load/remove round-trip for the fictional demo dataset.

Run with:
    bench --site frappe.com run-tests --module siraj_research.tests.test_demo_data

The pure content contracts (volumes, fictional guard, edge cases,
teardown coverage, command surface) live in the repo-root
tests/test_demo_data_structure.py and run in CI without frappe.
"""

from __future__ import annotations

import json
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase

from siraj_research.setup import demo_content as C
from siraj_research.setup.demo_data import (
    MANIFEST_NAME,
    TAG,
    demo_status,
    seed_demo_data,
    teardown_demo_data,
)
from siraj_research.setup.master_data import seed_master_data

LOOKUPS = (Path(__file__).resolve().parents[1] / "setup"
           / "reference_data" / "lookups.json")


def _tagged_names(doctype: str, field: str) -> list[str]:
    return list(frappe.get_all(
        doctype, filters={field: ("like", f"%{TAG}%")},
        pluck="name", limit_page_length=0))


def _auth_labels() -> set[str]:
    """English labels stored by the Authentication Level Link field."""
    data = json.loads(LOOKUPS.read_text(encoding="utf-8"))
    return {label for code, label, *_ in
            data["domains"]["authentication_level"]
            if code in C.CONFIDENCE_CODES}


class TestDemoData(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        seed_master_data()   # additive registries / workflow states
        teardown_demo_data() # clean slate (also clears any legacy demo)

    @classmethod
    def tearDownClass(cls):
        teardown_demo_data()

    def test_load_remove_roundtrip(self):
        # -- load -------------------------------------------------------
        result = seed_demo_data()
        self.assertEqual(result["Person"], C.SPEC["persons"])
        self.assertEqual(result["Institution"], C.SPEC["institutions"])
        self.assertEqual(result["Place"], C.SPEC["places"])
        self.assertEqual(result["Source"], C.SPEC["sources"])
        self.assertEqual(result["Military Unit"], C.SPEC["military_units"])
        self.assertEqual(result["Research Event"],
                         C.SPEC["research_events"])
        self.assertEqual(result["Siraj Event"], C.SPEC["siraj_events"])
        self.assertEqual(result["Relationship"], len(C.RELATIONSHIPS))
        self.assertTrue(_tagged_names("Person", "name_en"))

        # manifest written and covers what was created (assert the FILE
        # exists — get_site_path returns a non-empty path string, which
        # would make a bare assertTrue vacuously pass)
        self.assertTrue(Path(frappe.get_site_path(MANIFEST_NAME)).exists())

        # -- idempotent re-load ---------------------------------------
        before = sorted(_tagged_names("Person", "name_en"))
        again = seed_demo_data()
        self.assertEqual(again["Person"], C.SPEC["persons"])
        self.assertEqual(sorted(_tagged_names("Person", "name_en")), before)

        # -- showcases -------------------------------------------------
        # unit hierarchy: division subtree = sum of all six units
        # pluck returns the record name (MIL-UNIT-####) — match on the
        # tagged display field instead.
        unit_rows = frappe.get_all(
            "Military Unit",
            filters={"unit_name": ["like", f"%{TAG}%"]},
            fields=["name", "unit_name"], limit_page_length=0)
        div_name = next(r.name for r in unit_rows
                        if r.unit_name.startswith("1st Amal"))
        self.assertEqual(
            frappe.db.get_value("Military Unit", div_name,
                                "subtree_personnel"),
            sum(u["personnel"] for u in C.UNITS))

        # family showcase: married + grandchildren + derived flag
        person = frappe.db.get_value(
            "Person", {"name_en": f"{C.PERSONS[9]['en']} {TAG}"},
            ["marital_status", "is_grandparent"], as_dict=True)
        self.assertEqual(person.marital_status, "Married")
        self.assertTrue(person.is_grandparent)
        single = frappe.db.get_value(
            "Person", {"name_en": f"{C.PERSONS[10]['en']} {TAG}"},
            "marital_status")
        self.assertEqual(single, "Single")

        # varied relationship confidence (all six codes). primary_source
        # holds SRC-#### names — match through the tagged source titles.
        # authentication_level is a Link to label_en (e.g. "Single
        # source"), not the code, so map codes → labels via lookups.json.
        demo_sources = _tagged_names("Source", "title")
        self.assertTrue(demo_sources)
        auths = set(frappe.get_all(
            "Relationship",
            filters={"primary_source": ["in", demo_sources]},
            pluck="authentication_level", limit_page_length=0))
        expected_auths = _auth_labels()
        self.assertTrue(
            expected_auths <= auths,
            f"missing confidence labels: {expected_auths - auths}")

        # edge: the open-water place must not resolve any admin level
        ocean = frappe.db.get_value(
            "Place", {"name_en": f"{C.PLACES[6]['en']} {TAG}"},
            ["country", "governorate"], as_dict=True)
        self.assertFalse(ocean.country)
        self.assertFalse(ocean.governorate)

        # edge: coordinates-only place keeps its exact coordinates
        auto = frappe.db.get_value(
            "Place", {"name_en": f"{C.PLACES[4]['en']} {TAG}"},
            ["latitude", "longitude"], as_dict=True)
        self.assertEqual(auto.latitude, C.AUTO_FILL_SITE[0])
        self.assertEqual(auto.longitude, C.AUTO_FILL_SITE[1])

        # every record with an evidence table carries ≥1 sourced row
        for doctype, field in (("Person", "name_en"),
                               ("Research Event", "title_en"),
                               ("Siraj Event", "title")):
            names = _tagged_names(doctype, field)
            self.assertTrue(names)
            # Evidence rows are child rows — read them off the parent doc
            missing = [n for n in names
                       if not (frappe.get_doc(doctype, n).get("evidence")
                               or [])]
            self.assertEqual(missing, [], f"{doctype} rows without evidence")

        # isolation report sees the dataset
        status = demo_status()
        self.assertGreater(status["total"], 0)

        # -- remove -----------------------------------------------------
        removal = teardown_demo_data()
        self.assertGreater(removal["total"], 0)
        for doctype, field in (("Person", "name_en"),
                               ("Institution", "name_en"),
                               ("Place", "name_en"),
                               ("Source", "title"),
                               ("Research Event", "title_en"),
                               ("Siraj Event", "title"),
                               ("Military Unit", "unit_name")):
            self.assertEqual(_tagged_names(doctype, field), [],
                             f"{doctype} demo records survived teardown")
        self.assertEqual(
            frappe.get_all("Relationship",
                           filters={"primary_source": ["in", demo_sources]},
                           limit_page_length=1), [])
        # teardown removed the manifest FILE (a bare assertFalse on the
        # path string could never pass — the string is always truthy)
        self.assertFalse(Path(frappe.get_site_path(MANIFEST_NAME)).exists())
