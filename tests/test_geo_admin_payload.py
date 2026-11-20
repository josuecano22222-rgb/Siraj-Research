"""Pure tests for the Geographic Administration canonical contract."""

from siraj_research.geo_admin import (
    canonical_code,
    canonical_payload,
    chain_values,
    deepest_level,
)


def test_chain_values_accepts_dicts_and_objects():
    class Doc:
        country = "IQ"
        governorate = "IQ-BG"
        district = None
        municipality = None
        village = None
        community = None

    values = chain_values(Doc())
    assert values["country"] == "IQ"
    assert values["district"] is None
    assert deepest_level(values) == 1


def test_deepest_level_counts_only_populated_links():
    assert deepest_level({"country": "IQ"}) == 0
    assert deepest_level({"country": "IQ", "governorate": "G", "village": "V"}) == 4
    assert deepest_level({}) == -1


def test_canonical_code_is_deterministic_and_url_safe():
    chain = {"country": "IQ", "governorate": "IQ-BG", "district": "IQ-BG-KAR"}
    assert canonical_code(chain) == "GA:IQ/IQ-BG/IQ-BG-KAR"
    assert canonical_code(chain) == canonical_code(dict(chain))
    hostile = {"country": "IQ", "governorate": "bad value / with spaces",
               "district": "x" * 400}
    code = canonical_code(hostile)
    assert len(code) <= 140
    assert " " not in code


def test_canonical_payload_exposes_the_spec_field_contract():
    labels = {
        "country": {"en": "Iraq", "ar": "العراق"},
        "governorate": {"en": "Baghdad", "ar": "بغداد"},
        "district": {"en": "Karkh", "ar": "الكرخ"},
        "district_self": {"en": "Karkh", "ar": "الكرخ"},
    }
    payload = canonical_payload(
        {"country": "IQ", "governorate": "IQ-BG", "district": "IQ-BG-KAR"},
        labels=labels,
        source="gadm",
        is_active=True,
    )
    assert payload["name_en"] == "Karkh"
    assert payload["name_local"] == "الكرخ"
    assert payload["hierarchy_level"] == 2
    assert payload["level_key"] == "district"
    assert payload["ancestry_path"] == "IQ/IQ-BG/IQ-BG-KAR"
    assert payload["ancestry_labels"] == "Iraq › Baghdad › Karkh"
    assert payload["source"] == "gadm"
    assert payload["is_active"] == 1
    assert payload["code"].startswith("GA:")


def test_canonical_payload_without_labels_falls_back_to_keys():
    payload = canonical_payload({"country": "IQ", "governorate": "IQ-BG"})
    assert payload["ancestry_path"] == "IQ/IQ-BG"
    assert payload["ancestry_labels"] == "IQ › IQ-BG"
    assert payload["name_en"] == "IQ-BG"
