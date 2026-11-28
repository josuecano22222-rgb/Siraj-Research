# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
"""Tests for the geo document-hook extensions: the linked-Place coordinate
cascade, the Natural Earth country fallback, and meta-driven coverage.

Run on a live bench with:
    bench --site frappe.com run-tests --module siraj_research.tests.test_geo_doc_events
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from siraj_research.geo_doc_events import (
    _apply_natural_earth_country_fallback,
    _coords_from_linked_place,
    _linked_place_doctype,
)


def _doc(**values):
    """A real object (not a MagicMock) so hasattr/getattr reflect set fields."""
    doc = SimpleNamespace(
        doctype="Siraj Event", name="EVT-001",
        flags=SimpleNamespace(siraj_hierarchy_resolved=False),
    )
    for key, value in values.items():
        setattr(doc, key, value)
    return doc


class TestCoordsFromLinkedPlace(FrappeTestCase):
    def test_fetches_coordinates_from_linked_place(self):
        cfg = {"linked_place_field": "place"}
        doc = _doc(place="PL-001")
        mock_db = mock.MagicMock()
        mock_db.exists.return_value = True
        mock_db.get_value.return_value = (48.85, 2.35)
        with mock.patch(
            "siraj_research.geo_doc_events._linked_place_doctype",
            return_value="Place",
        ), mock.patch("siraj_research.geo_doc_events.frappe.db", mock_db):
            lat, lon = _coords_from_linked_place(doc, cfg)
        self.assertEqual((lat, lon), (48.85, 2.35))

    def test_no_place_returns_none(self):
        cfg = {"linked_place_field": "place"}
        doc = _doc(place=None)
        lat, lon = _coords_from_linked_place(doc, cfg)
        self.assertEqual((lat, lon), (None, None))

    def test_missing_linked_field_returns_none(self):
        cfg = {}
        doc = _doc()
        lat, lon = _coords_from_linked_place(doc, cfg)
        self.assertEqual((lat, lon), (None, None))


class TestLinkedPlaceDoctype(FrappeTestCase):
    def test_reads_field_options(self):
        df = mock.MagicMock()
        df.options = "Gazetteer Place"
        meta = mock.MagicMock()
        meta.get_field.return_value = df
        doc = _doc()
        with mock.patch.object(frappe, "get_meta", return_value=meta):
            self.assertEqual(
                _linked_place_doctype(doc, {}, "place"), "Gazetteer Place"
            )

    def test_falls_back_to_place(self):
        meta = mock.MagicMock()
        meta.get_field.return_value = mock.MagicMock(options=None)
        doc = _doc()
        with mock.patch.object(frappe, "get_meta", return_value=meta):
            self.assertEqual(_linked_place_doctype(doc, {}, "place"), "Place")


class TestNaturalEarthCountryFallback(FrappeTestCase):
    def test_fills_country_from_ne_when_gap(self):
        cfg = {"admin_fields": {"country": "country"}}
        doc = _doc(country=None)
        # Paris is France in NE; _resolve_country returns a real Country name.
        with mock.patch(
            "siraj_research.geo_hierarchy._resolve_country",
            return_value="France",
        ):
            _apply_natural_earth_country_fallback(doc, cfg, 48.85, 2.35)
        self.assertEqual(doc.country, "France")

    def test_skips_when_country_already_set(self):
        cfg = {"admin_fields": {"country": "country"}}
        doc = _doc(country="Netherlands")
        with mock.patch(
            "siraj_research.geo_hierarchy._resolve_country",
            return_value="France",
        ):
            _apply_natural_earth_country_fallback(doc, cfg, 48.85, 2.35)
        self.assertEqual(doc.country, "Netherlands")  # research input preserved

    def test_no_country_field_is_noop(self):
        cfg = {"admin_fields": {}}
        doc = _doc()
        _apply_natural_earth_country_fallback(doc, cfg, 48.85, 2.35)
        self.assertIsNone(getattr(doc, "country", None))
