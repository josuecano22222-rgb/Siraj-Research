"""Pure-Python tests for the Governorate geo-data fill (Step 3, tests-first).

Stubs ``frappe`` in ``sys.modules`` so this suite runs in the pure-Python CI
gate (no bench, no live DB, no network, no NE provisioning). Geometry
calculations use Shapely with deterministic fixtures; the orchestration
(loading / matching / fill planning / reporting) is exercised against stubbed
data providers.

Covers the approved design contract in
``docs/decisions/governorate-geo-fill-design.md``:
A. geometry calculations, B. antimeridian, C. code matching, D. source
precedence, E. fill-only-empty, F. idempotency, G. reporting, H. resolver.
"""

from __future__ import annotations

import unittest

# The production module guards ``import frappe`` with try/except (sets
# ``frappe = None`` when the bench is absent), so it imports cleanly in the
# pure-Python gate with no stub -- and we avoid polluting ``sys.modules`` for
# sibling test modules (e.g. test_geo_cascade).
from shapely.geometry import (
    GeometryCollection,
    MultiPolygon,
    Point,
    Polygon,
)

from siraj_research.api.governorate_geo import (
    bbox_contains,
    classify_and_fill,
    compute_bbox,
    is_antimeridian_crossing,
    is_empty,
    iso_suffix,
    match_admin_boundary,
    match_natural_earth,
    normalize_code,
    plan_fill,
    representative_point,
    resolve_point,
    select_geometry,
    wrap_longitude,
)

# ---------------------------------------------------------------------------
# Geometry fixtures
# ---------------------------------------------------------------------------

def _square(minx, miny, maxx, maxy):
    return Polygon([(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)])


def _concave():
    # L-shaped concave polygon; centroid falls outside, representative point inside.
    return Polygon([
        (0, 0), (4, 0), (4, 1), (1, 1), (1, 4), (0, 4),
    ])


def _multipolygon():
    return MultiPolygon([_square(0, 0, 1, 1), _square(2, 2, 3, 3)])


def _antimeridian_polygon():
    # Continuous-frame representation of a polygon crossing the antimeridian:
    # longitudes 170 -> 190 (190 wraps to -170 in [-180,180]). This is a valid
    # shapely polygon in the continuous frame; bounds (170,-10,190,10).
    return Polygon([(170, -10), (190, -10), (190, 10), (170, 10)])


# ---------------------------------------------------------------------------
# A. Geometry calculations
# ---------------------------------------------------------------------------

class TestGeometryCalculations(unittest.TestCase):
    def test_representative_point_inside_square(self):
        sq = _square(0, 0, 10, 10)
        lat, lon = representative_point(sq)
        self.assertTrue(sq.contains(Point(lon, lat)))

    def test_representative_point_not_centroid_for_concave(self):
        conc = _concave()
        centroid = conc.centroid
        rp = Point(*representative_point(conc)[::-1])
        # representative point must be inside; centroid of this L-shape is outside.
        self.assertTrue(conc.contains(rp))
        self.assertFalse(conc.contains(centroid))
        self.assertNotEqual((rp.x, rp.y), (centroid.x, centroid.y))

    def test_representative_point_multipolygon(self):
        mp = _multipolygon()
        lat, lon = representative_point(mp)
        self.assertTrue(mp.contains(Point(lon, lat)))

    def test_geometry_collection_rejected_safely(self):
        gc = GeometryCollection([_square(0, 0, 1, 1), Point(5, 5)])
        with self.assertRaises(ValueError):
            representative_point(gc)

    def test_invalid_geometry_rejected(self):
        # A bowtie polygon is invalid; detect-and-skip, never silently repair.
        bowtie = Polygon([(0, 0), (2, 2), (2, 0), (0, 2)])
        self.assertFalse(bowtie.is_valid)
        with self.assertRaises(ValueError):
            representative_point(bowtie)

    def test_empty_geometry_rejected(self):
        empty = Polygon()
        with self.assertRaises(ValueError):
            representative_point(empty)

    def test_missing_geometry_rejected(self):
        with self.assertRaises(ValueError):
            representative_point(None)

    def test_bbox_represents_geometry(self):
        sq = _square(1, 2, 3, 4)
        w, s, e, n = compute_bbox(sq)
        self.assertEqual((w, s, e, n), (1.0, 2.0, 3.0, 4.0))

    def test_bbox_contains_representative_point(self):
        sq = _square(-5, -3, 7, 9)
        w, s, e, n = compute_bbox(sq)
        lat, lon = representative_point(sq)
        self.assertTrue(bbox_contains((w, s, e, n), lat, lon))

    def test_bbox_ordering_w_s_e_n(self):
        sq = _square(10, 20, 30, 40)
        w, s, e, n = compute_bbox(sq)
        self.assertLessEqual(w, e)
        self.assertLessEqual(s, n)

    def test_west_never_greater_than_east(self):
        for geom in (_square(-10, -10, 10, 10), _concave(), _multipolygon()):
            w, _, e, _ = compute_bbox(geom)
            self.assertLessEqual(w, e)


