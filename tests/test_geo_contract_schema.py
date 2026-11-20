"""Static contract checks for the hierarchy DocTypes and new modules."""

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCTYPE_ROOT = ROOT / "siraj_research" / "siraj_research" / "doctype"
APP_ROOT = ROOT / "siraj_research"
LEVEL_SLUGS = ("governorate", "district", "municipality", "village", "community")


def _doctype(slug: str) -> dict:
    return json.loads((DOCTYPE_ROOT / slug / f"{slug}.json").read_text(encoding="utf-8"))


def _fieldnames(doc: dict) -> set[str]:
    return {field["fieldname"] for field in doc["fields"]}


def test_new_doctypes_are_well_formed():
    for slug in ("admin_level", "country_level_config", "country_level_row",
                 "geographic_administration"):
        doc = _doctype(slug)
        assert doc["module"] == "Siraj Research"
        assert _fieldnames(doc) == set(doc["field_order"])
        controller = DOCTYPE_ROOT / slug / f"{slug}.py"
        tree = ast.parse(controller.read_text(encoding="utf-8"))
        expected = doc["name"].replace(" ", "")
        classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        assert expected in classes


def test_country_level_config_uses_a_child_table():
    doc = _doctype("country_level_config")
    table = next(field for field in doc["fields"] if field["fieldname"] == "levels")
    assert table["fieldtype"] == "Table"
    assert table["options"] == "Country Level Row"
    child = _doctype("country_level_row")
    assert child["istable"] == 1
    assert {"level", "level_key", "is_active", "label_en", "label_ar", "skip_reason"} <= _fieldnames(child)


def test_level_doctypes_carry_ancestry_and_active_fields():
    for slug in LEVEL_SLUGS:
        doc = _doctype(slug)
        fields = _fieldnames(doc)
        assert {"ancestry_path", "ancestry_labels", "hierarchy_level", "is_active"} <= fields, slug
        assert fields == set(doc["field_order"]), slug
        assert any(
            field["fieldname"] == "ancestry_path" and field.get("search_index") == 1
            for field in doc["fields"]
        ), slug


def test_geographic_administration_exposes_the_canonical_contract():
    fields = _fieldnames(_doctype("geographic_administration"))
    assert {
        "code", "title", "name_en", "name_local", "source", "is_active",
        "country", "governorate", "district", "municipality", "village", "community",
        "hierarchy_level", "level_key", "level_label", "ancestry_path",
        "ancestry_labels", "centroid_lat", "centroid_lng", "geo_point", "boundary",
        "resolution_source", "resolved_on",
    } <= fields


def test_geo_settings_expose_backend_and_throttle_controls():
    fields = _fieldnames(_doctype("geo_settings"))
    assert {"spatial_backend", "endpoint_rate_limit_per_min", "border_tolerance_m",
            "online_geocoder_enabled", "online_provider"} <= fields


def test_no_placeholder_markers_in_new_modules():
    modules = [
        APP_ROOT / "geo_levels.py",
        APP_ROOT / "geo_lineage.py",
        APP_ROOT / "geo_admin.py",
        APP_ROOT / "geo_postgis.py",
        APP_ROOT / "geo_seeding.py",
        APP_ROOT / "offline_verify.py",
        APP_ROOT / "api" / "throttle.py",
        APP_ROOT / "commands" / "geo.py",
    ]
    forbidden = ("TODO", "FIXME", "implement later", "NotImplementedError")
    for module in modules:
        text = module.read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in text, f"{module.name} contains {marker}"


def test_commands_module_registers_the_geo_group():
    text = (APP_ROOT / "commands" / "__init__.py").read_text(encoding="utf-8")
    assert "commands = [*geo_commands]" in text
    geo_text = (APP_ROOT / "commands" / "geo.py").read_text(encoding="utf-8")
    for command in (
        "seed-levels", "seed-core", "seed-demo", "import-csv", "audit",
        "backfill-ancestry", "postgis-init", "postgis-backfill", "postgis-health",
        "verify-offline", "benchmark", "resolve", "seed-ga",
    ):
        assert f'@geo.command("{command}")' in geo_text, command
