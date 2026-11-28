"""Framework-independent tests for the Natural Earth country intelligence and
choropleth classification layer (``siraj_research.natural_earth_geography``).

These run without a Frappe site, exercising the bundled 1:110m pack directly.
"""

from __future__ import annotations

import unittest
from typing import ClassVar

from siraj_research.natural_earth_geography import (
    NaturalEarthGeographyError,
    aggregate_site_data,
    choropleth_from_values,
    class_index,
    classify,
    country_profile,
    enrich_country,
    find_country,
    geodesic_area_m2,
    iso_code,
    resolve_site_country,
)


class TestCountryIntelligence(unittest.TestCase):
    def test_find_country_by_coordinate(self):
        netherlands = find_country(4.90, 52.37)  # Amsterdam
        self.assertIsNotNone(netherlands)
        self.assertEqual(iso_code(netherlands), "NLD")
        france = find_country(2.35, 48.85)  # Paris
        self.assertEqual(iso_code(france), "FRA")

    def test_iso_code_falls_back_for_ne_minus_99(self):
        # Natural Earth stores France's ISO_A3 as '-99'; ADM0_A3 carries the real code.
        france = find_country(2.35, 48.85)
        self.assertEqual(france.get("ISO_A3"), "-99")
        self.assertEqual(iso_code(france), "FRA")

    def test_find_country_returns_none_over_open_ocean(self):
        self.assertIsNone(find_country(-30.0, -30.0))  # South Atlantic
        self.assertIsNone(find_country(0.0, 0.0))  # Gulf of Guinea

    def test_find_country_rejects_out_of_range(self):
        self.assertIsNone(find_country(200.0, 0.0))
        self.assertIsNone(find_country(0.0, 100.0))

    def test_country_profile_by_code(self):
        profile = country_profile("NLD")
        self.assertIsNotNone(profile)
        self.assertEqual(profile["name"], "Netherlands")
        self.assertEqual(profile["continent"], "Europe")
        self.assertEqual(profile["iso_a2"], "NL")
        self.assertEqual(profile["code"], "NLD")
        self.assertEqual(profile["adm0_code"], "NLD")
        self.assertGreater(profile["population_estimate"], 1_000_000)
        self.assertGreater(profile["gdp_million_usd"], 0)
        self.assertGreater(profile["area_km2"], 10_000)
        self.assertIsNotNone(profile["capital"])
        self.assertEqual(profile["capital"]["name"], "Amsterdam")
        self.assertEqual(profile["name_ar"], "هولندا")
        self.assertEqual(profile["capital"]["name_ar"], "أمستردام")
        self.assertEqual(profile["provenance"], "natural_earth_bundle")

    def test_adm0_code_valid_for_all_countries(self):
        # ADM0_A3 is the canonical choropleth join key — valid for every country
        # (ISO_A3 is -99 for 5, including France).
        from siraj_research.natural_earth_geography import _country_index, adm0_code

        codes = [adm0_code(p) for p, _b, _g in _country_index()]
        self.assertTrue(all(codes), "Every country must have an ADM0_A3 code")
        self.assertEqual(len(set(codes)), len(codes), "ADM0_A3 codes must be unique")
        france = next(
            p for p, _b, _g in _country_index()
            if p.get("NAME") == "France"
        )
        self.assertEqual(france.get("ISO_A3"), "-99")
        self.assertEqual(adm0_code(france), "FRA")

    def test_country_profile_by_coordinate_matches_code(self):
        by_point = country_profile(longitude=2.35, latitude=48.85)
        by_code = country_profile("FRA")
        self.assertEqual(by_point["code"], by_code["code"])
        self.assertEqual(by_point["name"], "France")

    def test_country_profile_unknown_returns_none(self):
        self.assertIsNone(country_profile("ZZZ"))
        self.assertIsNone(country_profile(longitude=-30.0, latitude=-30.0))

    def test_country_profile_rejects_non_numeric_coordinates(self):
        # HTTP form values arrive as strings; a bad coordinate must not raise.
        self.assertIsNone(country_profile(longitude="not-a-number", latitude="also-bad"))


