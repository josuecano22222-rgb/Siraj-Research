"""Pure tests for ancestry denormalisation and ancestor reconciliation."""

from siraj_research.geo_levels import default_rows, effective_levels
from siraj_research.geo_lineage import (
    ancestor_chain,
    build_ancestry,
    level_of_doctype,
    own_field,
    reconcile_plan,
)


def test_level_mapping_covers_the_five_editable_levels_only():
    assert level_of_doctype("Governorate") == 1
    assert level_of_doctype("Community") == 5
    assert level_of_doctype("Country") is None
    assert level_of_doctype("Place") is None
    assert own_field("Village") == "village"


def test_ancestry_path_and_labels_use_set_segments_only():
    values = {
        "country": "IQ",
        "governorate": "IQ-BG",
        "district": "IQ-BG-KAR",
        "municipality": None,
        "village": None,
        "community": None,
    }
    labels = {
        "country": {"en": "Iraq", "ar": "العراق"},
        "governorate": {"en": "Baghdad", "ar": "بغداد"},
        "district": {"en": "Karkh", "ar": "الكرخ"},
        "district_self": {"en": "Karkh", "ar": "الكرخ"},
    }
    ancestry = build_ancestry("District", values, labels=labels)
    assert ancestry["path"] == "IQ/IQ-BG/IQ-BG-KAR"
    assert ancestry["labels"] == "Iraq › Baghdad › Karkh"
    assert ancestry["level"] == 2
    assert [segment["field"] for segment in ancestry["segments"]] == [
        "country", "governorate", "district",
    ]


def test_skipped_level_leaves_no_empty_path_segment():
    values = {
        "country": "LB",
        "governorate": "LB-BA",
        "district": "LB-BA-BA",
        "municipality": None,
        "village": "LB-BA-BA-V1",
    }
    levels = effective_levels(
        [dict(row, is_active=0) if row["level"] == 3 else row for row in default_rows()]
    )
    ancestry = build_ancestry("Village", values, levels)
    assert ancestry["path"] == "LB/LB-BA/LB-BA-BA/LB-BA-BA-V1"
    assert "//" not in ancestry["path"]
    assert ancestry["level"] == 4


def test_stale_inactive_field_is_reported_without_breaking_the_path():
    values = {"country": "LB", "governorate": "LB-BA", "district": None,
              "municipality": "LB-BA-M1"}
    levels = effective_levels(
        [dict(row, is_active=0) if row["level"] == 3 else row for row in default_rows()]
    )
    ancestry = build_ancestry("Municipality", values, levels)
    assert "municipality" in ancestry["stale"]


def test_ancestor_chain_is_country_first_and_skips_empty_levels():
    values = {"country": "IQ", "governorate": "IQ-BG", "district": None,
              "municipality": "IQ-BG-RU-RU"}
    chain = ancestor_chain(4, values)
    assert [row[1] for row in chain] == ["country", "governorate", "municipality"]
    assert chain[-1][2] == "IQ-BG-RU-RU"


def test_reconcile_plan_clears_only_deeper_ancestors():
    levels = effective_levels()
    values = {
        "country": "IQ",
        "governorate": "IQ-BG",
        "district": "IQ-BG-KAR",
        "municipality": "IQ-BG-KAR-M",
    }
    plan = reconcile_plan(4, values, {"governorate"}, levels)
    assert plan["anchor"] == "governorate"
    assert plan["clear"] == ["district", "municipality"]
    no_change = reconcile_plan(4, values, set(), levels)
    assert no_change["clear"] == []
    assert no_change["reason"] == "no_ancestor_change"


def test_unknown_doctype_returns_empty_ancestry():
    ancestry = build_ancestry("Place", {"country": "IQ"})
    assert ancestry == {"path": "", "labels": "", "level": None, "segments": [], "stale": []}
