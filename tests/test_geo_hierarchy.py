"""Pure-Python checks for the admin hierarchy bridge (no bench required)."""

from typing import ClassVar

import pytest

from siraj_research import geo_hierarchy as gh


def test_normalise_chain_maps_six_levels_and_reports_gaps():
    chain = {
        "country": {"name_en": "Iraq", "pcode": "IQ"},
        "governorate": {"name_en": "Damascus", "pcode": "SY-DI"},
        "municipality": {"name_en": "Greater Damascus", "pcode": "SY-DI-DM-DM"},
    }
    entries, gaps = gh.normalise_chain(chain)
    assert set(entries) == {"country", "governorate", "municipality"}
    assert entries["municipality"]["level"] == 3
    assert [g["field"] for g in gaps] == ["district", "village", "community"]


def test_legacy_community_alias_becomes_village():
    entries, gaps = gh.normalise_chain({"community": {"name_en": "Old village", "level": 4}})
    assert "village" in entries
    assert "community" not in entries
    assert "village" not in {g["field"] for g in gaps}


def test_duplicate_alias_is_dropped_but_real_level_five_is_kept():
    entries, _ = gh.normalise_chain({
        "village": {"name_en": "Al-Midan", "pcode": "V1"},
        "community": {"name_en": "Al-Midan", "pcode": "V1", "level": 4},
    })
    assert "community" not in entries
    entries, _ = gh.normalise_chain({
        "village": {"name_en": "Al-Midan", "pcode": "V1"},
        "community": {"name_en": "Souq", "pcode": "Q1", "level": 5},
    })
    assert entries["community"]["level"] == 5


def test_gazetteer_only_fills_village_with_low_confidence():
    entries, gaps = gh.normalise_chain(
        {"country": {"name_en": "Iraq"}},
        {"name_en": "Ain al-Tamu", "distance_m": 320},
    )
    assert entries["village"]["confidence"] == "low"
    assert entries["village"]["source"] == "gazetteer_nearest"
    assert "village" not in {g["field"] for g in gaps}


def test_chain_rows_are_parent_first_and_deterministic():
    entries, _ = gh.normalise_chain({
        "country": {"name_en": "Syria", "pcode": "SY"},
        "governorate": {"name_en": "Damascus", "pcode": "SY-DI"},
        "district": {"name_en": "Damascus", "pcode": "SY-DI-DM"},
        "village": {"name_en": "Al-Midan", "pcode": "SY-DI-DM-DM-MD"},
    })
    rows = gh.chain_rows(entries)
    assert [r["field"] for r in rows] == ["governorate", "district", "village"]
    assert rows[0]["parent_code"] is None
    assert rows[1]["parent_code"] == "SY-DI"
    assert rows[2]["ancestor_codes"]["district"] == "SY-DI-DM"
    assert gh.chain_rows(entries) == rows


def test_make_code_handles_arabic_names_and_collisions():
    assert gh.make_code("IQ-BG", "بغداد", "IQ", 1) == "IQ-BG"
    derived = gh.make_code(None, "بغداد", "IQ-BG", 2)
    assert derived.startswith("D-IQ-BG-")
    assert len(derived) <= gh.MAX_CODE_LENGTH
    assert derived == gh.make_code(None, "بغداد", "IQ-BG", 2)
    assert gh.normalize_code("IQ.BG") == "IQ-BG"
    assert gh.make_code("IQ.BG", "Baghdad", "IQ", 1) == "IQ-BG"


class _FakeGeom:
    def __init__(self, area, contains):
        self.area = area
        self._contains = contains

    def contains(self, point):
        return self._contains


def test_iso_from_pcode_handles_dots_and_dashes():
    assert gh._iso_from_pcode("IL.01.123") == "IL"
    assert gh._iso_from_pcode("PS-BTH-BL") == "PS"
    assert gh._iso_from_pcode("442267") is None