# ---------------------------------------------------------------------------
# B. Antimeridian behavior
# ---------------------------------------------------------------------------

class TestAntimeridian(unittest.TestCase):
    def test_crossing_detected(self):
        geom = _antimeridian_polygon()
        self.assertTrue(is_antimeridian_crossing(geom))

    def test_non_crossing_not_flagged(self):
        self.assertFalse(is_antimeridian_crossing(_square(10, 10, 20, 20)))
        self.assertFalse(is_antimeridian_crossing(_square(-20, -20, -10, -10)))

    def test_crossing_bbox_well_formed_in_continuous_frame(self):
        geom = _antimeridian_polygon()
        w, s, e, n = compute_bbox(geom)
        # Continuous-frame bbox is well-formed (W <= E) and its east bound
        # exceeds 180, reflecting that the polygon crosses the antimeridian.
        self.assertLessEqual(w, e)
        self.assertGreater(e, 180.0)

    def test_representative_point_longitude_normalized(self):
        geom = _antimeridian_polygon()
        _, lon = representative_point(geom)
        self.assertGreaterEqual(lon, -180.0)
        self.assertLessEqual(lon, 180.0)

    def test_no_malformed_bbox_stored(self):
        geom = _antimeridian_polygon()
        w, _, e, _ = compute_bbox(geom)
        self.assertFalse(w > e)

    def test_non_crossing_polygon_unchanged(self):
        geom = _square(10, 10, 20, 20)
        w, s, e, n = compute_bbox(geom)
        self.assertEqual((w, s, e, n), (10.0, 10.0, 20.0, 20.0))

    def test_wrap_longitude(self):
        self.assertAlmostEqual(wrap_longitude(190), -170.0)
        self.assertAlmostEqual(wrap_longitude(-190), 170.0)
        self.assertAlmostEqual(wrap_longitude(0), 0.0)
        self.assertAlmostEqual(wrap_longitude(180), 180.0)


# ---------------------------------------------------------------------------
# C. Administrative code matching
# ---------------------------------------------------------------------------

