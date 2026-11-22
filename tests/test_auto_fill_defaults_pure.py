"""Pure contracts for the coordinate auto-fill default override (Phase 4)."""
from siraj_research.geo_doc_events import defaulted_level_fields


def test_scalar_default_match_is_detected():
    assert defaulted_level_fields(
        {"country": "United States"}, {"country": "United States"}
    ) == ["country"]


def test_multi_value_default_match_is_detected():
    assert defaulted_level_fields(
        {"country": "Iraq"}, {"country": ["Iraq", "Kuwait"]}
    ) == ["country"]


def test_genuine_input_is_never_matched():
    # A value that differs from the live default is human input.
    assert defaulted_level_fields(
        {"country": "Iraq"}, {"country": "United States"}
    ) == []


def test_missing_default_never_matches():
    assert defaulted_level_fields({"country": "Iraq"}, {}) == []
    assert defaulted_level_fields({"country": "Iraq"}, {"governorate": "Baghdad"}) == []


def test_empty_values_are_skipped():
    assert defaulted_level_fields(
        {"country": "", "governorate": None, "district": []},
        {"country": "United States", "governorate": "x", "district": "y"},
    ) == []


def test_string_coercion_matches_across_types():
    # Frappe may hand back int/str variants of the same default.
    assert defaulted_level_fields({"code": 7}, {"code": "7"}) == ["code"]


def test_only_matching_fields_returned_in_input_order():
    values = {"country": "United States", "governorate": "Baghdad", "district": "US"}
    defaults = {"country": "United States", "district": "US"}
    assert defaulted_level_fields(values, defaults) == ["country", "district"]
