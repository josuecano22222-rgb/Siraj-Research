"""Pure regression tests for Country → Community parent/child cascading."""
from siraj_research.geo_cascade import (
    ancestor_filters,
    cascade,
    chain_from_filters,
    chain_from_record,
    merge_chain,
    option_from_row,
    visible_chain,
)


def test_ancestor_filters_follow_the_six_level_chain():
    assert ancestor_filters("country", {"country": "IL"}) == {}
    assert ancestor_filters("governorate", {"country": "IL"}) == {"country": "IL"}
    assert ancestor_filters("community", {
        "country": "IL", "governorate": "G1", "district": "D1",
        "municipality": "M1", "village": "V1", "community": "Q1",
    }) == {
        "country": "IL", "governorate": "G1", "district": "D1",
        "municipality": "M1", "village": "V1",
    }


def test_option_from_row_uses_link_target_not_raw_label():
    row = option_from_row("community", {
        "name": "Com A", "label_en": "Community A", "label_ar": "مجتمع أ",
        "code": "Q1", "pcode": "Q1",
    })
    assert row["value"] == "Com A"       # safe Link target
    assert row["label"] == "Community A"
    assert row["label_ar"] == "مجتمع أ"
    assert row["doctype"] == "Community"
    country = option_from_row("country", {"name": "IL", "country_name": "Israel"})
    assert country["label"] == "Israel"


def test_chain_from_record_backfills_every_higher_level():
    record = {
        "name": "Com A", "country": "IL", "governorate": "Gov A",
        "district": "Dist A", "municipality": "Mun A", "village": "Vil A",
        "pcode": "Q1", "parent_pcode": "V1",
    }
    chain = chain_from_record("community", "Com A", record)
    assert chain["community"]["value"] == "Com A"
    assert chain["village"]["value"] == "Vil A"
    assert chain["municipality"]["value"] == "Mun A"
    assert chain["district"]["value"] == "Dist A"
    assert chain["governorate"]["value"] == "Gov A"
    assert chain["country"]["value"] == "IL"
    assert [row["field"] for row in visible_chain(chain)] == [
        "country", "governorate", "district", "municipality", "village", "community",
    ]


def test_missing_ancestors_stay_gaps_and_do_not_get_invented():
    chain = chain_from_record("district", "Dist A", {"name": "Dist A", "country": ""})
    assert chain["country"]["value"] == ""
    assert chain["governorate"]["value"] == ""
    assert [row["field"] for row in visible_chain(chain)] == ["district"]


def test_merge_and_filters_chains_prefer_specific_values():
    broad = chain_from_filters({"country": "IL"})
    specific = chain_from_record("village", "Vil A", {
        "name": "Vil A", "country": "PS", "governorate": "Gov B",
        "district": "Dist B", "municipality": "Mun B",
    })
    merged = merge_chain(broad, specific)
    assert merged["country"]["value"] == "PS"  # selected record wins
    assert merged["village"]["value"] == "Vil A"


def test_cascade_rejects_unknown_field_and_returns_shape_without_frappe():
    result = cascade("not_a_level", "x")
    assert result["error"].startswith("Unknown hierarchy field")
    result = cascade("governorate", None, country="IL")
    assert result["field"] == "governorate"
    assert result["filters"] == {"country": "IL"}
    assert result["source"] == "local-bench"
    assert result["options"] == []  # pure process has no local bench rows
