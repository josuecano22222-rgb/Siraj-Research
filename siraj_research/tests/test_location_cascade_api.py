# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
"""Tests for the unified hierarchical location-cascade API and the
meta-driven config builder.

Run on a live bench with:
    bench --site frappe.com run-tests --module siraj_research.tests.test_location_cascade_api

Covers ``resolve_location_chain`` (coordinate + place paths), the country
enrichment attachment, ``field_values`` mapping, permission gating, and
``build_cfg_from_meta`` (registered, derived, and non-coordinate cases).
"""

from __future__ import annotations

from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from siraj_research.api.location_cascade import (
    resolve_location_chain,
)
from siraj_research.geo_hierarchy_ui import build_cfg_from_meta


def _fake_chain(lat=4.9, lon=52.37):
    """A minimal display_resolution-style chain for Paris (FRA)."""
    return {
        "lat": lat, "lon": lon,
        "levels": [
            {"level": 0, "field": "country", "status": "linked",
             "name": "France", "label_en": "France", "code": "FRA"},
        ],
        "by_field": {"country": {"name": "France", "code": "FRA"}},
        "gaps": [], "warnings": [], "source": "local",
        "resolved_count": 1, "deepest_level": 0,
    }


class TestResolveLocationChainCoordinate(FrappeTestCase):
    def test_coordinate_path_attaches_enrichment(self):
        with mock.patch(
            "siraj_research.api.location_cascade.display_resolution",
            return_value=_fake_chain(),
        ), mock.patch(
            "siraj_research.api.location_cascade.field_values",
            return_value={"country": "France"},
        ):
            payload = resolve_location_chain(
                latitude=48.85, longitude=2.35, doctype="Siraj Event"
            )
        self.assertEqual(payload["source"], "coordinate")
        self.assertEqual(payload["country_enrichment"]["name"], "France")
        self.assertEqual(payload["country_enrichment"]["name_ar"], "فرنسا")
        self.assertEqual(payload["field_values"], {"country": "France"})
        self.assertEqual(payload["cfg"]["lat_field"], "latitude")

    def test_coordinate_path_requires_coordinates_or_place(self):
        with self.assertRaises(frappe.ValidationError):
            resolve_location_chain(latitude=None, longitude=None)


class TestResolveLocationChainPlace(FrappeTestCase):
    def test_place_path_resolves_from_place_coords(self):
        place = mock.MagicMock()
        place.get.side_effect = lambda field: {
            "latitude": 48.85, "longitude": 2.35,
        }.get(field)
        with mock.patch(
            "siraj_research.api.location_cascade.frappe.get_doc",
            return_value=place,
        ), mock.patch(
            "siraj_research.api.location_cascade.display_resolution",
            return_value=_fake_chain(lat=48.85, lon=2.35),
        ):
            payload = resolve_location_chain(
                place_doctype="Place", place_name="Paris"
            )
        self.assertEqual(payload["source"], "place")
        self.assertEqual(payload["place"]["name"], "Paris")
        self.assertEqual(payload["place"]["latitude"], 48.85)
        self.assertEqual(payload["country_enrichment"]["iso_a3"], "FRA")

    def test_place_without_coordinates_returns_error(self):
        place = mock.MagicMock()
        place.get.side_effect = lambda field: None
        with mock.patch(
            "siraj_research.api.location_cascade.frappe.get_doc",
            return_value=place,
        ):
            payload = resolve_location_chain(
                place_doctype="Place", place_name="Empty"
            )
        self.assertIn("error", payload)
        self.assertIn("place_no_coordinates", payload["warnings"])


class TestResolveLocationChainPermissions(FrappeTestCase):
    def test_requires_place_read(self):
        with mock.patch.object(frappe, "has_permission", return_value=False):
            with self.assertRaises(frappe.PermissionError):
                resolve_location_chain(latitude=1, longitude=2)


class TestBuildCfgFromMeta(FrappeTestCase):
    def _meta(self, fields):
        meta = mock.MagicMock()
        meta.has_field.side_effect = lambda f: f in fields
        meta.get_field.return_value = mock.MagicMock(options="Place")
        return meta

    def test_registered_doctype_returns_its_config(self):
        cfg = build_cfg_from_meta("Place")
        self.assertEqual(cfg["lat_field"], "latitude")
        self.assertEqual(cfg["linked_place_field"], "parent_place")
        self.assertIn("country", cfg["admin_fields"])

    def test_derived_config_for_custom_coordinate_doctype(self):
        fields = {"latitude", "longitude", "geo_point", "country",
                  "governorate", "district", "municipality", "village",
                  "community", "place_name", "place"}
        with mock.patch(
            "siraj_research.geo_hierarchy_ui.frappe.get_meta",
            return_value=self._meta(fields),
        ):
            cfg = build_cfg_from_meta("Custom Site")
        self.assertEqual(cfg["lat_field"], "latitude")
        self.assertEqual(cfg["linked_place_field"], "place")
        self.assertEqual(
            set(cfg["admin_fields"]),
            {"country", "governorate", "district", "municipality",
             "village", "community", "place_name"},
        )

    def test_non_coordinate_doctype_returns_empty(self):
        with mock.patch(
            "siraj_research.geo_hierarchy_ui.frappe.get_meta",
            return_value=self._meta({"name", "status"}),
        ):
            self.assertEqual(build_cfg_from_meta("Note"), {})
