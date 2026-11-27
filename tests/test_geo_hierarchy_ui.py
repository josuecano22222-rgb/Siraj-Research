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

    class Meta:
        def has_field(self, name):
            return name in {"country", "governorate", "district", "municipality",
                            "place_name", "geocoding_method", "geometry_source"}

        def get_field(self, name):
            return SimpleNamespace(fieldname=name, fieldtype="Data")

    # The fake must be in place before field_values: with a real frappe
    # package but no site, frappe.get_meta dies on frappe.cache being None.
    fake_frappe = SimpleNamespace(get_meta=lambda dt: Meta())
    monkeypatch.setattr(ui, "frappe", fake_frappe)

    result = ui.display_resolution(31.78, 35.22)
    values = ui.field_values("Person", result)
    assert values["country"] == "Israel"
    assert values["governorate"] == "IL-JM"
    assert values["place_name"] == "Jerusalem"
    assert "village" not in values

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
    ("siraj_event", ["country", "governorate", "district", "municipality", "village", "community"]),
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

    for doctype in ("Person", "Institution", "Place", "Siraj Event",
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
    assert "$anchor.after(group);" in source
    assert "resolveFromInputs(frm2, cfg);" in source
    assert "if (lat === 0 && lon === 0 && !originConfirmed(frm, cfg)) return;" in source
    assert "use_online: 1" in source


def test_geopoint_bridge_does_not_construct_missing_leaflet_draw_plugin():
    root = Path(__file__).resolve().parents[1]
    source = (root / "siraj_research/public/js/siraj-geopoint.js").read_text()
    assert "L.Control.Draw is not a constructor" in source
    assert "C.prototype.make_map = function (value)" in source
    assert "new L.Control.Draw" not in source


def test_map_mount_initializes_form_flags_before_setting_marker():
    root = Path(__file__).resolve().parents[1]
    source = (root / "siraj_research/public/js/coordinate_map.js").read_text()
    assert "frm.flags = frm.flags || {};" in source
    assert source.index("frm.flags = frm.flags || {};") < source.index("frm.flags.siraj_custom_map = true;")


def test_field_values_never_writes_unlinked_pcodes_into_link_fields(monkeypatch):
    result = {
        "by_field": {
            "country": {"status": "resolved", "name": None, "code": "PS", "label_en": "Palestine"},
            "governorate": {"status": "linked", "name": "Gaza", "code": "PS-GZ", "label_en": "Gaza"},
            "district": {"status": "gap"},
        },
        "nearest_place_name": "Khan Yunis Camp",
    }

    class Field:
        def __init__(self, fieldtype):
            self.fieldtype = fieldtype

    class Meta:
        def has_field(self, name):
            return name in {"country", "governorate", "district", "place_name"}

        def get_field(self, name):
            return Field("Data" if name == "place_name" else "Link")

    fake_frappe = SimpleNamespace(get_meta=lambda dt: Meta())
    monkeypatch.setattr(ui, "frappe", fake_frappe)
    values = ui.field_values("Person", result)
    assert "country" not in values  # raw PS is not a valid Country doc name
    assert values["governorate"] == "Gaza"
    assert "district" not in values
    assert values["place_name"] == "Khan Yunis Camp"


def test_form_autofill_uses_linked_server_rows_and_survives_missing_toolbar():
    root = Path(__file__).resolve().parents[1]
    source = (root / "siraj_research/public/js/coordinate_map.js").read_text()
    hierarchy = (root / "siraj_research/public/js/siraj-hierarchy.js").read_text()
    assert "window.SirajHierarchy.resolve(lat, lon, {" in source
    assert "createMissing: true, useOnline: true," in source
    assert "value = (row.status === 'linked' && row.name) ? row.name : null;" in source
    assert "const fallbackToolbar = () => {" in source
    assert "if (opts.force) { cache.delete(k); inflight.delete(k); }" in hierarchy


def test_all_browser_tiles_route_through_server_cache():
    root = Path(__file__).resolve().parents[1]
    js_root = root / "siraj_research" / "public" / "js"
    for path in js_root.rglob("*.js"):
        if "vendor" in path.parts:
            continue
        source = path.read_text()
        assert "tile.openstreetmap.org" not in source, str(path)


def test_toolbar_installs_eagerly_after_leaflet_require():
    root = Path(__file__).resolve().parents[1]
    toolbar = (root / "siraj_research/public/js/siraj-map-toolbar.js").read_text()
    coord = (root / "siraj_research/public/js/coordinate_map.js").read_text()
    assert "window.SirajMapToolbar = {" in toolbar
    assert "window.SirajMapToolbar.install(window.L);" in coord


def test_hierarchy_upsert_is_parent_safe_and_duplicate_tolerant():
    root = Path(__file__).resolve().parents[1]
    source = (root / "siraj_research/geo_hierarchy.py").read_text()
    assert "def _resolve_link_name(" in source
    assert '"reason": "parent_not_found"' in source
    assert '"Duplicate entry" in message' in source
    bulk = (root / "siraj_research/geo_bulk.py").read_text()
    assert '"active_boundary_dataset", dataset' in bulk


def test_geo_package_returns_json_dict_and_client_unwraps_message():
    root = Path(__file__).resolve().parents[1]
    server = (root / "siraj_research/api/geo_package.py").read_text()
    client = (root / "siraj_research/public/js/siraj-geo.js").read_text()
    assert 'frappe.response["data"]' not in server
    assert '"etag": f"{dataset}:{int(version or 0)}.{PACKAGE_FORMAT}"' in server
    assert '"format": PACKAGE_FORMAT' in server
    assert 'ab.country' in server
    assert '?version=' in client
    assert "wrapped.message !== undefined" in client


def test_tile_failures_are_fast_and_cheap():
    root = Path(__file__).resolve().parents[1]
    source = (root / "siraj_research/tile_cache.py").read_text()
    assert "_HTTP_TIMEOUT = 4" in source
    assert "_EMPTY_PNG" in source
    assert 'frappe.logger("siraj.tile_cache").warning' in source
    assert 'frappe.log_error(f"Tile fetch failed' not in source


def test_save_hook_skips_resolution_when_hierarchy_is_already_complete():
    root = Path(__file__).resolve().parents[1]
    source = (root / "siraj_research/geo_doc_events.py").read_text()
    assert "level_fields" in source
    assert "not hasattr(doc, fieldname) or getattr(doc, fieldname) not in (None, \"\")" in source


def test_precision_column_is_backticked_in_spatial_sql():
    root = Path(__file__).resolve().parents[1]
    for name in ("siraj_research/api/geo_package.py", "siraj_research/api/geo_resolve.py"):
        source = (root / name).read_text()
        assert "ag.`precision`" in source, name
        assert "precision," not in source.split("ROW_NUMBER()")[0].split("SELECT parent")[-1] or name.endswith("geo_resolve.py")


def test_offline_package_carries_real_linked_names():
    root = Path(__file__).resolve().parents[1]
    server = (root / "siraj_research/api/geo_package.py").read_text()
    worker = (root / "siraj_research/public/js/siraj-geo-worker.js").read_text()
    hierarchy = (root / "siraj_research/public/js/siraj-hierarchy.js").read_text()
    coord = (root / "siraj_research/public/js/coordinate_map.js").read_text()
    assert "def _linked_name_maps(" in server
    assert "linked_name," in server
    assert "linked_name: row[6]||''" in worker
    assert "linked_name: cur.linked_name" in worker
    assert "const linkedName = node && node.linked_name" in hierarchy
    assert "name: linkedName" in hierarchy
    assert "{ offlineOnly: true }" in coord


def test_zero_internet_bootstrap_assets_exist():
    root = Path(__file__).resolve().parents[1]
    server = (root / "siraj_research/api/geo_package.py").read_text()
    client = (root / "siraj_research/public/js/siraj-geo.js").read_text()
    docs = (root / "docs/offline-first.md").read_text()
    assert "def export_offline_package(" in server
    assert "/assets/siraj_research/data/geo-package.json" in client
    assert "SIRAJ_OFFLINE_BOOTSTRAP" in client
    assert "allow_tile_fetch" in docs
    assert "Offline" in docs


def test_offline_bootstrapTile_math_and_lock():
    import math

    from siraj_research.offline_bootstrap import DEFAULT_BBOX, _lat_to_y, _lon_to_x, tile_range

    xs, ys = tile_range(DEFAULT_BBOX, 4)
    assert xs.start <= xs.stop and ys.start <= ys.stop
    for z in (0, 4, 11):
        assert 0 <= _lon_to_x(0.0, z) < 2 ** z
        assert 0 <= _lat_to_y(0.0, z) < 2 ** z
    assert math.isfinite(DEFAULT_BBOX[0])


def test_offline_bootstrap_source_contains_full_workflow():
    root = Path(__file__).resolve().parents[1]
    source = (root / "siraj_research/offline_bootstrap.py").read_text()
    docs = (root / "docs/offline-first.md").read_text()
    assert "def prepare_offline_site(" in source
    assert "def lock_offline_mode(" in source
    assert "def prewarm_tiles(" in source
    assert "def download_python_wheels(" in source
    assert "from siraj_research.geo_bulk import sync_boundary_hierarchy" in source
    assert "def _step(" in source
    assert 'prepare_offline_site' in docs
    assert '"create_missing":True' in docs


def test_bootstrap_progress_is_immediate_and_tailable():
    root = Path(__file__).resolve().parents[1]
    source = (root / "siraj_research/offline_bootstrap.py").read_text()
    docs = (root / "docs/offline-first.md").read_text()
    assert "def emit(" in source
    assert "print(f\"[SIRAJ offline] {stage}: {message}\", flush=True)" in source
    assert "bootstrap-progress.json" in source
    assert "tail -f" in docs


def test_bootstrap_step_failure_does_not_abort_remaining_stages(monkeypatch):
    import siraj_research.offline_bootstrap as ob
    from siraj_research.offline_bootstrap import _step

    # Outside a site frappe.db is unbound; the stop-flag probe would raise
    # 'object is not bound' before the stage function runs. The test is
    # about failure isolation, so pin the flag to False.
    monkeypatch.setattr(ob, "stop_requested", lambda: False)

    def broken(**kwargs):
        raise RuntimeError("demo failure")

    result = _step("demo", broken)
    assert "demo failure" in result["error"]


def test_bootstrap_reports_real_failures_and_guards_lock():
    root = Path(__file__).resolve().parents[1]
    source = (root / "siraj_research/offline_bootstrap.py").read_text()
    docs = (root / "docs/offline-first.md").read_text()
    assert '"failed": failed' in source
    assert '"cached": cached' in source
    assert '"skipped": "incomplete_downloads"' in source
    assert "force_lock" in source
    assert "written`, `cached` and `failed`" in docs



def test_cascade_is_wired_into_every_desk_form():
    root = Path(__file__).resolve().parents[1]
    bundle = (root / "siraj_research/public/js/siraj.bundle.js").read_text()
    cascade = (root / "siraj_research/public/js/siraj-cascade.js").read_text()
    core = (root / "siraj_research/public/js/siraj-cascade-core.js").read_text()
    server = (root / "siraj_research/geo_cascade.py").read_text()
    assert "import './siraj-cascade-core.js';" in bundle
    assert "import './siraj-cascade.js';" in bundle
    assert "siraj_research.geo_cascade.cascade" in cascade
    assert "frm.set_query(field" in cascade
    assert "clearDescendants" in cascade
    assert "root.SirajCascadeCore = api" in core
    assert "def cascade(field" in server
    assert "ancestor_filters" in server


def test_offline_bootstrap_has_settings_stop_control():
    import json

    root = Path(__file__).resolve().parents[1]
    source = (root / "siraj_research/offline_bootstrap.py").read_text()
    settings = json.loads((root / "siraj_research/siraj_research/doctype/geo_settings/geo_settings.json").read_text())
    fields = {f.get("fieldname") for f in settings["fields"]}
    hooks = (root / "siraj_research/hooks.py").read_text()
    js = (root / "siraj_research/public/js/geo_settings.js").read_text()
    docs = (root / "docs/offline-first.md").read_text()
    assert "class BootstrapStopped" in source
    assert "def request_stop" in source
    assert "check_stop(\"tiles\")" in source
    assert "bootstrap_stop_requested=0" in source
    assert {"stop_bootstrap", "bootstrap_running", "bootstrap_stop_requested",
            "bootstrap_last_status"} <= fields
    assert '"Geo Settings": "public/js/geo_settings.js"' in hooks
    assert "siraj_research.offline_bootstrap.request_stop" in js
    assert "Stop Offline Bootstrap" in docs


def test_online_setup_toggle_and_run_button():
    import json

    root = Path(__file__).resolve().parents[1]
    settings = json.loads((root / "siraj_research/siraj_research/doctype/geo_settings/geo_settings.json").read_text())
    fields = {f.get("fieldname") for f in settings["fields"]}
    source = (root / "siraj_research/offline_bootstrap.py").read_text()
    js = (root / "siraj_research/public/js/geo_settings.js").read_text()
    docs = (root / "docs/offline-first.md").read_text()
    assert {"online_setup_enabled", "run_online_setup", "sb_online_setup"} <= fields
    assert "def online_setup_allowed" in source
    assert "def run_online_setup" in source
    assert "online_setup_disabled" in source or "skipped: online setup disabled" in source
    assert "siraj_research.offline_bootstrap.run_online_setup" in js
    assert "Allow online setup downloads" in docs
    # Default is enabled so a fresh install can prepare online.
    default_row = next(f for f in settings["fields"] if f.get("fieldname") == "online_setup_enabled")
    assert str(default_row.get("default", "1")) == "1"


def test_cascade_offline_options_are_global_until_parent_is_set():
    root = Path(__file__).resolve().parents[1]
    core = (root / "siraj_research/public/js/siraj-cascade-core.js").read_text()
    cascade = (root / "siraj_research/public/js/siraj-cascade.js").read_text()
    # No parent → every row at that level (global search).
    assert "rec.level === level" in core
    assert "No ancestor chosen yet" in core
    # Status box labels the unscoped list.
    assert "all countries" in cascade
    # Upward fill still uses the shared applyChain path.
    assert "applyChain" in cascade
    assert "clearDescendants" in cascade


def test_setup_region_helper_exists_for_multi_region_import():
    root = Path(__file__).resolve().parents[1]
    bulk = (root / "siraj_research/geo_bulk.py").read_text()
    docs = (root / "docs/installation.md").read_text()
    assert "def setup_region(" in bulk
    assert "setup_region" in docs
    assert "OSM-LB" in docs
    # Dead helpers removed in this release.
    cascade = (root / "siraj_research/geo_cascade.py").read_text()
    demo = (root / "siraj_research/setup/demo_data.py").read_text()
    assert "def _label_field" not in cascade
    assert "def _extid" not in demo


def test_prewarm_enables_shared_basemaps_and_skips_disabled_layers():
    root = Path(__file__).resolve().parents[1]
    source = (root / "siraj_research/offline_bootstrap.py").read_text()
    assert "enable_shared_basemaps" in source
    assert "skipped_layers" in source
    assert "skipped (disabled in Geo Settings)" in source
    # Disabled layers must not abort the whole pass (no bare throw path).
    assert "_resolve_layer" in source


def test_setup_region_does_not_export_while_import_is_queued():
    root = Path(__file__).resolve().parents[1]
    bulk = (root / "siraj_research/geo_bulk.py").read_text()
    assert 'skipped": "import_queued"' in bulk or "'import_queued'" in bulk
    assert "Wait until Boundary Dataset shows Complete" in bulk
