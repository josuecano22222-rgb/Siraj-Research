# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
"""Bench-side contract for the advanced map search endpoint.

Run with:
    bench --site frappe.com run-tests --module siraj_research.tests.test_map_search_api

The pure parsing/ranking rules live in repo-root tests/test_map_search.py;
this module pins the endpoint surface (whitelisting, scopes, exact
coordinate payloads) against a real site.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from siraj_research.api import map_search


class TestMapSearchApi(FrappeTestCase):
	def test_endpoint_is_whitelisted(self):
		self.assertTrue(getattr(map_search.search, "whitelisted", False))

	def test_empty_query_returns_empty_shape(self):
		result = map_search.search("")
		self.assertEqual(set(result), {
			"query", "scope", "coordinate", "regions", "places", "records", "counts",
		})
		self.assertIsNone(result["coordinate"])
		self.assertEqual(result["regions"], [])
		self.assertEqual(result["places"], [])
		self.assertEqual(result["records"], [])
		self.assertEqual(result["counts"], {"regions": 0, "places": 0, "records": 0})

	def test_textual_query_never_fabricates_coordinates(self):
		result = map_search.search("zzzz-not-a-place-qqq")
		self.assertIsNone(result["coordinate"])
		self.assertEqual(result["counts"]["regions"], 0)
		self.assertEqual(result["counts"]["places"], 0)

	def test_decimal_coordinate_is_exact_and_skips_text_scan(self):
		result = map_search.search("31.5900000000000001, 34.47")
		coord = result["coordinate"]
		self.assertEqual(coord["format"], "decimal")
		self.assertEqual(coord["lat"], "31.5900000000000001")
		self.assertEqual(coord["lon"], "34.47")
		# A coordinate answers for itself: no needless table scans.
		self.assertEqual(result["regions"], [])
		self.assertEqual(result["places"], [])

	def test_out_of_range_coordinate_returns_error_with_suggestion(self):
		result = map_search.search("100.2, 34.47")
		coord = result["coordinate"]
		self.assertEqual(coord["error"], "out_of_range")
		self.assertEqual(coord["suggestion"]["lat"], "34.47")
		self.assertEqual(coord["suggestion"]["lon"], "100.2")

	def test_scope_and_filters_are_sanitised(self):
		result = map_search.search("gaza", scope="nonsense", levels="1,junk,99",
		                           types="Source,Person", limit="999")
		self.assertEqual(result["scope"], "all")
		self.assertEqual(len(result["records"]), min(len(result["records"]), 25))

	def test_dms_coordinate_carries_exact_fraction(self):
		result = map_search.search('31°35\'24.5"N 34°28\'11.92"E')
		coord = result["coordinate"]
		self.assertEqual(coord["format"], "dms")
		self.assertEqual(coord["lat_fraction"], "227449/7200")

	def test_known_place_matches_when_gazetteer_loaded(self):
		"""If the gazetteer is live, its own rows must be findable by name."""
		if not frappe.db.count("Gazetteer Place"):
			self.skipTest("gazetteer not loaded on this site")
		row = frappe.get_list(
			"Gazetteer Place",
			fields=["name_en", "name_ar"],
			filters=[["name_en", "is", "set"]],
			limit_page_length=1,
		)
		if not row:
			self.skipTest("gazetteer rows have no name_en")
		needle = row[0]["name_en"]
		result = map_search.search(needle, scope="places")
		self.assertGreaterEqual(result["counts"]["places"], 1)
		self.assertTrue(
			any(p.get("name_en") == needle for p in result["places"]),
			f"{needle!r} not returned for its own exact query",
		)
