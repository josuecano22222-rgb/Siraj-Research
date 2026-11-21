# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
"""Pure-core tests for the advanced map search (no site required).

Precision is the contract: decimal input must survive verbatim, DMS must
convert through exact fractions, and name folding must match the client's
Arabic normalisation rule-for-rule.
"""

from decimal import Decimal

from siraj_research.utils.map_search import (
	LEVEL_LABELS,
	coordinate_looks_like,
	normalise_name,
	parse_coordinate_query,
	parse_levels,
	parse_types,
	rank_candidates,
	score_name,
	score_pcode,
)

PAIR = "31.5900000000000001, 34.47"


class TestDecimalPairs:
	def test_decimal_pair_is_verbatim_exact(self):
		result = parse_coordinate_query(PAIR)
		assert result["format"] == "decimal"
		# The researcher's digits survive — no float round-trip.
		assert result["lat"] == "31.5900000000000001"
		assert result["lon"] == "34.47"
		assert result["assumed_order"] == "lat,lon"

	def test_trailing_zeros_kept(self):
		result = parse_coordinate_query("31.50, 34.470")
		assert result["lat"] == "31.50"
		assert result["lon"] == "34.470"

	def test_arabic_digits_and_separator(self):
		result = parse_coordinate_query("٣١٫٥, ٣٤٫٤٧")
		assert result["lat"] == "31.5"
		assert result["lon"] == "34.47"

	def test_space_and_semicolon_separators(self):
		assert parse_coordinate_query("31.5 34.47")["lon"] == "34.47"
		assert parse_coordinate_query("31.5; 34.47")["lat"] == "31.5"

	def test_hemisphere_suffixes_apply_sign(self):
		result = parse_coordinate_query("31.5N, 34.4W")
		assert result["lat"] == "31.5"
		assert result["lon"] == "-34.4"
		south = parse_coordinate_query("31.5S 34.4E")
		assert south["lat"] == "-31.5"
		assert south["lon"] == "34.4"

	def test_conflicting_hemisphere_and_sign(self):
		result = parse_coordinate_query("-31.5N, 34.4E")
		assert result["error"] == "conflicting_hemisphere"
		assert result["suggestion"] is None

	def test_out_of_range_offers_lon_lat_suggestion(self):
		result = parse_coordinate_query("100.2, 34.47")
		assert result["error"] == "out_of_range"
		suggestion = result["suggestion"]
		assert suggestion["lat"] == "34.47"
		assert suggestion["lon"] == "100.2"
		assert suggestion["assumed_order"] == "lon,lat"

	def test_both_out_of_range_has_no_suggestion(self):
		result = parse_coordinate_query("95, 200")
		assert result["error"] == "out_of_range"
		assert result["suggestion"] is None

	def test_non_coordinate_text_is_not_coordinates(self):
		assert parse_coordinate_query("غزة") is None
		assert parse_coordinate_query("31") is None  # single value: ambiguous
		assert parse_coordinate_query("") is None
		assert parse_coordinate_query(None) is None

	def test_looks_like_helper(self):
		assert coordinate_looks_like("31.5, 34.47")
		assert coordinate_looks_like("31°35'24\"N 34°28'11\"E")
		assert not coordinate_looks_like("Gaza district")


class TestDms:
	def test_dms_exact_fraction_and_decimal(self):
		result = parse_coordinate_query('31°35\'24.5"N 34°28\'11.92"E')
		assert result["format"] == "dms"
		# 31 + 35/60 + 24.5/3600 = 227449/7200 exactly.
		assert result["lat_fraction"] == "227449/7200"
		assert abs(Decimal(result["lat"]) - Decimal(227449) / Decimal(7200)) < Decimal("1e-25")
		# 34 + 28/60 + 11.92/3600 = 34 + 7/15 + 745/22500 … verify by value.
		assert abs(Decimal(result["lon"]) - (Decimal(34) + Decimal(28) / 60 + Decimal("11.92") / 3600)) < Decimal("1e-25")

	def test_dms_without_seconds_and_with_letters(self):
		result = parse_coordinate_query("31d35mN 34d28mE")
		assert result["format"] == "dms"
		assert Decimal(result["lat"]) == Decimal(31) + Decimal(35) / 60

	def test_dms_arabic_digits_and_hemisphere_letters(self):
		result = parse_coordinate_query('٣١°٣٥\'٢٤٫٥"ش ٣٤°٢٨\'١١٫٩٢"ق')
		assert result["format"] == "dms"
		assert result["lat_fraction"] == "227449/7200"

	def test_dms_west_and_south_negative(self):
		result = parse_coordinate_query('34°0\'0"S 31°30\'0"W')
		assert Decimal(result["lat"]) == Decimal(-34)
		assert Decimal(result["lon"]) == Decimal(-(31 + Decimal(30) / 60))

	def test_dms_minutes_out_of_range(self):
		result = parse_coordinate_query('31°65\'0"N 34°0\'0"E')
		assert result["error"] == "dms_out_of_range"

	def test_dms_latitude_over_90(self):
		result = parse_coordinate_query('95°0\'0"N 34°0\'0"E')
		assert result["error"] == "out_of_range"

	def test_dms_sign_conflict(self):
		result = parse_coordinate_query('-31°30\'0"N 34°0\'0"E')
		assert result["error"] == "dms_sign_conflict"


