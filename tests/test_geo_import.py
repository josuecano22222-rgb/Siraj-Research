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