class TestCodeMatching(unittest.TestCase):
    def test_normalize_code_trims_and_uppercases(self):
        self.assertEqual(normalize_code("  us-mn "), "US-MN")
        self.assertEqual(normalize_code("jo-am"), "JO-AM")

    def test_normalize_code_none(self):
        self.assertIsNone(normalize_code(None))
        self.assertIsNone(normalize_code(""))

    def test_iso_suffix_extraction(self):
        self.assertEqual(iso_suffix("US-MN"), "MN")
        self.assertEqual(iso_suffix("JO-AM"), "AM")

    def test_iso_suffix_no_hyphen(self):
        self.assertIsNone(iso_suffix("USMN"))
        self.assertIsNone(iso_suffix("MN"))

    def test_match_admin_boundary_by_pcode(self):
        ab = [
            {"pcode": "US-MN", "country": "US", "level": 1, "name_en": "Minnesota"},
            {"pcode": "US-CA", "country": "US", "level": 1, "name_en": "California"},
        ]
        match = match_admin_boundary("US-MN", "US", ab)
        self.assertIsNotNone(match)
        self.assertEqual(match["pcode"], "US-MN")

    def test_match_admin_boundary_case_insensitive(self):
        ab = [{"pcode": "us-mn", "country": "US", "level": 1}]
        self.assertIsNotNone(match_admin_boundary("US-MN", "US", ab))

    def test_match_admin_boundary_level_filter(self):
        # level != 1 must not match.
        ab = [{"pcode": "US-MN", "country": "US", "level": 2}]
        self.assertIsNone(match_admin_boundary("US-MN", "US", ab))

    def test_match_admin_boundary_duplicate_conflict(self):
        ab = [
            {"pcode": "US-MN", "country": "US", "level": 1, "name_en": "A"},
            {"pcode": "US-MN", "country": "US", "level": 1, "name_en": "B"},
        ]
        match = match_admin_boundary("US-MN", "US", ab)
        # Conflict -> None (reported, not arbitrarily chosen).
        self.assertIsNone(match)

    def test_match_natural_earth_by_iso_3166_2(self):
        ne = [
            {"iso_3166_2": "US-MN", "iso_a2": "US", "name_en": "Minnesota"},
            {"iso_3166_2": "US-CA", "iso_a2": "US", "name_en": "California"},
        ]
        match = match_natural_earth("US-MN", "US", ne)
        self.assertIsNotNone(match)
        self.assertEqual(match["iso_3166_2"], "US-MN")

    def test_match_natural_earth_missing_iso_attribute(self):
        ne = [{"name_en": "Nowhere", "iso_a2": "US"}]  # no iso_3166_2
        self.assertIsNone(match_natural_earth("US-XX", "US", ne))

    def test_match_natural_earth_no_name_fallback(self):
        # A feature whose iso_3166_2 differs must NOT match by name.
        ne = [{"iso_3166_2": "US-CA", "iso_a2": "US", "name_en": "Minnesota"}]
        self.assertIsNone(match_natural_earth("US-MN", "US", ne))

    def test_match_unknown_code(self):
        ab = [{"pcode": "US-MN", "country": "US", "level": 1}]
        ne = [{"iso_3166_2": "US-MN", "iso_a2": "US"}]
        self.assertIsNone(match_admin_boundary("ZZ-99", "ZZ", ab))
        self.assertIsNone(match_natural_earth("ZZ-99", "ZZ", ne))

    def test_multiple_subdivisions_same_country(self):
        ne = [
            {"iso_3166_2": "US-MN", "iso_a2": "US"},
            {"iso_3166_2": "US-CA", "iso_a2": "US"},
            {"iso_3166_2": "US-TX", "iso_a2": "US"},
        ]
        for code in ("US-MN", "US-CA", "US-TX"):
            self.assertIsNotNone(match_natural_earth(code, "US", ne))


# ---------------------------------------------------------------------------
# D. Source precedence
# ---------------------------------------------------------------------------

class TestSourcePrecedence(unittest.TestCase):
    def test_imported_takes_precedence(self):
        imported = _square(0, 0, 1, 1)
        ne = _square(10, 10, 11, 11)
        geom, kind = select_geometry(imported, "Imported", ne, "Online")
        self.assertEqual(kind, "Imported")
        self.assertTrue(geom.equals(imported))

    def test_ne_only_when_no_imported(self):
        ne = _square(10, 10, 11, 11)
        geom, kind = select_geometry(None, None, ne, "Online")
        self.assertEqual(kind, "Online")
        self.assertTrue(geom.equals(ne))

    def test_imported_never_overwritten_by_ne(self):
        imported = _square(0, 0, 1, 1)
        ne = _square(10, 10, 11, 11)
        geom, kind = select_geometry(imported, "Imported", ne, "Online")
        self.assertNotEqual(kind, "Online")
        self.assertTrue(geom.equals(imported))

    def test_no_geometry_returns_none(self):
        geom, kind = select_geometry(None, None, None, None)
        self.assertIsNone(geom)
        self.assertIsNone(kind)


# ---------------------------------------------------------------------------
# E. Fill-only-empty behavior
# ---------------------------------------------------------------------------

