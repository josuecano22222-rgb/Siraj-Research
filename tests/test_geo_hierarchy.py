"""Pure-Python checks for the admin hierarchy bridge (no bench required)."""

from siraj_research import geo_hierarchy as gh


def test_normalise_chain_maps_six_levels_and_reports_gaps():
    chain = {
        "country": {"name_en": "Iraq", "pcode": "IQ"},
        "governorate": {"name_en": "Damascus", "pcode": "SY-DI"},
        "municipality": {"name_en": "Greater Damascus", "pcode": "SY-DI-DM-DM"},
    }
    entries, gaps = gh.normalise_chain(chain)
    assert set(entries) == {"country", "governorate", "municipality"}
    assert entries["municipality"]["level"] == 3
    assert [g["field"] for g in gaps] == ["district", "village", "community"]


def test_legacy_community_alias_becomes_village():
    entries, gaps = gh.normalise_chain({"community": {"name_en": "Old village", "level": 4}})
    assert "village" in entries
    assert "community" not in entries
    assert "village" not in {g["field"] for g in gaps}


def test_duplicate_alias_is_dropped_but_real_level_five_is_kept():
    entries, _ = gh.normalise_chain({
        "village": {"name_en": "Al-Midan", "pcode": "V1"},
        "community": {"name_en": "Al-Midan", "pcode": "V1", "level": 4},
    })
    assert "community" not in entries
    entries, _ = gh.normalise_chain({
        "village": {"name_en": "Al-Midan", "pcode": "V1"},
        "community": {"name_en": "Souq", "pcode": "Q1", "level": 5},
    })
    assert entries["community"]["level"] == 5


def test_gazetteer_only_fills_village_with_low_confidence():
    entries, gaps = gh.normalise_chain(
        {"country": {"name_en": "Iraq"}},
        {"name_en": "Ain al-Tamu", "distance_m": 320},
    )
    assert entries["village"]["confidence"] == "low"
    assert entries["village"]["source"] == "gazetteer_nearest"
    assert "village" not in {g["field"] for g in gaps}


def test_chain_rows_are_parent_first_and_deterministic():
    entries, _ = gh.normalise_chain({
        "country": {"name_en": "Syria", "pcode": "SY"},
        "governorate": {"name_en": "Damascus", "pcode": "SY-DI"},
        "district": {"name_en": "Damascus", "pcode": "SY-DI-DM"},
        "village": {"name_en": "Al-Midan", "pcode": "SY-DI-DM-DM-MD"},
    })
    rows = gh.chain_rows(entries)
    assert [r["field"] for r in rows] == ["governorate", "district", "village"]
    assert rows[0]["parent_code"] is None
    assert rows[1]["parent_code"] == "SY-DI"
    assert rows[2]["ancestor_codes"]["district"] == "SY-DI-DM"
    assert gh.chain_rows(entries) == rows


def test_make_code_handles_arabic_names_and_collisions():
    assert gh.make_code("IQ-BG", "بغداد", "IQ", 1) == "IQ-BG"
    derived = gh.make_code(None, "بغداد", "IQ-BG", 2)
    assert derived.startswith("D-IQ-BG-")
    assert len(derived) <= gh.MAX_CODE_LENGTH
    assert derived == gh.make_code(None, "بغداد", "IQ-BG", 2)
    assert gh.normalize_code("IQ.BG") == "IQ-BG"
    assert gh.make_code("IQ.BG", "Baghdad", "IQ", 1) == "IQ-BG"


class _FakeGeom:
    def __init__(self, area, contains):
        self.area = area
        self._contains = contains

    def contains(self, point):
        return self._contains


def test_iso_from_pcode_handles_dots_and_dashes():
    assert gh._iso_from_pcode("IL.01.123") == "IL"
    assert gh._iso_from_pcode("PS-BTH-BL") == "PS"
    assert gh._iso_from_pcode("442267") is None


def test_containing_ancestors_prefers_smallest_polygon_per_level():
    candidates = [
        {"level": 1, "pcode": "IL", "geom": _FakeGeom(100, True)},
        {"level": 2, "pcode": "IL-01", "geom": _FakeGeom(20, True)},
        {"level": 2, "pcode": "IL-02", "geom": _FakeGeom(10, False)},
        {"level": 3, "pcode": "IL-01-A", "geom": _FakeGeom(2, True)},
        {"level": 5, "pcode": "IL-01-A-Q", "geom": _FakeGeom(0.5, True)},
    ]
    ancestors = gh.containing_ancestors(4, (0, 0), candidates)
    assert set(ancestors) == {1, 2, 3}
    assert ancestors[2][1]["pcode"] == "IL-01"


def test_level_helpers_and_editable_fields():
    assert gh.field_to_level("community") == 5
    assert gh.level_spec("3")["doctype"] == "Municipality"
    assert "label_ar" in gh.editable_fields(2)
    assert "boundary" in gh.editable_fields(4)
    assert gh.hierarchy_settings()["auto_create_missing"] is True


def test_containing_ancestors_includes_country_polygon():
    candidates = [
        {"level": 0, "pcode": "IL", "country": "Israel", "geom": _FakeGeom(1000, True)},
        {"level": 2, "pcode": "IL-01", "geom": _FakeGeom(20, True)},
    ]
    ancestors = gh.containing_ancestors(3, (0, 0), candidates)
    assert set(ancestors) == {0, 2}
    assert ancestors[0][1]["country"] == "Israel"


def test_resolve_country_document_accepts_iso_codes_and_names():
    countries = {"IL": "Israel", "Israel": "Israel", "PS": "Palestinian Territory, Occupied"}
    assert gh._resolve_country_document("IL", countries) == "Israel"
    assert gh._resolve_country_document("PS-WE", countries) == "Palestinian Territory, Occupied"
    assert gh._resolve_country_document("Israel", countries) == "Israel"
