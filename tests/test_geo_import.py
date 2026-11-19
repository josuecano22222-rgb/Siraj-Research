"""Pure checks for vector-import field mapping (no bench required)."""

import sys
import types

import pytest


@pytest.fixture(autouse=True)
def _fake_frappe(monkeypatch):
    fake = types.ModuleType("frappe")
    monkeypatch.setitem(sys.modules, "frappe", fake)
    import importlib

    import siraj_research.geo_import as gi

    importlib.reload(gi)
    return gi


def test_osm_admin_level_maps_to_siraj_chain(_fake_frappe):
    gi = _fake_frappe
    expected = {2: 0, 3: 1, 4: 1, 5: 2, 6: 2, 7: 3, 8: 3, 9: 4, 10: 5, 11: 5}
    for osm_level, siraj_level in expected.items():
        assert gi.osm_level_to_siraj(osm_level) == siraj_level
    assert gi.osm_level_to_siraj("nonsense") is None


def test_osm_field_aliases_are_recognised(_fake_frappe):
    gi = _fake_frappe
    assert "osm_id" in gi.POLYGON_FIELDS["pcode"]
    assert "name:ar" in gi.POLYGON_FIELDS["name_ar"]
    assert "admin_level" in gi.POLYGON_FIELDS["osm_admin_level"]


def test_pyogrio_result_compatibility(_fake_frappe):
    gi = _fake_frappe
    meta = {"fields": ["name", "admin_level"]}
    fields = (["Gaza", "Nablus"], [8, 9])
    old_result = (meta, fields, [None, None])
    new_result = (meta, None, [None, None], fields)
    for result in (old_result, new_result):
        normalized_meta, normalized_fields, geometry = gi._normalize_pyogrio_result(result)
        assert normalized_meta is meta
        assert normalized_fields is fields
        assert geometry == [None, None]


def test_iter_features_reads_new_pyogrio_four_tuple(monkeypatch, _fake_frappe):
    from pathlib import Path

    import numpy as np

    gi = _fake_frappe
    meta = {"fields": ["name", "admin_level"]}
    fields = (np.array(["Gaza"]), np.array([8]))
    fake_raw = types.SimpleNamespace(
        read=lambda path, **kwargs: (meta, None, [None], fields),
    )
    fake_pyogrio = types.SimpleNamespace(
        raw=fake_raw,
        read_info=lambda path, **kwargs: {"features": 1},
    )
    monkeypatch.setattr(gi, "_IO_BACKEND", "pyogrio")
    monkeypatch.setattr(gi, "pyogrio", fake_pyogrio)
    monkeypatch.setitem(sys.modules, "pyogrio", fake_pyogrio)

    features = list(gi._iter_features(Path("boundaries.geojson"), "utf-8", 500))
    assert len(features) == 1
    assert features[0]["properties"] == {"name": "Gaza", "admin_level": 8}


def test_country_resolution_helpers(_fake_frappe):
    gi = _fake_frappe
    by_code = {"IL": "Israel", "PS": "Palestinian Territory, Occupied"}
    by_name = {name.upper(): name for name in by_code.values()}
    assert gi._resolve_country_name("IL", by_code, by_name) == "Israel"
    assert gi._resolve_country_name("PS-WE", by_code, by_name) == "Palestinian Territory, Occupied"
    assert gi._resolve_country_name(
        "Palestinian Territory, Occupied", by_code, by_name
    ) == "Palestinian Territory, Occupied"
    assert gi._country_candidates_from_dataset("OSM-IL-PS", by_code) == ["IL", "PS"]
    assert gi._country_candidates_from_dataset("GADM-ADM5", by_code) == []