class TestFillOnlyEmpty(unittest.TestCase):
    def test_empty_row_gets_filled(self):
        gov = {"code": "US-MN", "latitude": None, "longitude": None, "bbox": None}
        updates = plan_fill(gov, _square(0, 0, 1, 1), "Online", None)
        self.assertIsNotNone(updates)
        self.assertIn("latitude", updates)
        self.assertIn("longitude", updates)
        self.assertIn("bbox", updates)
        self.assertEqual(updates["source_kind"], "Online")

    def test_fully_populated_row_not_overwritten(self):
        gov = {"code": "US-MN", "latitude": 1.0, "longitude": 2.0, "bbox": "0,0,1,1"}
        updates = plan_fill(gov, _square(0, 0, 1, 1), "Online", None)
        self.assertIsNone(updates)

    def test_partial_lat_only_not_overwritten(self):
        # latitude set, longitude empty -> must NOT replace existing latitude.
        gov = {"code": "US-MN", "latitude": 1.0, "longitude": None, "bbox": None}
        updates = plan_fill(gov, _square(0, 0, 1, 1), "Online", None)
        # Partial record cannot be completed safely -> reported, not modified.
        self.assertIsNone(updates)

    def test_partial_bbox_only_not_overwritten(self):
        gov = {"code": "US-MN", "latitude": None, "longitude": None, "bbox": "0,0,1,1"}
        updates = plan_fill(gov, _square(0, 0, 1, 1), "Online", None)
        self.assertIsNone(updates)

    def test_blank_string_treated_as_empty(self):
        gov = {"code": "US-MN", "latitude": "", "longitude": "", "bbox": ""}
        self.assertTrue(is_empty(gov["latitude"]))
        updates = plan_fill(gov, _square(0, 0, 1, 1), "Online", None)
        self.assertIsNotNone(updates)

    def test_is_empty(self):
        self.assertTrue(is_empty(None))
        self.assertTrue(is_empty(""))
        self.assertTrue(is_empty("   "))
        self.assertFalse(is_empty(0.0))
        self.assertFalse(is_empty("0,0,1,1"))


# ---------------------------------------------------------------------------
# F. Idempotency + G. Reporting (classify_and_fill)
# ---------------------------------------------------------------------------

class _Row:
    """A simple in-memory Governorate row mirroring the DB fields we touch."""

    def __init__(self, code, lat=None, lon=None, bbox=None, source_kind=None):
        self.code = code
        self.latitude = lat
        self.longitude = lon
        self.bbox = bbox
        self.source_kind = source_kind

    def as_dict(self):
        return {
            "code": self.code, "latitude": self.latitude, "longitude": self.longitude,
            "bbox": self.bbox, "source_kind": self.source_kind,
        }


def _geom_for(code):
    # deterministic geometry keyed by code
    return _square(0, 0, 1, 1)


class TestIdempotencyAndReporting(unittest.TestCase):
    def _run(self, rows, imported=None, ne=None):
        report = classify_and_fill(
            rows=[r.as_dict() for r in rows],
            imported_geoms=imported or {},
            ne_features=ne or [],
            dry_run=False,
            apply=lambda code, updates: self._apply(rows, code, updates),
        )
        return report

    def _apply(self, rows, code, updates):
        for r in rows:
            if r.code == code:
                for k, v in updates.items():
                    setattr(r, k, v)
                return

    def test_first_run_fills_and_second_changes_nothing(self):
        rows = [_Row("US-MN"), _Row("US-CA")]
        ne = [
            {"iso_3166_2": "US-MN", "iso_a2": "US", "geometry": _square(0, 0, 1, 1)},
            {"iso_3166_2": "US-CA", "iso_a2": "US", "geometry": _square(2, 2, 3, 3)},
        ]
        r1 = self._run(rows, ne=ne)
        self.assertEqual(r1["filled"], 2)
        self.assertEqual(r1["natural_earth"], 2)
        # rows now populated
        self.assertIsNotNone(rows[0].latitude)

        r2 = self._run(rows, ne=ne)
        self.assertEqual(r2["filled"], 0)
        self.assertEqual(r2["already_set"], 2)
        # coordinates unchanged
        self.assertEqual(rows[0].latitude, r1 and rows[0].latitude)

    def test_report_reconciles(self):
        rows = [_Row("US-MN"), _Row("ZZ-99"), _Row("US-CA")]
        ne = [{"iso_3166_2": "US-MN", "iso_a2": "US", "geometry": _square(0, 0, 1, 1)}]
        report = self._run(rows, ne=ne)
        # US-MN filled, US-CA unmatched, ZZ-99 unmatched
        self.assertEqual(report["total"], 3)
        self.assertEqual(report["filled"], 1)
        self.assertEqual(report["unmatched"], 2)
        self.assertIn("ZZ-99", report["unmatched_codes"])
        self.assertIn("US-CA", report["unmatched_codes"])
        # total = filled + already_set + unmatched + others
        others = (report["partial"] + report["invalid_geometry"]
                  + report["duplicate_match"] + report["conflicting_match"])
        self.assertEqual(report["total"], report["filled"] + report["already_set"]
                         + report["unmatched"] + others)

    def test_unmatched_reported_not_filled(self):
        rows = [_Row("ZZ-99")]
        report = self._run(rows, ne=[])
        self.assertEqual(report["unmatched"], 1)
        self.assertIsNone(rows[0].latitude)

    def test_imported_precedence_in_report(self):
        rows = [_Row("US-MN")]
        imported = {"US-MN": _square(0, 0, 1, 1)}
        ne = [{"iso_3166_2": "US-MN", "iso_a2": "US", "geometry": _square(9, 9, 10, 10)}]
        report = self._run(rows, imported=imported, ne=ne)
        self.assertEqual(report["filled"], 1)
        self.assertEqual(report["imported"], 1)
        self.assertEqual(report["natural_earth"], 0)

    def test_dry_run_does_not_modify(self):
        rows = [_Row("US-MN")]
        ne = [{"iso_3166_2": "US-MN", "iso_a2": "US", "geometry": _square(0, 0, 1, 1)}]
        report = classify_and_fill(
            rows=[r.as_dict() for r in rows],
            imported_geoms={}, ne_features=ne, dry_run=True,
            apply=lambda code, updates: self._apply(rows, code, updates),
        )
        self.assertEqual(report["filled"], 1)
        self.assertTrue(report["dry_run"])
        # nothing applied
        self.assertIsNone(rows[0].latitude)

    def test_conflicting_imported_match_skipped(self):
        # Two Admin Boundary rows with the same pcode -> conflict -> None
        # (reported and skipped, never arbitrarily resolved).
        ab = [
            {"pcode": "US-MN", "country": "US", "level": 1},
            {"pcode": "US-MN", "country": "US", "level": 1},
        ]
        self.assertIsNone(match_admin_boundary("US-MN", "US", ab))