def test_containing_ancestors_prefers_smallest_polygon_per_level():
    candidates = [
        {"level": 1, "pcode": "IL", "geom": _FakeGeom(100, True)},
        {"level": 2, "pcode": "IL-01", "geom": _FakeGeom(20, True)},
        {"level": 2, "pcode": "IL-02", "geom": _FakeGeom(10, False)},
        {"level": 3, "pcode": "IL-01-A", "geom": _FakeGeom(2, True)},
        {"level": 5, "pcode": "IL-01-A-Q", "geom": _FakeGeom(0.5, True)},
    ]
    ancestors = gh.containing_ancestors(4, (0, 0), candidates)
    assert set(ancestors) == {1, 2, 3}
    assert ancestors[2][1]["pcode"] == "IL-01"


def test_level_helpers_and_editable_fields():
    assert gh.field_to_level("community") == 5
    assert gh.level_spec("3")["doctype"] == "Municipality"
    assert "label_ar" in gh.editable_fields(2)
    assert "boundary" in gh.editable_fields(4)
    assert gh.hierarchy_settings()["auto_create_missing"] is True


def test_containing_ancestors_includes_country_polygon():
    candidates = [
        {"level": 0, "pcode": "IL", "country": "Israel", "geom": _FakeGeom(1000, True)},
        {"level": 2, "pcode": "IL-01", "geom": _FakeGeom(20, True)},
    ]
    ancestors = gh.containing_ancestors(3, (0, 0), candidates)
    assert set(ancestors) == {0, 2}
    assert ancestors[0][1]["country"] == "Israel"


def test_resolve_country_document_accepts_iso_codes_and_names():
    countries = {"IL": "Israel", "Israel": "Israel", "PS": "Palestinian Territory, Occupied"}
    assert gh._resolve_country_document("IL", countries) == "Israel"
    assert gh._resolve_country_document("PS-WE", countries) == "Palestinian Territory, Occupied"
    assert gh._resolve_country_document("Israel", countries) == "Israel"


class _RecordingTree:
    """Fake STRtree: records the geometry list it was built from."""

    built: ClassVar[list] = []

    def __init__(self, geoms):
        type(self).built = list(geoms)
        self._geoms = list(geoms)

    def query(self, point):
        # Mimic STRtree.query: indices into the geometry list at build time.
        return [i for i, g in enumerate(self._geoms) if g.contains(point)]


def test_sorted_strtree_builds_tree_from_sorted_records():
    """Regression: tree indices must address the *sorted* records order.

    The old code built the STRtree first and sorted records afterwards, so
    every ``records[i]`` candidate picked through a tree index pointed at the
    wrong row and hierarchy sync skipped nearly every boundary.
    """
    _RecordingTree.built = []
    records = [
        # insertion order deliberately differs from (level, pcode) order
        {"level": 5, "pcode": "IL-01-A-Z", "geom": _FakeGeom(0.5, True)},
        {"level": 0, "pcode": "IL", "geom": _FakeGeom(100, True)},
        {"level": 2, "pcode": "IL-01", "geom": _FakeGeom(20, False)},
    ]
    tree = gh._sorted_strtree(records, strtree_cls=_RecordingTree)

    # Parent-first processing order is preserved.
    assert [r["pcode"] for r in records] == ["IL", "IL-01", "IL-01-A-Z"]
    # The tree was built from that SAME order — the core regression check.
    assert _RecordingTree.built == [r["geom"] for r in records]

    # Candidates fetched through tree indices are the records that actually
    # match, not whatever row happens to sit at that position.
    candidates = [records[i] for i in tree.query((0, 0))]
    assert [c["pcode"] for c in candidates] == ["IL", "IL-01-A-Z"]


def test_sorted_strtree_empty_records_returns_none():
    assert gh._sorted_strtree([]) is None


