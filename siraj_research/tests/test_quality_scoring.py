# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
"""Live quality-scoring test (Phase 4).

The scores are computed presentation-time by
``profile_presentation.compute_quality_scores`` and injected into the
profile's Quality section by ``api.entity_profile``. This test exercises
that wiring end-to-end on a real Person: baseline unverified scoring, then
one evidence row shifting confidence to ``single_source`` and quality by
exactly the evidence weight.

Run with:
    bench --site frappe.com run-tests --module siraj_research.tests.test_quality_scoring
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from siraj_research.api.entity_profile import get_entity_profile
from siraj_research.profile_presentation import (
    CONFIDENCE_CODES,
    QUALITY_WEIGHTS,
)

PROBE_TAG = "Quality Probe"


def _quality_section(profile):
    return next(
        section
        for section in profile["sections"]
        if section["id"] == "quality"
    )


def _scores(profile):
    fields = {
        field["fieldname"]: field
        for field in _quality_section(profile)["fields"]
    }
    return fields


class TestQualityScoring(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = None
        cls.person = None
        # source_type is a Link to the "Source Type" registry, not a Select —
        # resolve a real registry name (seeded at install).
        types = frappe.get_all(
            "Source Type", pluck="name", limit=10, order_by="name"
        )
        if not types:
            self.skipTest("Source Type registry is not seeded")
        first_type = next((t for t in types if t == "report"), types[0])
        src = frappe.get_doc(
            {
                "doctype": "Source",
                "naming_series": "SRC-.####",
                "title": PROBE_TAG,
                "source_type": first_type,
            }
        )
        src.insert(ignore_permissions=True)
        cls.source = src.name

        person = frappe.get_doc(
            {
                "doctype": "Person",
                "display_name": PROBE_TAG,
                "name_en": PROBE_TAG,
                "name_ar": PROBE_TAG,
            }
        )
        person.insert(ignore_permissions=True)
        cls.person = person.name
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        for doctype, name in (("Person", cls.person), ("Source", cls.source)):
            if name and frappe.db.exists(doctype, name):
                try:
                    frappe.delete_doc(
                        doctype, name, force=True, ignore_permissions=True
                    )
                except Exception:
                    pass
        frappe.db.commit()

    def test_quality_section_is_computed_and_updates_with_evidence(self):
        profile = get_entity_profile("Person", self.person)
        fields = _scores(profile)

        # All three score fields render in the existing Quality group.
        self.assertEqual(
            [f["fieldname"] for f in _quality_section(profile)["fields"]],
            ["completeness_score", "quality_score", "confidence"],
        )
        self.assertEqual(fields["confidence"]["value"], "unverified")
        self.assertIn(fields["confidence"]["value"], CONFIDENCE_CODES)

        completeness = fields["completeness_score"]["value"]
        quality_before = fields["quality_score"]["value"]
        self.assertIsInstance(completeness, int)
        self.assertGreater(completeness, 0)
        self.assertLessEqual(completeness, 100)
        # No evidence, no source -> quality is completeness x 0.6.
        expected_base = int(
            QUALITY_WEIGHTS["completeness"] * completeness + 0.5
        )
        self.assertEqual(quality_before, expected_base)

        # One evidence row → confidence moves up one step and quality
        # gains exactly the per-row evidence share (25% ÷ 5 rows = 5).
        person = frappe.get_doc("Person", self.person)
        row = person.append(
            "evidence",
            {"source": self.source, "support_type": "supports"},
        )
        person.save(ignore_permissions=True)
        frappe.db.commit()

        profile_after = get_entity_profile("Person", self.person)
        fields_after = _scores(profile_after)
        self.assertEqual(fields_after["confidence"]["value"], "single_source")
        self.assertEqual(
            fields_after["quality_score"]["value"], quality_before + 5
        )
        self.assertEqual(
            fields_after["completeness_score"]["value"], completeness
        )
        self.assertIsNotNone(row)

    def test_confidence_scale_is_exposed(self):
        profile = get_entity_profile("Person", self.person)
        # The payload carries the ordered six-level scale for clients.
        from siraj_research.profile_presentation import compute_quality_scores

        raw = {"sections": profile["sections"], "children": profile["children"]}
        scores = compute_quality_scores(raw)
        self.assertEqual(scores["confidence_scale"], list(CONFIDENCE_CODES))
        self.assertEqual(len(scores["confidence_scale"]), 6)
