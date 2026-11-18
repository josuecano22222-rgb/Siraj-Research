"""Guard the DocType contract used by the resolver and importer."""

import json
from pathlib import Path

DOCTYPES = Path(__file__).resolve().parents[1] / "siraj_research" / "siraj_research" / "doctype"

LEVELS = {
    "governorate": "Governorate",
    "district": "District",
    "municipality": "Municipality",
    "village": "Village",
    "community": "Community",
}


def _load(slug):
    return json.loads((DOCTYPES / slug / f"{slug}.json").read_text(encoding="utf-8"))


def test_all_editable_levels_have_spatial_and_provenance_fields():
    expected = {
        "pcode", "parent_pcode", "admin_level_type", "latitude", "longitude",
        "bbox", "boundary", "geojson", "source_dataset", "source_kind",
        "last_verified_on",
    }
    for slug, doctype in LEVELS.items():
        doc = _load(slug)
        assert doc["name"] == doctype
        fields = {f["fieldname"] for f in doc["fields"]}
        assert expected <= fields, doctype
        assert set(doc["field_order"]) == fields


def test_admin_boundary_stores_bbox_index_geojson_and_hierarchy_link():
    fields = {f["fieldname"] for f in _load("admin_boundary")["fields"]}
    assert {
        "bbox_min_lon", "bbox_min_lat", "bbox_max_lon", "bbox_max_lat",
        "linked_hierarchy_doctype", "linked_hierarchy",
    } <= fields
    geom = {f["fieldname"] for f in _load("admin_boundary_geom")["fields"]}
    assert "geom_geojson" in geom


def test_settings_allow_auto_creation_and_all_providers():
    fields = {f["fieldname"]: f for f in _load("geo_settings")["fields"]}
    assert {"auto_create_missing", "link_gazetteer_as_village",
            "online_fallback_when", "online_user_agent",
            "online_min_interval_s"} <= set(fields)
    options = fields["online_provider"]["options"].split("\n")
    assert "Nominatim (OpenStreetMap)" in options
    assert "Google Geocoding" in options


def test_boundary_dataset_can_tune_batch_size():
    fields = {f["fieldname"] for f in _load("boundary_dataset")["fields"]}
    assert {"store_geojson", "import_batch_size", "last_processed_offset"} <= fields