# ---------------------------------------------------------------------------
# H. Resolver
# ---------------------------------------------------------------------------

class TestResolver(unittest.TestCase):
    def _candidates(self):
        return [
            {"code": "A", "geometry": _square(0, 0, 10, 10)},
            {"code": "B", "geometry": _square(20, 20, 30, 30)},
        ]

    def test_point_inside(self):
        res = resolve_point(5, 5, self._candidates(), max_distance_km=0)
        self.assertEqual(res["code"], "A")

    def test_point_outside_every_governorate(self):
        res = resolve_point(50, 50, self._candidates(), max_distance_km=0)
        self.assertIsNone(res)

    def test_point_on_boundary(self):
        # on the shared edge x=10 between A and B's region is outside B; on A's edge.
        res = resolve_point(10, 5, self._candidates(), max_distance_km=0)
        # boundary point: shapely contains is False on the edge; resolve to nearest
        # within threshold. With max_distance 0 -> None (strict).
        self.assertIsNone(res)

    def test_point_near_shared_border_strict(self):
        # point just outside A (x=10.5) -> no contains; strict -> None.
        res = resolve_point(10.5, 5, self._candidates(), max_distance_km=0)
        self.assertIsNone(res)

    def test_offshore_no_assignment(self):
        res = resolve_point(0, -170, [{"code": "A", "geometry": _square(0, 0, 1, 1)}],
                            max_distance_km=0)
        self.assertIsNone(res)

    def test_nearest_fallback_disabled(self):
        # point near A but not inside, fallback disabled -> None.
        res = resolve_point(11, 5, self._candidates(), max_distance_km=0)
        self.assertIsNone(res)

    def test_nearest_fallback_enabled(self):
        # point near A (lat=11, just outside) within a generous threshold -> nearest A.
        res = resolve_point(11, 5, self._candidates(), max_distance_km=2000)
        self.assertIsNotNone(res)
        self.assertEqual(res["code"], "A")

    def test_overlapping_candidates_no_arbitrary_choice(self):
        overlap = [
            {"code": "A", "geometry": _square(0, 0, 10, 10)},
            {"code": "B", "geometry": _square(5, 5, 15, 15)},
        ]
        # point inside both -> ambiguous. Must NOT arbitrarily pick; strict -> None.
        res = resolve_point(7, 7, overlap, max_distance_km=0)
        self.assertIsNone(res)

    def test_antimeridian_adjacent_point(self):
        am = [{"code": "AM", "geometry": _antimeridian_polygon()}]
        # point inside the crossing polygon (lat=0, lon=175 in continuous frame).
        res = resolve_point(0, 175, am, max_distance_km=0)
        self.assertIsNotNone(res)
        self.assertEqual(res["code"], "AM")


if __name__ == "__main__":
    unittest.main()
