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
    # pyogrio returns `fields` as a numpy array, not a list.
    meta = {"fields": np.array(["name", "admin_level"])}
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


def test_source_country_value_uses_lowercased_osm_tags(_fake_frappe):
    gi = _fake_frappe
    props = {
        "name": "Gaza",
        "iso3166-1:alpha2": None,
        "iso3166-2": "PS-GZ",
    }
    assert gi._source_country_value(props) == "PS-GZ"


def test_wkb_hex_returns_text_with_shapely_two(_fake_frappe):
    pytest.importorskip("shapely")
    from shapely.geometry import Point

    gi = _fake_frappe
    value = gi._wkb_hex(Point(0, 0))
    assert isinstance(value, str)
    assert value.startswith("01")


def test_derived_pcode_is_stable_without_source_ids(_fake_frappe):
    gi = _fake_frappe
    first = gi._derived_pcode(3, "Gaza", (34.2, 31.2, 34.4, 31.4))
    second = gi._derived_pcode(3, "Gaza", (34.2, 31.2, 34.4, 31.4))
    other = gi._derived_pcode(3, "Nablus", (35.0, 32.0, 35.2, 32.2))
    assert first == second
    assert first.startswith("OSM-")
    assert first != other


def test_admin_boundary_name_en_falls_back_to_pcode(_fake_frappe):
    gi = _fake_frappe
    created = []

    class FakeDoc:
        def __init__(self, doctype, values=None):
            self.doctype = doctype
            self.flags = types.SimpleNamespace()
            for key, value in (values or {}).items():
                setattr(self, key, value)

        def get(self, key, default=None):
            return getattr(self, key, default)

        def save(self, **kwargs):
            created.append(self)

    db = types.SimpleNamespace(
        get_value=lambda *a, **k: None,
        exists=lambda *a, **k: None,
    )
    fake = types.SimpleNamespace(
        db=db,
        get_doc=lambda dt, name: FakeDoc(dt, {"name": name}),
        new_doc=lambda dt: FakeDoc(dt),
        get_meta=lambda dt: types.SimpleNamespace(has_field=lambda f: False),
    )
    gi.frappe = fake
    assert gi._upsert_admin_boundary("DS", 3, {"pcode": "OSM-X"}, False) is True
    assert created[0].name_en == "OSM-X"


def test_reimport_does_not_rewrite_set_only_once_admin_fields(_fake_frappe):
    gi = _fake_frappe
    saved = []

    class FakeDoc:
        def __init__(self, doctype, values=None):
            self.doctype = doctype
            self.flags = types.SimpleNamespace()
            for key, value in (values or {}).items():
                setattr(self, key, value)

        def get(self, key, default=None):
            return getattr(self, key, default)

        def save(self, **kwargs):
            saved.append(self)

    doc = FakeDoc("Admin Boundary", {
        "name": "AB1", "level": 2, "pcode": "OSM-X", "country": "Israel",
    })
    db = types.SimpleNamespace(
        get_value=lambda *a, **k: "AB1",
        exists=lambda *a, **k: None,
    )
    fake = types.SimpleNamespace(
        db=db,
        get_doc=lambda dt, name: doc,
        new_doc=lambda dt: FakeDoc(dt),
        get_meta=lambda dt: types.SimpleNamespace(has_field=lambda f: False),
    )
    gi.frappe = fake
    assert gi._upsert_admin_boundary("DS", 5, {
        "pcode": "OSM-X", "name_en": "New name", "country": "Palestinian Territory, Occupied",
    }, False) is True
    assert saved == [doc]
    assert doc.level == 2
    assert doc.pcode == "OSM-X"
    assert doc.country == "Israel"
    assert doc.name_en == "New name"