def test_sorted_strtree_with_real_shapely_candidates_align():
    pytest.importorskip("shapely")
    from shapely.geometry import Point, box

    records = [
        # scrambled insertion order: level 4 first, country last-but-inserted
        {"level": 4, "pcode": "XX-C", "geom": box(5, 5, 6, 6)},
        {"level": 0, "pcode": "XX", "geom": box(0, 0, 10, 10)},
        {"level": 2, "pcode": "XX-B", "geom": box(1, 1, 4, 4)},
        {"level": 1, "pcode": "XX-A", "geom": box(0.5, 0.5, 8, 8)},
    ]
    tree = gh._sorted_strtree(records)
    assert [r["pcode"] for r in records] == ["XX", "XX-A", "XX-B", "XX-C"]

    point = Point(2, 2)
    hits = [records[i] for i in tree.query(point)]
    assert {h["pcode"] for h in hits} == {"XX", "XX-A", "XX-B"}
    assert all(h["geom"].intersects(point) for h in hits)


def test_sync_hierarchy_spatial_country_inherits_despite_scrambled_rows(monkeypatch):
    """End-to-end guard: sync must find the country polygon for child rows.

    SQL has no ORDER BY, so rows arrive in arbitrary order. The country
    polygon is inserted LAST here — with a tree built before the sort, the
    district's candidate lookup misses it and the row is skipped (the ~97%
    skip regression observed on OSM-IL-PS).
    """
    pytest.importorskip("shapely")
    import sys
    import types
    from types import SimpleNamespace

    from shapely import wkb as shapely_wkb
    from shapely.geometry import box

    # sync imports geo_import, which imports frappe unconditionally.
    monkeypatch.setitem(sys.modules, "frappe", types.ModuleType("frappe"))
    import siraj_research.geo_import as geo_import

    monkeypatch.setattr(geo_import, "deps_ok", lambda: (True, []))
    monkeypatch.setattr(geo_import, "shapely", sys.modules.get("shapely") or __import__("shapely"))

    def _row(name, pcode, level, name_en, geom, country=None):
        hex_wkb = shapely_wkb.dumps(geom).hex()
        return SimpleNamespace(
            name=name, pcode=pcode, level=level, name_en=name_en, name_ar=None,
            country=country, parent_pcode=None,
            centroid_lat=geom.centroid.y, centroid_lon=geom.centroid.x,
            bbox=None, source_id=None,
            simplified_wkb=hex_wkb, full_wkb=hex_wkb,
        )

    village_geom = box(6, 6, 8, 8)
    district_geom = box(2, 2, 5, 5)
    country_geom = box(0, 0, 10, 10)
    rows = [
        # Deliberately adversarial order: country LAST.
        _row("BV", "OSM-VILL", 4, "Village Q", village_geom),
        _row("BD", "OSM-DIST", 2, "District Q", district_geom),
        _row("BC", "OSM-CTRY", 0, "Israel", country_geom, country="Israel"),
    ]

    fake_frappe = SimpleNamespace(
        db=SimpleNamespace(sql=lambda *a, **k: rows, commit=lambda: None),
        get_all=lambda *a, **k: [{"name": "Israel", "code": "IL"}],
    )
    monkeypatch.setattr(gh, "frappe", fake_frappe)
    monkeypatch.setattr(gh, "_country_names", lambda: {"IL": "Israel", "Israel": "Israel"})

    created = []

    def _fake_upsert(entry, parent_name, **kwargs):
        created.append((entry["code"], entry["field"], parent_name))
        return {"name": entry["code"], "status": "created"}

    monkeypatch.setattr(gh, "upsert_level", _fake_upsert)

    result = gh.sync_hierarchy_from_boundaries("OSM-TEST")

    assert result["synced"] == 2, result
    assert result["skipped"] == 0, result
    # District and village both attach to the country found via the tree.
    assert ("OSM-DIST", "district", "Israel") in created
    assert ("OSM-VILL", "village", "Israel") in created
