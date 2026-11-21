"""Pure-Python checks for OSM admin_level -> SIRAJ hierarchy level (no bench)."""

import sys
import types

import pytest


@pytest.fixture()
def geo_import(monkeypatch):
    # geo_import imports frappe unconditionally at module level, and its
    # helpers lazily import geo_hierarchy, which decorates whitelisted
    # endpoints at import time.
    stub = types.ModuleType("frappe")
    stub.whitelist = lambda *a, **k: (lambda fn: fn)
    monkeypatch.setitem(sys.modules, "frappe", stub)
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


def test_country_evidence_flows_from_trusted_neighbours(geo_import):
    rows = [
        # Trusted GeoNames district (real name, has country).
        {"key": ("District", "NGZ"), "scoped": False,
         "country": "Palestinian Territory, Occupied", "neighbor_keys": []},
        # Scoped hash rows: municipality is adjacent to the district,
        # governorate is adjacent only via the municipality.
        {"key": ("Municipality", "OSM-AAA"), "scoped": True, "country": "United States",
         "neighbor_keys": [("District", "NGZ"), ("Governorate", "OSM-BBB")]},
        {"key": ("Governorate", "OSM-BBB"), "scoped": True, "country": "United States",
         "neighbor_keys": [("Municipality", "OSM-AAA")]},
        # Scoped row with no evidence anywhere: must not be touched.
        {"key": ("Village", "OSM-CCC"), "scoped": True, "country": "United States",
         "neighbor_keys": []},
    ]
    derived = geo_import._propagate_country_evidence(rows)
    assert derived[("Municipality", "OSM-AAA")] == "Palestinian Territory, Occupied"
    # Second hop: governorate learns after the municipality becomes trusted.
    assert derived[("Governorate", "OSM-BBB")] == "Palestinian Territory, Occupied"
    assert ("Village", "OSM-CCC") not in derived


def test_country_evidence_never_trusts_scoped_or_empty_rows(geo_import):
    rows = [
        {"key": ("District", "OSM-1"), "scoped": True,
         "country": "United States", "neighbor_keys": [("Governorate", "OSM-2")]},
        {"key": ("Governorate", "OSM-2"), "scoped": True,
         "country": "United States", "neighbor_keys": [("District", "OSM-1")]},
        # Trusted but empty: no evidence to give.
        {"key": ("District", "Real"), "scoped": False,
         "country": None, "neighbor_keys": [("Municipality", "OSM-3")]},
        {"key": ("Municipality", "OSM-3"), "scoped": True,
         "country": None, "neighbor_keys": [("District", "Real")]},
    ]
    assert geo_import._propagate_country_evidence(rows) == {}


def test_country_evidence_respects_round_limit(geo_import):
    # Chain: NGZ -> OSM-0 -> OSM-1 -> OSM-2 -> OSM-3, listed from the far
    # end so that a single round can only reach OSM-0 (its row, at the
    # end of the list, sees the trusted NGZ after the others have already
    # been visited with untrusted neighbours).
    chain = [("District", "NGZ")]
    for i in range(4):
        chain.append(("Municipality", f"OSM-{i}"))
    rows = [{"key": key, "scoped": key != ("District", "NGZ"),
             "country": "Israel" if key == ("District", "NGZ") else None,
             "neighbor_keys": [chain[index - 1]] if index else []}
            for index, key in reversed(list(enumerate(chain)))]
    derived = geo_import._propagate_country_evidence(rows, rounds=1)
    assert set(derived) == {("Municipality", "OSM-0")}
    assert derived[("Municipality", "OSM-0")] == "Israel"
    # With enough rounds the whole chain learns.
    derived = geo_import._propagate_country_evidence(rows, rounds=4)
    assert set(derived) == {k for k in chain if k != ("District", "NGZ")}


def test_partition_country_fills_two_country_remainder(geo_import):
    by_code = {"IL": "Israel", "PS": "Palestinian Territory, Occupied"}
    # Only Israel established spatially → the rest of OSM-IL-PS is PS.
    assert (geo_import._partition_country_for_remainder("OSM-IL-PS", by_code, {"Israel"})
            == "Palestinian Territory, Occupied")
    # Only PS established → remainder is Israel.
    assert (geo_import._partition_country_for_remainder(
        "OSM-IL-PS", by_code, {"Palestinian Territory, Occupied"}) == "Israel")


def test_partition_country_never_guesses_ambiguous_datasets(geo_import):
    by_code = {"IL": "Israel", "PS": "Palestinian Territory, Occupied", "IQ": "Iraq"}
    # Both declared countries present: remainder has no answer.
    assert geo_import._partition_country_for_remainder(
        "OSM-IL-PS", by_code, {"Israel", "Palestinian Territory, Occupied"}) is None
    # No country established yet: containment must go first.
    assert geo_import._partition_country_for_remainder("OSM-IL-PS", by_code, set()) is None
    # Single-country datasets are handled by containment, not partition.
    assert geo_import._partition_country_for_remainder(
        "OSM-IQ", by_code, {"Iraq"}) is None
    # Unknown tokens (not in by_code) leave fewer than two candidates.
    assert geo_import._partition_country_for_remainder(
        "OSM-XX-YY", by_code, set()) is None


def test_authoritative_evidence_outranks_and_spreads(geo_import):
    rows = [
        {"key": ("District", "NGZ"), "scoped": True,
         "country": "United States", "neighbor_keys": [("Governorate", "OSM-H1")]},
        {"key": ("Governorate", "OSM-H1"), "scoped": True,
         "country": "United States", "neighbor_keys": [("District", "NGZ")]},
        {"key": ("Municipality", "OSM-M1"), "scoped": True,
         "country": None, "neighbor_keys": [("District", "NGZ")]},
    ]
    authoritative = {("District", "NGZ"): "Palestinian Territory, Occupied"}
    derived = geo_import._propagate_country_evidence(rows, authoritative=authoritative)
    # The twin value is written even though the row is scoped...
    assert derived[("District", "NGZ")] == "Palestinian Territory, Occupied"
    # ...and from there the evidence reaches its neighbours.
    assert derived[("Governorate", "OSM-H1")] == "Palestinian Territory, Occupied"
    assert derived[("Municipality", "OSM-M1")] == "Palestinian Territory, Occupied"


def test_authoritative_values_must_differ_to_be_written(geo_import):
    rows = [{"key": ("District", "X"), "scoped": True,
             "country": "Israel", "neighbor_keys": []}]
    assert geo_import._propagate_country_evidence(
        rows, authoritative={("District", "X"): "Israel"}) == {}