class TestNormalisation:
	def test_alef_variants(self):
		assert normalise_name("أحمد") == normalise_name("احمد") == "احمد"
		assert normalise_name("إطلاق") == normalise_name("اطلاق") == "اطلاق"

	def test_ta_marbuta_and_ya(self):
		assert normalise_name("غزة") == "غزه"
		assert normalise_name("موسى") == "موسي"

	def test_diacritics_and_case(self):
		assert normalise_name("مَرْحَبًا") == normalise_name("مرحبا")
		assert normalise_name("Gaza Strip") == "gaza strip"

	def test_none_and_spaces(self):
		assert normalise_name(None) == ""
		assert normalise_name("  Gaza   City ") == "gaza city"


class TestRanking:
	def test_pcode_beats_exact_name(self):
		rows = [
			{"name_en": "Gaza", "pcode": "PS-GZ"},
			{"name_en": "Other", "pcode": "gaza"},
		]
		ranked = rank_candidates("gaza", rows, ("name_en",), ("pcode",))
		assert ranked[0]["pcode"] == "gaza"  # exact pcode match, score 1000

	def test_exact_beats_prefix_beats_word_beats_contains(self):
		rows = [
			{"name_en": "Magaza"},          # mid-word contains (400)
			{"name_en": "Northern Gaza"},   # word start (600)
			{"name_en": "Gaza Strip"},      # prefix (700)
			{"name_en": "Gaza"},            # exact (900)
		]
		ranked = rank_candidates("gaza", rows, ("name_en",))
		assert [r["name_en"] for r in ranked] == [
			"Gaza", "Gaza Strip", "Northern Gaza", "Magaza",
		]

	def test_word_start_beats_midword(self):
		rows = [{"name_en": "New Gaza"}, {"name_en": "Magaza"}]
		ranked = rank_candidates("gaza", rows, ("name_en",))
		assert [r["name_en"] for r in ranked] == ["New Gaza", "Magaza"]

	def test_tie_break_uses_level_ascending(self):
		rows = [
			{"name_en": "Gaza", "level": 2},
			{"name_en": "Gaza", "level": 1},
		]
		ranked = rank_candidates(
			"gaza", rows, ("name_en",), tie_break=lambda r: r.get("level", 99),
		)
		assert [r["level"] for r in ranked] == [1, 2]

	def test_unmatched_rows_dropped(self):
		ranked = rank_candidates("خانيونس", [{"name_en": "Gaza"}], ("name_en",))
		assert ranked == []

	def test_arabic_query_matches_folded_store(self):
		rows = [{"name_ar": "غزة"}]
		ranked = rank_candidates("غزه", rows, ("name_ar",))
		assert len(ranked) == 1

	def test_score_helpers(self):
		assert score_name("gaza", "Gaza City") == 700  # prefix
		assert score_pcode("ps-gz", "PS-GZ") == 1000
		assert score_pcode("", None) == 0


class TestScopeHelpers:
	def test_parse_levels(self):
		assert parse_levels("1,2,9") == [1, 2]
		assert parse_levels([5, "3", 3]) == [3, 5]
		assert parse_levels(None) == []
		assert parse_levels("junk") == []

	def test_parse_levels_all_six_exist(self):
		assert sorted(LEVEL_LABELS) == [0, 1, 2, 3, 4, 5]

	def test_parse_types_restricts_to_allowed(self):
		allowed = ("Person", "Place")
		assert parse_types("Person,Source", allowed) == ["Person"]
		assert parse_types(["Place", "Place"], allowed) == ["Place"]
		assert parse_types("", allowed) == []