class TestChoroplethClassification(unittest.TestCase):
    def test_quantile_breaks_are_increasing_and_end_at_max(self):
        result = classify([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], method="quantile", classes=5)
        self.assertFalse(result["empty"])
        self.assertEqual(result["min"], 1)
        self.assertEqual(result["max"], 10)
        self.assertEqual(result["breaks"], sorted(result["breaks"]))
        self.assertEqual(result["breaks"][-1], 10)
        self.assertTrue(
            all(a < b for a, b in zip(result["breaks"], result["breaks"][1:], strict=False))
        )

    def test_equal_interval_splits_range_evenly(self):
        result = classify([0, 100], method="equal_interval", classes=4)
        self.assertEqual(result["breaks"], [25, 50, 75, 100])

    def test_empty_and_single_value(self):
        empty = classify([])
        self.assertTrue(empty["empty"])
        self.assertEqual(empty["breaks"], [])
        single = classify([7, 7, 7])
        self.assertEqual(single["breaks"], [7])
        self.assertEqual(class_index(7, single["breaks"]), 0)

    def test_class_index_assignment(self):
        breaks = [25, 50, 75, 100]
        self.assertEqual(class_index(10, breaks), 0)
        self.assertEqual(class_index(25, breaks), 0)
        self.assertEqual(class_index(26, breaks), 1)
        self.assertEqual(class_index(100, breaks), 3)
        self.assertEqual(class_index(999, breaks), 3)

    def test_invalid_method_and_classes_raise(self):
        with self.assertRaises(NaturalEarthGeographyError):
            classify([1, 2], method="bogus")
        with self.assertRaises(NaturalEarthGeographyError):
            classify([1, 2], classes=1)
        with self.assertRaises(NaturalEarthGeographyError):
            classify([1, 2], classes=20)


