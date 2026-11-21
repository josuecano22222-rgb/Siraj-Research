"""Pure-Python checks for OSM admin_level -> SIRAJ hierarchy level (no bench)."""

import sys
import types

import pytest


@pytest.fixture()
def geo_import(monkeypatch):
    # geo_import imports frappe unconditionally at module level.
    monkeypatch.setitem(sys.modules, "frappe", types.ModuleType("frappe"))
    from siraj_research import geo_import as mod

    return mod


def test_osm_level_to_siraj_mapping(geo_import):
    assert geo_import.osm_level_to_siraj("2") == 0
    assert geo_import.osm_level_to_siraj(4) == 1
    assert geo_import.osm_level_to_siraj("6") == 2
    assert geo_import.osm_level_to_siraj(8) == 3
    assert geo_import.osm_level_to_siraj(9) == 4
    assert geo_import.osm_level_to_siraj("10") == 5
    assert geo_import.osm_level_to_siraj(None) is None
    assert geo_import.osm_level_to_siraj("") is None
    assert geo_import.osm_level_to_siraj("abc") is None


def test_feature_hierarchy_level_osm_column_owns_mapping(geo_import):
    # admin_level <= 2 stays a country (0) — never clobbered to 1 by `or level`.
    assert geo_import.feature_hierarchy_level({"osm_admin_level": "2"}, dataset_level=1) == 0
    assert geo_import.feature_hierarchy_level({"osm_admin_level": "4"}, dataset_level=1) == 1
    # Empty/unmappable admin_level on an OSM source: geometry-only row.
    assert geo_import.feature_hierarchy_level({"osm_admin_level": None}, dataset_level=1) == 0
    assert geo_import.feature_hierarchy_level({"osm_admin_level": ""}, dataset_level=1) == 0
    # Sources without the column (GADM) keep the dataset default.
    assert geo_import.feature_hierarchy_level({}, dataset_level=3) == 3


def test_untagged_junk_never_becomes_governorate(geo_import):
    # Eyeballed OSM-IL-PS reality: a church/locality with no admin_level
    # must not land in the editable hierarchy at level 1.
    church = {"osm_admin_level": None, "name_en": "Église Sainte-Anne de Jérusalem"}
    assert geo_import.feature_hierarchy_level(church, dataset_level=1) == 0


def test_map_country_label_accepts_bilingual_level0_labels(geo_import):
    by_code = {"IL": "Israel", "PS": "Palestinian Territory, Occupied"}
    by_name = {"ISRAEL": "Israel"}
    # English label resolved directly.
    assert geo_import._map_country_label("Israel", None, by_code, by_name) == "Israel"
    # Arabic label resolves through the shipped reference codes.
    assert (geo_import._map_country_label("فلسطين", None, by_code, by_name)
            == "Palestinian Territory, Occupied")
    # Derived (hash) name_en is never mapped; a real Arabic name_ar still is.
    assert (geo_import._map_country_label("OSM-ABCDEF0123456789", "إسرائيل", by_code, by_name)
            == "Israel")
    assert geo_import._map_country_label("OSM-ABCDEF0123456789", None, by_code, by_name) is None


def test_map_country_label_never_guesses_unknown_labels(geo_import):
    assert geo_import._map_country_label("Narnia", None, {}, {}) is None
    assert geo_import._map_country_label(None, None, {}, {}) is None
