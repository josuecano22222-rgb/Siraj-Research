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
		# Frappe registers whitelisted functions in the frappe.whitelisted
		# collection (a set on develop, a list on older versions) — it does
		# NOT set a ``whitelisted`` attribute on the function itself.
		import frappe

		self.assertIn(map_search.search, frappe.whitelisted)

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

	def test_coordinate_carries_chain_missing_levels_and_nearby(self):
		result = map_search.search("31.5, 34.47", radius=10000)
		coord = result["coordinate"]
		# Full chain with explicitly missing levels (ocean points return
		# everything missing — never an exception).
		self.assertIn("admin_chain", coord)
		self.assertIn("missing_levels", coord)
		self.assertIsInstance(coord["missing_levels"], list)
		self.assertIn("on_land", coord)
		self.assertIn("nearby", coord)
		self.assertIsInstance(coord["nearby"], list)
		self.assertEqual(coord["radius_m"], 10000.0)
		for item in coord["nearby"]:
			self.assertIn("distance_m", item)
			self.assertLessEqual(item["distance_m"], 10000.0)

	def test_ocean_point_resolves_with_all_levels_missing(self):
		# Mid-Atlantic: valid coordinates, no country — explicit, not fatal.
		result = map_search.search("0, -30")
		coord = result["coordinate"]
		self.assertEqual(coord["format"], "decimal")
		self.assertEqual(len(coord["missing_levels"]), 6)
		self.assertFalse(coord["on_land"])

	def test_bbox_search_shape_and_invalid_input(self):
		ok = map_search.search_bbox(31.4, 34.3, 31.6, 34.6)
		self.assertNotIn("error", ok)
		self.assertEqual(set(ok), {"bbox", "records", "places", "regions", "counts"})
		self.assertEqual(len(ok["bbox"]), 4)
		bad = map_search.search_bbox("x", 0, 1, 1)
		self.assertEqual(bad["error"], "invalid_bbox")
		out_of_range = map_search.search_bbox(-95, 0, 10, 10)
		self.assertEqual(out_of_range["error"], "invalid_bbox")

	def test_bbox_search_wraps_antimeridian(self):
		result = map_search.search_bbox(0, 170, 10, -170)
		self.assertNotIn("error", result)
		self.assertEqual(result["bbox"], ["0", "170", "10", "-170"])

	def test_bbox_echo_keeps_caller_strings_verbatim(self):
		# Never round-trip the reply through float: '31.590000000000001'
		# must come back byte-identical, not as '31.59'.
		result = map_search.search_bbox(
			"31.590000000000001", "34.47", "31.6", "34.6")
		self.assertNotIn("error", result)
		self.assertEqual(
			result["bbox"],
			["31.590000000000001", "34.47", "31.6", "34.6"])

	def test_region_children_cascade_levels(self):
		countries = map_search.region_children(0)
		self.assertNotIn("error", countries)
		self.assertEqual(countries["level"], 0)
		self.assertIsInstance(countries["children"], list)
		bad = map_search.region_children("junk")
		self.assertEqual(bad["error"], "invalid_level")
		too_big = map_search.region_children(9)
		self.assertEqual(too_big["error"], "invalid_level")
		# Level 1 without a parent lists governorates (registry-dependent).
		govs = map_search.region_children(1)
		self.assertNotIn("error", govs)
		self.assertEqual(govs["level"], 1)
		if govs["children"]:
			child = govs["children"][0]
			self.assertIn("name", child)
			self.assertIn("centroid", child)
			# Level 2 children of that governorate link back through the field.
			districts = map_search.region_children(2, parent=child["name"])
			self.assertNotIn("error", districts)

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
