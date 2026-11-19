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


def test_js_build_stamps_match_server_stamp():
    from siraj_research.record_icons import SIRAJ_BUILD

    root = Path(__file__).resolve().parents[1]
    for relative in (
        "siraj_research/public/js/siraj-record-meta.js",
        "siraj_research/public/js/siraj-map/siraj-map.js",
    ):
        assert SIRAJ_BUILD in (root / relative).read_text()


def test_every_coordinate_doctype_has_native_map_and_zero_confirmation_field():
    import json

    from siraj_research.record_icons import COORDINATE_DOCS

    root = Path(__file__).resolve().parents[1]
    checked = 0
    for path in (root / "siraj_research/siraj_research/doctype").glob("*/*.json"):
        meta = json.loads(path.read_text())
        fields = meta.get("fields", [])
        names = {field.get("fieldname") for field in fields}
        if "latitude" not in names or "longitude" not in names:
            continue
        checked += 1
        by_name = {field.get("fieldname"): field for field in fields}
        assert by_name["geo_point"]["fieldtype"] == "Geolocation", meta["name"]
        assert by_name["coordinate_origin_confirmed"]["fieldtype"] == "Check", meta["name"]
        assert by_name["geo_point"]["insert_after"] == "longitude"
    assert checked >= 7
    for doctype, cfg in COORDINATE_DOCS.items():
        assert cfg["map_field"] == "geo_point", doctype
        assert cfg["origin_confirmed_field"] == "coordinate_origin_confirmed", doctype


def test_bundle_imports_native_map_bridge():
    root = Path(__file__).resolve().parents[1]
    bundle = (root / "siraj_research/public/js/siraj.bundle.js").read_text()
    assert "import './siraj-geopoint-core.js';" in bundle
    assert "import './siraj-geopoint.js';" in bundle


def test_doc_event_hook_ignores_unconfirmed_zero_pair(monkeypatch):
    from siraj_research import geo_doc_events

    class FakeFlags:
        siraj_hierarchy_resolved = False

    doc = SimpleNamespace(doctype="Place", latitude=0, longitude=0,
                          coordinate_origin_confirmed=0, country="",
                          flags=FakeFlags())
    calls = []

    def fake_apply(doc, **kwargs):
        calls.append(kwargs)
        return {"updated": []}

    monkeypatch.setattr("siraj_research.geo_hierarchy_ui.apply_to_doc", fake_apply)
    geo_doc_events.auto_fill_hierarchy(doc)
    assert calls == []
    assert doc.flags.siraj_hierarchy_resolved is False


def test_all_map_layers_use_shared_server_tile_cache():
    root = Path(__file__).resolve().parents[1]
    sources = {
        name: (root / path).read_text()
        for name, path in {
            "basemap": "siraj_research/public/js/siraj-basemap.js",
            "maplibre": "siraj_research/public/js/siraj-map/siraj-map.js",
        }.items()
    }
    for name, source in sources.items():
        assert "tile_cache.tile?layer=standard" in source or name == "basemap", name
        assert "tile_cache.tile?layer=aerial" in source, name
        assert "tile_cache.tile?layer=hybrid" in source, name
        assert "tile_cache.tile?layer=hybrid_labels" in source, name
        assert "server.arcgisonline.com" not in source, name
        assert "tile.openstreetmap.org" not in source, name

    tile_cache_source = (root / "siraj_research/tile_cache.py").read_text()
    assert "def enable_shared_basemaps()" in tile_cache_source


def test_enhanced_map_mirrors_pick_into_geolocation_field():
    root = Path(__file__).resolve().parents[1]
    source = (root / "siraj_research/public/js/coordinate_map.js").read_text()
    assert "function syncMapField(frm, cfg, lat, lon)" in source
    assert "syncMapField(frm, cfg, latitude, longitude);" in source
    assert "$nativeWrapper.append(group);" in source