class TestGeodesicArea(unittest.TestCase):
    def test_one_degree_square_near_equator(self):
        square = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
        area = geodesic_area_m2(square)
        expected = 1.236e10  # ~111.2 km x 111.2 km
        self.assertLess(abs(area - expected) / expected, 0.02)

    def test_hole_subtracts_area(self):
        outer = [[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]
        hole = [[0.5, 0.5], [1.5, 0.5], [1.5, 1.5], [0.5, 1.5], [0.5, 0.5]]
        solid = geodesic_area_m2({"type": "Polygon", "coordinates": [outer]})
        with_hole = geodesic_area_m2({"type": "Polygon", "coordinates": [outer, hole]})
        self.assertLess(with_hole, solid)
        self.assertGreater(with_hole, solid * 0.5)

    def test_multipolygon_sums_parts(self):
        part_a = [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]
        part_b = [[[10, 10], [11, 10], [11, 11], [10, 11], [10, 10]]]
        multi = geodesic_area_m2({"type": "MultiPolygon", "coordinates": [part_a, part_b]})
        single = geodesic_area_m2({"type": "Polygon", "coordinates": part_a})
        self.assertGreater(multi, single * 1.9)


class TestSiteDataAggregation(unittest.TestCase):
    RECORDS: ClassVar[list] = [
        {"latitude": 52.37, "longitude": 4.90, "country": "Netherlands", "value": 10},
        {"latitude": 48.85, "longitude": 2.35, "country": "France", "value": 20},
        {"latitude": 48.85, "longitude": 2.35, "country": "France", "value": 30},
        {"latitude": -30.0, "longitude": -30.0, "country": "", "value": 5},
        {"latitude": None, "longitude": None, "country_name": "Germany", "value": 7},
    ]

    def test_resolve_by_coordinate_and_name(self):
        self.assertEqual(resolve_site_country(latitude=50.11, longitude=8.68), "DEU")
        self.assertEqual(resolve_site_country(country_name="Germany"), "DEU")
        self.assertEqual(resolve_site_country(country_name="Atlantis"), "")

    def test_count_aggregation(self):
        result = aggregate_site_data(self.RECORDS, agg="count")
        self.assertEqual(result["NLD"], 1)
        self.assertEqual(result["FRA"], 2)
        self.assertEqual(result["DEU"], 1)
        self.assertEqual(result["unmatched"], 1)

    def test_sum_and_mean_aggregation(self):
        self.assertEqual(aggregate_site_data(self.RECORDS, agg="sum")["FRA"], 50.0)
        self.assertEqual(aggregate_site_data(self.RECORDS, agg="mean")["FRA"], 25.0)

    def test_invalid_aggregation_raises(self):
        with self.assertRaises(NaturalEarthGeographyError):
            aggregate_site_data(self.RECORDS, agg="median")

    def test_choropleth_from_values_payload(self):
        payload = choropleth_from_values({"NLD": 10, "FRA": 20, "DEU": 7}, method="quantile", classes=3)
        self.assertFalse(payload["empty"])
        self.assertEqual(payload["breaks"], sorted(payload["breaks"]))
        self.assertEqual(payload["breaks"][-1], 20)
        self.assertEqual(set(payload["classByKey"]), {"NLD", "FRA", "DEU"})
        self.assertEqual(payload["matchedCount"], 3)

    def test_choropleth_empty_values(self):
        payload = choropleth_from_values({}, method="quantile", classes=5)
        self.assertTrue(payload["empty"])
        self.assertEqual(payload["breaks"], [])
        self.assertEqual(payload["valueByKey"], {})


class TestCountryEnrichment(unittest.TestCase):
    def test_enrich_by_code(self):
        enriched = enrich_country("NLD")
        self.assertIsNotNone(enriched)
        self.assertEqual(enriched["name"], "Netherlands")
        self.assertEqual(enriched["name_ar"], "هولندا")
        self.assertEqual(enriched["iso_a3"], "NLD")
        self.assertEqual(enriched["adm0_code"], "NLD")
        self.assertEqual(enriched["provenance"], "natural_earth_bundle")

    def test_enrich_by_english_name(self):
        enriched = enrich_country("France")
        self.assertEqual(enriched["name"], "France")
        self.assertEqual(enriched["iso_a3"], "FRA")  # falls back from -99

    def test_enrich_by_arabic_name(self):
        enriched = enrich_country("هولندا")
        self.assertEqual(enriched["name"], "Netherlands")

    def test_enrich_unknown_returns_none(self):
        self.assertIsNone(enrich_country("Atlantis"))
        self.assertIsNone(enrich_country(""))
        self.assertIsNone(enrich_country(None))

    def test_enrich_chain_country_uses_resolved_name(self):
        from siraj_research.natural_earth_geography import enrich_chain_country

        result = {"lat": 4.9, "lon": 52.37,
                  "by_field": {"country": {"name": "Netherlands"}}}
        enriched = enrich_chain_country(result)
        self.assertEqual(enriched["name"], "Netherlands")
        self.assertEqual(enriched["name_ar"], "هولندا")

    def test_enrich_chain_country_falls_back_to_coordinate(self):
        # Coordinate over a country with no resolved name: NE identifies it.
        from siraj_research.natural_earth_geography import enrich_chain_country

        result = {"lat": 48.85, "lon": 2.35, "by_field": {"country": {}}}
        enriched = enrich_chain_country(result)
        self.assertEqual(enriched["name"], "France")
        self.assertEqual(enriched["iso_a3"], "FRA")

    def test_enrich_chain_country_ocean_returns_none(self):
        from siraj_research.natural_earth_geography import enrich_chain_country

        result = {"lat": -30.0, "lon": -30.0, "by_field": {"country": {}}}
        self.assertIsNone(enrich_chain_country(result))


if __name__ == "__main__":
    unittest.main()
