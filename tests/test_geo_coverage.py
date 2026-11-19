"""Pure aggregation checks for hierarchy coverage reporting."""

from siraj_research.geo_coverage import summarise_counts


def test_summary_counts_each_level_and_finds_final_level_gaps():
    rows = {
        0: [{"name": "Iraq", "code": "IQ"}],
        1: [{"name": "IQ-BG", "country": "Iraq"}, {"name": "SY-DI", "country": "Syria"}],
        2: [{"name": "IQ-BG-C", "country": "Iraq"}],
        3: [{"name": "IQ-BG-C-M", "country": "Iraq"}],
        4: [{"name": "IQ-BG-C-M-V", "country": "Iraq"}],
        5: [],
    }
    summary = summarise_counts(rows)
    assert summary["totals"] == {"0": 1, "1": 2, "2": 1, "3": 1, "4": 1, "5": 0}
    assert summary["per_country"]["Iraq"]["4"] == 1
    assert "Syria" in summary["countries_without_village_or_community"]
    assert "Iraq" not in summary["countries_without_village_or_community"]
    assert summary["countries_with_full_chain"] == []


def test_full_chain_is_detected_when_all_six_levels_present():
    rows = {
        0: [{"name": "X", "code": "XX"}],
        1: [{"name": "X1", "country": "X"}],
        2: [{"name": "X2", "country": "X"}],
        3: [{"name": "X3", "country": "X"}],
        4: [{"name": "X4", "country": "X"}],
        5: [{"name": "X5", "country": "X"}],
    }
    assert summarise_counts(rows)["countries_with_full_chain"] == ["X"]
