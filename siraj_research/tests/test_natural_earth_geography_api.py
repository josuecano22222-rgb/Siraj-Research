# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
"""Tests for the country-intelligence and site-data choropleth API endpoints.

Run on a live bench with:
    bench --site frappe.com run-tests --module siraj_research.tests.test_natural_earth_geography_api

The pure country-intelligence / classification logic is covered by
``test_natural_earth_geography`` (framework-independent). This module covers
the Frappe-facing ``country_profile`` and ``country_choropleth`` endpoints:
profile lookups by code/coordinate, endpoint validation, the aggregation
wiring (with ``frappe.get_list`` mocked to synthetic Siraj rows), and the
fail-closed path when the caller cannot read the site doctype.
"""

from __future__ import annotations

from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from siraj_research.api.natural_earth_vector import (
    country_choropleth,
    country_profile,
)


def _fake_meta(module="Siraj Research", has_latlon=True):
    """Build a minimal DocumentMeta stand-in for endpoint validation tests."""
    meta = mock.MagicMock()
    meta.module = module
    meta.has_field.side_effect = (
        lambda field: field in ("latitude", "longitude") if has_latlon else False
    )
    return meta


class TestCountryProfileEndpoint(FrappeTestCase):
    def test_profile_by_code(self):
        profile = country_profile(code="NLD")
        assert profile is not None
        assert profile["code"] == "NLD"
        assert profile["adm0_code"] == "NLD"
        assert profile["name"] == "Netherlands"
        assert profile["capital"]["name"] == "Amsterdam"
        assert profile["continent"] == "Europe"
        assert profile["name_ar"]  # Arabic name populated from the bundle

    def test_profile_by_coordinate(self):
        # Paris resolves to France even though NE stores ISO_A3='-99' for France.
        profile = country_profile(longitude=2.35, latitude=48.85)
        assert profile is not None
        assert profile["code"] == "FRA"
        assert profile["adm0_code"] == "FRA"
        assert profile["name"] == "France"

    def test_profile_over_ocean_returns_none(self):
        assert country_profile(longitude=-30.0, latitude=-30.0) is None

    def test_profile_unknown_code_returns_none(self):
        assert country_profile(code="ZZZ") is None


class TestCountryChoroplethValidation(FrappeTestCase):
    def test_non_siraj_doctype_rejected(self):
        with mock.patch(
            "siraj_research.api.natural_earth_vector.frappe.get_meta",
            return_value=_fake_meta(module="Core"),
        ):
            with self.assertRaises(frappe.PermissionError):
                country_choropleth(doctype="User")

    def test_doctype_without_coordinates_rejected(self):
        with mock.patch(
            "siraj_research.api.natural_earth_vector.frappe.get_meta",
            return_value=_fake_meta(module="Siraj Research", has_latlon=False),
        ):
            with self.assertRaises(frappe.ValidationError):
                country_choropleth(doctype="Data Group")

    def test_invalid_aggregation_rejected(self):
        with mock.patch(
            "siraj_research.api.natural_earth_vector.frappe.get_meta",
            return_value=_fake_meta(),
        ):
            with self.assertRaises(frappe.ValidationError):
                country_choropleth(doctype="Place", agg="median")

    def test_sum_requires_numeric_value_field(self):
        meta = _fake_meta()
        meta.get_field.return_value = None  # no such numeric field
        with mock.patch(
            "siraj_research.api.natural_earth_vector.frappe.get_meta",
            return_value=meta,
        ):
            with self.assertRaises(frappe.ValidationError):
                country_choropleth(doctype="Place", agg="sum", value_field="not_a_field")


class TestCountryChoroplethAggregation(FrappeTestCase):
    def test_count_aggregation_matches_adm0_codes(self):
        rows = [
            {"latitude": 52.37, "longitude": 4.90, "country": "Netherlands"},
            {"latitude": 48.85, "longitude": 2.35, "country": "France"},
            {"latitude": 48.85, "longitude": 2.35, "country": "France"},
            {"latitude": 50.11, "longitude": 8.68, "country": "Germany"},
        ]
        with mock.patch(
            "siraj_research.api.natural_earth_vector.frappe.get_meta",
            return_value=_fake_meta(),
        ), mock.patch(
            "siraj_research.api.natural_earth_vector.frappe.get_list",
            return_value=rows,
        ):
            payload = country_choropleth(doctype="Place", agg="count")

        assert payload["source"] == "siraj_site_data"
        assert payload["recordCount"] == 4            # records aggregated
        assert payload["matchedCount"] == 3            # distinct countries colored
        assert payload["matchedCount"] == len(payload["valueByKey"])
        assert payload["valueByKey"]["FRA"] == 2
        assert payload["valueByKey"]["NLD"] == 1
        assert payload["valueByKey"]["DEU"] == 1
        # breaks are increasing and end at the observed maximum (2)
        assert payload["breaks"] == sorted(payload["breaks"])
        assert payload["breaks"][-1] == 2
        assert payload["empty"] is False

    def test_sum_aggregation(self):
        rows = [
            {"latitude": 52.37, "longitude": 4.90, "country": "Netherlands",
             "geo_uncertainty_m": 10.0},
            {"latitude": 48.85, "longitude": 2.35, "country": "France",
             "geo_uncertainty_m": 30.0},
        ]
        meta = _fake_meta()
        meta.get_field.return_value = mock.MagicMock(fieldtype="Float")
        with mock.patch(
            "siraj_research.api.natural_earth_vector.frappe.get_meta",
            return_value=meta,
        ), mock.patch(
            "siraj_research.api.natural_earth_vector.frappe.get_list",
            return_value=rows,
        ):
            payload = country_choropleth(
                doctype="Place", agg="sum", value_field="geo_uncertainty_m"
            )
        assert payload["valueByKey"]["FRA"] == 30.0
        assert payload["valueByKey"]["NLD"] == 10.0

    def test_fail_closed_when_no_read_access(self):
        with mock.patch(
            "siraj_research.api.natural_earth_vector.frappe.get_meta",
            return_value=_fake_meta(),
        ), mock.patch(
            "siraj_research.api.natural_earth_vector.frappe.get_list",
            side_effect=frappe.exceptions.PermissionError("no read"),
        ):
            payload = country_choropleth(doctype="Place")

        # No site data leaks to a caller without read access.
        assert payload["empty"] is True
        assert payload["valueByKey"] == {}
        assert payload["classByKey"] == {}
        assert payload["source"] == "no_access"
        assert payload["recordCount"] == 0
