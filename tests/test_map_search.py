# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
"""Pure-core tests for the advanced map search (no site required).

Precision is the contract: decimal input must survive verbatim, DMS must
convert through exact fractions, and name folding must match the client's
Arabic normalisation rule-for-rule.
"""

from decimal import Decimal

from siraj_research.utils.map_search import (
	HIERARCHY_CHILD_DOCTYPE,
	HIERARCHY_PARENT_FIELD,
	LEVEL_LABELS,
	bboxes_intersect,
	coordinate_looks_like,
	haversine_m,
	lon_in_bbox,
	missing_chain_levels,
	normalise_name,
	parse_coordinate_query,
	parse_levels,
	parse_types,
	point_in_bbox,
	radial_bboxes,
	radial_lat_range,
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


class TestGeometryHelpers:
	def test_haversine_known_distance(self):
		# ~111.32 km per degree of latitude at the equator.
		metres = haversine_m(0, 0, 1, 0)
		assert 110000 < metres < 112000

	def test_haversine_zero_for_identical_points(self):
		assert haversine_m(31.5, 34.47, 31.5, 34.47) == 0.0

	def test_radial_bbox_normal_mid_latitude(self):
		boxes = radial_bboxes(31.5, 34.47, 5000)
		assert len(boxes) == 1
		min_lon, max_lon = boxes[0]
		assert min_lon < 34.47 < max_lon
		# ±5 km at lat 31.5 ≈ ±0.0525° of longitude → full width ≈ 0.105°.
		assert 0.10 < (max_lon - min_lon) < 0.11

	def test_radial_bbox_splits_at_antimeridian(self):
		boxes = radial_bboxes(0, 179, 200000)
		assert len(boxes) == 2
		assert boxes[0][1] == 180.0 and boxes[1][0] == -180.0
		assert boxes[0][0] > 170
		assert boxes[1][1] < -170

	def test_radial_bbox_pole_spans_all_longitudes(self):
		boxes = radial_bboxes(89.99999, 10, 5000)
		# Either the explicit pole branch or a wrap — must cover ±180.
		covered = any(b0 <= -180.0 and b1 >= 180.0 for b0, b1 in boxes)
		or_wrapped = len(boxes) == 2 and boxes[0][1] == 180.0 and boxes[1][0] == -180.0
		assert covered or or_wrapped

	def test_lat_range_clamped_to_poles(self):
		lo, hi = radial_lat_range(89.99, 100000)
		assert lo >= -90 and hi <= 90

	def test_lon_in_bbox_wrap(self):
		assert lon_in_bbox(-179, 170, -170) is True
		assert lon_in_bbox(0, 170, -170) is False
		assert lon_in_bbox(175, 170, -170) is True
		assert lon_in_bbox(50, -10, 10) is False

	def test_point_in_bbox(self):
		assert point_in_bbox(31.5, 34.47, (30, 34, 32, 35)) is True
		assert point_in_bbox(31.5, 40, (30, 34, 32, 35)) is False

	def test_missing_chain_levels_explicit(self):
		assert missing_chain_levels({}) == [
			"country", "governorate", "district", "municipality", "village", "community",
		]
		assert missing_chain_levels(
			{"country": {"pcode": "PS"}, "governorate": {"pcode": "PS-GZ"}}
		) == ["district", "municipality", "village", "community"]
		# An ocean point (empty chain) reports everything, no error.
		assert len(missing_chain_levels(None)) == 6

	def test_bboxes_intersect_orthogonal(self):
		a = (30, 34, 32, 35)
		assert bboxes_intersect(a, (31, 34.5, 33, 36)) is True
		assert bboxes_intersect(a, (33, 34, 34, 35)) is False

	def test_bboxes_intersect_antimeridian_wrapped(self):
		region = (0, 170, 10, -170)  # wraps the dateline
		assert bboxes_intersect(region, (2, 175, 4, 179)) is True
		assert bboxes_intersect(region, (2, -179, 4, -175)) is True
		assert bboxes_intersect(region, (2, 0, 4, 5)) is False

	def test_cascade_parent_maps_are_consistent(self):
		assert set(HIERARCHY_CHILD_DOCTYPE) == {1, 2, 3, 4, 5}
		assert set(HIERARCHY_PARENT_FIELD) == {1, 2, 3, 4, 5}
		assert HIERARCHY_CHILD_DOCTYPE[1] == "Governorate"
		assert HIERARCHY_PARENT_FIELD[5] == "village"


def test_api_imports_geometry_helpers_and_never_uses_numeric_between():
    """Regression locks for two server-only bugs (F821 is ignored by the
    project ruff config, and frappe's db_query breaks numeric `between`:
    it renders flt([a, b]) -> 0.0 into invalid SQL)."""
    import ast
    from pathlib import Path

    api = Path(__file__).resolve().parents[1] / "siraj_research" / "api" / "map_search.py"
    src = api.read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and "map_search" in node.module:
            imported.update(alias.name for alias in node.names)
    assert "bboxes_intersect" in imported, "search_bbox needs bboxes_intersect"
    assert '["between"' not in src, "numeric between emits broken SQL on frappe v15"
    assert '["latitude", ">=", ' in src, "bbox prefilter must use >= / <="
