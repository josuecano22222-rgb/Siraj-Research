"""Pure checks for universal hierarchy display and form-fill helpers."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from siraj_research import geo_hierarchy_ui as ui


@pytest.fixture
def linked():
    return {
        "country": {"name": "Israel", "code": "IL", "label_en": "Israel", "label_ar": "إسرائيل"},
        "hierarchy": [
            {"field": "governorate", "name": "IL-JM", "code": "IL-JM", "pcode": "IL-JM",
             "label_en": "Jerusalem", "label_ar": "القدس", "source": "polygon_containment"},
            {"field": "district", "name": "IL-JM-01", "code": "IL-JM-01",
             "label_en": "Jerusalem District", "label_ar": None},
            {"field": "municipality", "name": "IL-JM-01-01", "code": "IL-JM-01-01",
             "label_en": "Jerusalem Municipality", "label_ar": None},
        ],
        "gaps": [
            {"field": "village", "reason": "no_polygon_at_level"},
            {"field": "community", "reason": "no_polygon_at_level"},
        ],
        "warnings": [], "provenance": ["polygon_containment"],
        "ambiguous": False, "on_land": True,
        "raw": {"dataset": "OSM-IL-PS", "nearest_place": {"name_en": "Jerusalem"}},
    }


def test_display_resolution_builds_six_levels_with_gaps(monkeypatch, linked):
    import siraj_research.geo_hierarchy as gh

    monkeypatch.setattr(gh, "resolve_and_link",
                        lambda *a, **k: {**linked, "raw": dict(linked["raw"], lat=a[0], lon=a[1])})
    result = ui.display_resolution(31.78, 35.22)
    assert [row["field"] for row in result["levels"]] == [
        "country", "governorate", "district", "municipality", "village", "community"]
    assert result["resolved_count"] == 4
    assert result["deepest_level"] == 3
    assert [row["field"] for row in result["gaps"]] == ["village", "community"]
    assert result["status"] if "status" in result else True
    assert result["by_field"]["governorate"]["name"] == "IL-JM"
    assert result["by_field"]["village"]["status"] == "gap"
    assert "Jerusalem Municipality" in result["text_en"]
    assert "Jerusalem" in result["nearest_place_name"]


def test_display_resolution_rejects_invalid_longitude():
    result = ui.display_resolution(31.7, 200)
    assert result["error"] == "Invalid coordinates"


def test_field_values_and_apply_to_doc_fill_only_empty_fields(monkeypatch, linked):
    import siraj_research.geo_hierarchy as gh

    monkeypatch.setattr(gh, "resolve_and_link", lambda *a, **k: linked)
    result = ui.display_resolution(31.78, 35.22)
    values = ui.field_values("Person", result)
    assert values["country"] == "Israel"
    assert values["governorate"] == "IL-JM"
    assert values["place_name"] == "Jerusalem"
    assert "village" not in values

    class Meta:
        def has_field(self, name):
            return name in {"country", "governorate", "district", "municipality",
                            "place_name", "geocoding_method", "geometry_source"}

    fake_frappe = SimpleNamespace(get_meta=lambda dt: Meta())
    monkeypatch.setattr(ui, "frappe", fake_frappe)
    doc = SimpleNamespace(doctype="Person", latitude=31.78, longitude=35.22,
                          country="", governorate="Existing Governorate", place_name=None)
    applied = ui.apply_to_doc(doc, result=result)
    assert "country" in applied["updated"]
    assert "governorate" not in applied["updated"]
    assert doc.country == "Israel"
    assert doc.governorate == "Existing Governorate"
    assert doc.geocoding_method == "administrative"
    assert doc.geometry_source == "polygon_resolver"


@pytest.mark.parametrize("doctype, expected", [
    ("institution", ["country", "governorate", "district", "municipality", "village", "community"]),
    ("research_event", ["country", "governorate", "district", "municipality", "village", "community"]),
    ("operational_deployment", ["country", "governorate", "district", "municipality", "village", "community"]),
])
def test_additive_hierarchy_fields_exist_on_all_geo_doctypes(doctype, expected):
    root = Path(__file__).resolve().parents[1]
    path = root / "siraj_research" / "siraj_research" / "doctype" / doctype / f"{doctype}.json"
    meta = json.loads(path.read_text())
    names = {field.get("fieldname") for field in meta["fields"]}
    assert set(expected) <= names


def test_coordinate_registry_covers_every_geo_doctype():
    from siraj_research.record_icons import COORDINATE_DOCS

    for doctype in ("Person", "Institution", "Place", "Research Event", "Siraj Event",
                    "Military Unit", "Operational Deployment"):
        assert doctype in COORDINATE_DOCS
        assert COORDINATE_DOCS[doctype]["admin_fields"]["community"] == "community"


def test_doc_event_hook_fills_empty_hierarchy_fields(monkeypatch):
    from siraj_research import geo_doc_events

    class FakeFlags:
        siraj_hierarchy_resolved = False

    doc = SimpleNamespace(doctype="Place", latitude=31.78, longitude=35.22,
                          country="", flags=FakeFlags())
    calls = []

    def fake_apply(doc, **kwargs):
        doc.country = "Israel"
        calls.append(kwargs)
        return {"updated": ["country"]}

    monkeypatch.setattr("siraj_research.geo_hierarchy_ui.apply_to_doc", fake_apply)
    geo_doc_events.auto_fill_hierarchy(doc)
    assert doc.country == "Israel"
    assert doc.flags.siraj_hierarchy_resolved is True
    assert calls and calls[0]["create_missing"] is True


def test_doc_event_hook_ignores_unconfigured_doctypes():
    from siraj_research import geo_doc_events

    doc = SimpleNamespace(doctype="Country", flags=SimpleNamespace())
    geo_doc_events.auto_fill_hierarchy(doc)
