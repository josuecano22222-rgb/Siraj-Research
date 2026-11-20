"""Pure tests for per-country level configuration (no bench required)."""

from siraj_research.geo_levels import (
    DEFAULT_LEVELS,
    ancestor_filters,
    clear_descendants,
    config_payload,
    default_rows,
    effective_levels,
    label_for,
    level_of,
    level_spec,
    normalise_rows,
    validate_chain,
    validate_config_rows,
)


def _levels(overrides):
    rows = default_rows()
    for row in rows:
        if row["level"] in overrides:
            row.update(overrides[row["level"]])
    return effective_levels(rows)


def test_catalogue_is_the_documented_six_level_contract():
    assert [spec["level"] for spec in DEFAULT_LEVELS] == [0, 1, 2, 3, 4, 5]
    assert [spec["field"] for spec in DEFAULT_LEVELS] == [
        "country", "governorate", "district", "municipality", "village", "community",
    ]
    assert level_of("municipality") == 3
    assert level_spec("Community")["doctype"] == "Community"
    assert level_spec("nope") is None


def test_defaults_are_all_active_and_parent_chain_is_catalogue_order():
    levels = effective_levels()
    assert all(level["is_active"] for level in levels)
    by_field = {level["field"]: level for level in levels}
    assert by_field["village"]["parent_field"] == "municipality"
    assert by_field["community"]["ancestor_fields"] == [
        "country", "governorate", "district", "municipality", "village",
    ]
    payload = config_payload(levels, country="IQ")
    assert payload["depth"] == 5
    assert payload["active_fields"] == [
        "country", "governorate", "district", "municipality", "village", "community",
    ]


def test_skipped_municipality_moves_village_parent_to_district():
    levels = _levels({3: {"is_active": 0, "skip_reason": "no municipality tier"}})
    by_field = {level["field"]: level for level in levels}
    assert by_field["municipality"]["is_active"] is False
    assert by_field["municipality"]["parent_field"] is None
    assert by_field["village"]["parent_field"] == "district"
    assert by_field["village"]["ancestor_fields"] == ["country", "governorate", "district"]
    assert by_field["community"]["parent_field"] == "village"


def test_hierarchy_depth_truncates_without_changing_labels_or_order():
    levels = effective_levels(default_rows(), depth=2)
    active = [level["field"] for level in levels if level["is_active"]]
    assert active == ["country", "governorate", "district"]
    labels = {level["field"]: level["label_en"] for level in levels}
    assert labels["municipality"] == "Municipality"
    assert label_for(levels, "district", "ar") == "المنطقة"


def test_label_override_and_arabic_fallback():
    levels = _levels({1: {"label_en": "Region", "label_ar": "المنطقة"}})
    assert label_for(levels, "governorate") == "Region"
    assert label_for(levels, "governorate", "ar") == "المنطقة"
    payload = config_payload(levels, country="SA")
    assert payload["labels_en"]["governorate"] == "Region"
    assert payload["labels_ar"]["governorate"] == "المنطقة"


def test_ancestor_filters_skip_inactive_levels():
    levels = _levels({3: {"is_active": 0}})
    values = {
        "country": "LB",
        "governorate": "LB-BA",
        "district": "LB-BA-BA",
        "municipality": None,
        "village": "LB-BA-BA-V1",
    }
    assert ancestor_filters("village", values, levels) == {
        "country": "LB",
        "governorate": "LB-BA",
        "district": "LB-BA-BA",
    }
    # An inactive ancestor value is ignored even if a legacy row carries it.
    values["municipality"] = "stale-municipality"
    assert "municipality" not in ancestor_filters("village", values, levels)


def test_clear_descendants_only_returns_active_deeper_fields():
    levels = _levels({3: {"is_active": 0}})
    assert clear_descendants("district", levels) == ["village", "community"]
    assert clear_descendants("country", levels) == ["governorate", "district", "village", "community"]
    assert clear_descendants("community", levels) == []


def test_validate_chain_accepts_skipped_level_chains():
    levels = _levels({3: {"is_active": 0}})
    values = {
        "country": "LB",
        "governorate": "LB-BA",
        "district": "LB-BA-BA",
        "municipality": None,
        "village": "LB-BA-BA-V1",
    }
    assert validate_chain(levels, values, own_field="village") == []


def test_validate_chain_rejects_values_at_inactive_levels():
    levels = _levels({3: {"is_active": 0}})
    values = {
        "country": "LB",
        "governorate": "LB-BA",
        "district": "LB-BA-BA",
        "municipality": "LB-BA-BA-M1",
    }
    errors = validate_chain(levels, values, own_field="municipality")
    codes = {error["code"] for error in errors}
    assert "inactive_level_populated" in codes
    assert "inactive_own_level" in codes


def test_validate_chain_rejects_a_hole_but_allows_incomplete_chains():
    levels = effective_levels()
    # Village with a District but no Municipality: Municipality is active, so
    # the chain has a hole.
    hole = {"country": "IQ", "governorate": "IQ-BG", "district": "IQ-BG-KAR",
            "village": "IQ-BG-KAR-V1"}
    codes = {error["code"] for error in validate_chain(levels, hole, own_field="village")}
    assert "missing_active_ancestor" in codes
    # Bulk importers / boundary synchronisation may record the same row and let
    # the audit report the gap.
    assert validate_chain(levels, hole, own_field="village", allow_partial=True) == []
    # Only a country is known: incomplete, but not inconsistent.
    assert validate_chain(levels, {"country": "IQ"}, own_field="village") == []
    # With Municipality skipped, the same chain is complete.
    skipped = _levels({3: {"is_active": 0}})
    assert validate_chain(skipped, hole, own_field="village") == []


def test_validate_config_rows_reports_structural_problems():
    rows = default_rows()
    rows[2]["level"] = 1  # duplicate
    rows[1]["label_en"] = ""
    problems = validate_config_rows(rows)
    reasons = {problem["reason"] for problem in problems}
    assert "duplicate_level" in reasons
    assert "missing_label_en" in reasons


def test_normalise_rows_accepts_missing_and_invalid_input():
    rows = normalise_rows(
        [
            {"level": "1", "label_en": "Region", "is_active": "0"},
            {"level_key": "district", "label_en": "Area"},
            {"level": 99},
            "not a row",
        ]
    )
    assert rows[1]["label_en"] == "Region"
    assert rows[1]["is_active"] == 0
    assert rows[2]["label_en"] == "Area"
    assert 99 not in rows
