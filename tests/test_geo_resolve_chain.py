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
    class _PermissionError(Exception):
        pass

    class _ValidationError(Exception):
        pass

    stub = types.ModuleType("frappe")
    stub.PermissionError = _PermissionError
    stub.ValidationError = _ValidationError
    stub.whitelist = lambda *a, **k: (lambda fn: fn)
    stub.has_permission = lambda doctype, ptype="read": True

    def _throw(msg, exc=_ValidationError):
        raise exc(msg)

    stub.throw = _throw
    monkeypatch.setitem(sys.modules, "frappe", stub)
    import importlib

    from siraj_research.api import geo_resolve as mod

    importlib.reload(mod)
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


def test_sweep_points_compacts_six_fields_and_sources(geo_resolve, monkeypatch):
    monkeypatch.setattr(geo_resolve, "_resolve_one", lambda lat, lon: {
        "on_land": True,
        "admin_chain": {
            "country": {"name_en": "Palestinian Territory, Occupied"},
            "village": {"name_en": "الرمال", "source": "gazetteer_nearest"},
        },
        "provenance": ["polygon_containment", "gazetteer_nearest"],
        "nearest_place": {"name_en": "الرمال"},
    })
    rows = geo_resolve.sweep_points([["Jabalia", 31.55, 34.47]])
    row = rows[0]
    assert row["point"] == "Jabalia"
    assert row["country"] == "Palestinian Territory, Occupied"
    assert row["country_src"] == "polygon_containment"
    assert row["municipality"] is None          # coverage hole stays visible
    assert row["municipality_src"] is None
    assert row["village"] == "الرمال"
    assert row["village_src"] == "gazetteer_nearest"
    assert row["nearest_place"] == "الرمال"
    assert "gazetteer_nearest" in row["provenance"]


def test_hierarchy_record_queries_use_real_doctype_columns():
    """Regression (MySQL 1054): hierarchy DocTypes expose label_en/label_ar
    — name_en/name_ar live on Admin Boundary/Gazetteer Place only. Every
    hierarchy SELECT/field list in the gap-fill must use the real names."""
    import glob
    import json
    from pathlib import Path

    src = Path("siraj_research/api/geo_resolve.py").read_text()
    assert "label_en AS name_en" in src
    assert 'fields=["name", "label_en", "label_ar", "pcode"]' in src
    for dt in ("municipality", "village", "community"):
        path = glob.glob(f"siraj_research/**/doctype/{dt}/{dt}.json",
                         recursive=True)[0]
        names = {f["fieldname"] for f in json.load(open(path))["fields"]}
        assert "label_en" in names and "label_ar" in names
        assert "name_en" not in names and "name_ar" not in names


def test_settlement_fallback_labels_community_from_resolved_village(geo_resolve, monkeypatch):
    """Community must never be null once a village is known: the
    settlement itself fills the field, clearly labelled low-confidence
    with its own source (never disguised as neighborhood evidence)."""
    monkeypatch.setattr(geo_resolve, "_nearest_hierarchy_record",
                        lambda *a, **k: None)
    chain = {"village": {"pcode": "GEO-123", "name_en": "Rafaḥ",
                         "name_ar": "رفح"}}
    tags = geo_resolve._fill_chain_gaps(31.29, 34.25, chain, {"nearest_place": None},
                                        {"reverse_max_m": 5000})
    community = chain["community"]
    assert community["name_en"] == "Rafaḥ"
    assert community["source"] == "settlement_fallback"
    assert community["confidence"] == "low"
    assert community["pcode"] is None        # derived code, no Village collision
    assert "settlement_fallback" in tags


def test_nearest_record_community_wins_over_settlement_fallback(geo_resolve, monkeypatch):
    monkeypatch.setattr(
        geo_resolve, "_nearest_hierarchy_record",
        lambda lat, lon, doctype, max_m, parent_hint=None: (
            {"name": "C1", "name_en": "Al Nasser", "name_ar": None,
             "pcode": "PS-C1", "latitude": 31.0, "longitude": 34.0,
             "distance_m": 100.0} if doctype == "Community" else None))
    chain = {"village": {"pcode": "GEO-123", "name_en": "Rafaḥ", "name_ar": "رفح"}}
    geo_resolve._fill_chain_gaps(31.29, 34.25, chain, {"nearest_place": None},
                                 {"reverse_max_m": 5000})
    assert chain["community"]["name_en"] == "Al Nasser"
    assert chain["community"]["source"] == "nearest_record"


def test_sweep_points_enforces_place_read_permission(geo_resolve, monkeypatch):
    monkeypatch.setattr(geo_resolve.frappe, "has_permission", lambda dt, ptype="read": False)
    with pytest.raises(geo_resolve.frappe.PermissionError):
        geo_resolve.sweep_points([["Jabalia", 31.55, 34.47]])


def test_sweep_points_parses_json_string_and_caps_at_500(geo_resolve, monkeypatch):
    import json

    monkeypatch.setattr(geo_resolve, "_resolve_one", lambda lat, lon: {
        "on_land": True,
        "admin_chain": {"country": {"name_en": "Palestine"}},
        "provenance": ["polygon_containment"],
        "nearest_place": None,
    })

    # JSON string payload (as delivered by HTTP /api/method form/JSON calls)
    parsed_rows = geo_resolve.sweep_points(json.dumps([["Jabalia", 31.55, 34.47]]))
    assert len(parsed_rows) == 1
    assert parsed_rows[0]["point"] == "Jabalia"

    # Invalid JSON string rejected cleanly
    with pytest.raises(geo_resolve.frappe.ValidationError):
        geo_resolve.sweep_points("{not-json")

    # Non-list JSON payload rejected cleanly
    with pytest.raises(geo_resolve.frappe.ValidationError):
        geo_resolve.sweep_points(json.dumps({"points": []}))

    # Hard cap of 500 points enforced
    oversized = [[f"P-{idx}", 31.5, 34.45] for idx in range(525)]
    capped_rows = geo_resolve.sweep_points(oversized)
    assert len(capped_rows) == 500
    assert capped_rows[0]["point"] == "P-0"
    assert capped_rows[-1]["point"] == "P-499"


def test_sweep_points_rejects_malformed_items_h1(geo_resolve, monkeypatch):
    monkeypatch.setattr(geo_resolve, "_resolve_one", lambda lat, lon: {
        "on_land": True,
        "admin_chain": {},
        "provenance": [],
        "nearest_place": None,
    })
    for malformed in (
        [None],
        [123],
        [["only_name"]],
        [["x", "bad", 34.4]],
        [["x", 31.5, float("nan")]],
        [["x", float("inf"), 34.4]],
    ):
        with pytest.raises(geo_resolve.frappe.ValidationError):
            geo_resolve.sweep_points(malformed)
