"""Pure-Python checks for the polygon-containment admin chain (no bench).

The production bug these guard against: the resolver built ``admin_chain``
only by walking ``parent_pcode`` from the finest polygon *and* wrote
capitalised DocType keys, so OSM exports (which ship no parent codes)
reached the client with nothing but the record-country fallback — which,
when the imported ``country`` column was wrong, meant "United States"
everywhere.
"""

import sys
import types

import pytest


@pytest.fixture()
def geo_resolve(monkeypatch):
    # geo_resolve imports frappe (and geo_import, which imports frappe)
    # unconditionally at module level and decorates endpoints with
    # @frappe.whitelist() at import time.
    stub = types.ModuleType("frappe")
    stub.whitelist = lambda *a, **k: (lambda fn: fn)
    monkeypatch.setitem(sys.modules, "frappe", stub)
    from siraj_research.api import geo_resolve as mod

    return mod


def _rec(level, pcode, name_en, parent_pcode=None, country=None):
    return {"level": level, "pcode": pcode, "name_en": name_en, "name_ar": None,
            "parent_pcode": parent_pcode, "country": country}


def test_containment_levels_survive_missing_parent_codes(geo_resolve):
    # OSM-style import: parent_pcode is NULL on every record.
    best = {
        0: _rec(0, "OSM-AAAA", "Israel"),
        1: _rec(1, "OSM-BBBB", "Central"),
        3: _rec(3, "OSM-DDDD", "Tel Aviv"),
    }
    chain = geo_resolve.build_admin_chain(best, {})
    # Keys must be the lowercase chain fields normalise_chain reads back.
    assert set(chain) == {"country", "governorate", "municipality"}
    assert chain["country"]["name_en"] == "Israel"
    assert chain["governorate"]["pcode"] == "OSM-BBBB"
    assert chain["municipality"]["pcode"] == "OSM-DDDD"


def test_parent_walk_only_fills_levels_without_a_containing_polygon(geo_resolve):
    gov = _rec(1, "G1", "Central")
    district = _rec(2, "D1", "Tel Aviv", parent_pcode="G1")
    best = {0: _rec(0, "IL", "Israel"), 2: district}
    chain = geo_resolve.build_admin_chain(best, {"G1": gov})
    assert chain["country"]["pcode"] == "IL"
    assert chain["district"]["pcode"] == "D1"
    assert chain["governorate"]["pcode"] == "G1"  # filled via parent walk


def test_country_fallback_only_when_no_level_zero_polygon(geo_resolve):
    best = {2: _rec(2, "D1", "District", country="Palestine")}
    chain = geo_resolve.build_admin_chain(best, {})
    assert chain["country"] == {"pcode": None, "name_en": "Palestine", "name_ar": None}
    assert chain["district"]["pcode"] == "D1"  # containment still fills its own level


def test_no_containment_no_fallback_yields_empty_chain(geo_resolve):
    assert geo_resolve.build_admin_chain({}, {}) == {}


def test_parent_cycle_terminates(geo_resolve):
    a = _rec(2, "A", "District A", parent_pcode="B")
    b = _rec(1, "B", "Gov B", parent_pcode="A")
    chain = geo_resolve.build_admin_chain({2: a}, {"A": a, "B": b})
    assert "district" in chain
    assert "governorate" in chain
    assert "country" not in chain  # nothing contains the point and no fallback source


def test_pick_nearest_record_prefers_parent_match_then_distance(geo_resolve):
    # ~11 m north (wrong parent) vs ~167 m north (right parent); a third
    # row sits 11 km away, outside any sane radius.
    rows = [
        {"name": "A", "latitude": 31.5501, "longitude": 34.4700,
         "parent_ref": "OTHER"},
        {"name": "B", "latitude": 31.5515, "longitude": 34.4700,
         "parent_ref": "NGZ"},
        {"name": "C", "latitude": 31.6500, "longitude": 34.4700,
         "parent_ref": "NGZ"},
    ]
    hinted = geo_resolve._pick_nearest_record(rows, 31.55, 34.47, 5000,
                                              parent_hint="NGZ")
    assert hinted["name"] == "B"          # parent match beats raw proximity
    plain = geo_resolve._pick_nearest_record(rows, 31.55, 34.47, 5000)
    assert plain["name"] == "A"           # no hint → nearest wins
    assert plain["distance_m"] < 20
    # Out-of-radius rows are excluded entirely.
    far = geo_resolve._pick_nearest_record([rows[2]], 31.55, 34.47, 5000)
    assert far is None


def test_pick_nearest_record_skips_bad_coordinates(geo_resolve):
    rows = [
        {"name": "X", "latitude": None, "longitude": None},
        {"name": "Y", "latitude": "not-a-number", "longitude": 34.47},
    ]
    assert geo_resolve._pick_nearest_record(rows, 31.55, 34.47, 5000) is None


def test_chain_gap_fills_are_wired_into_resolve(geo_resolve):
    from pathlib import Path

    src = Path("siraj_research/api/geo_resolve.py").read_text()
    assert '_fill_chain_gaps(lat, lon, result["admin_chain"], result, cfg)' in src
    assert '"record_fallback"' in src
    assert '"hierarchy_child"' in src
    assert '"gazetteer_nearest"' in src
