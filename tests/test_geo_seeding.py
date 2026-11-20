"""Pure tests for CSV/GeoJSON parsing, rejections and resumable sessions."""

import json

from siraj_research.geo_seeding import (
    SeedSession,
    parse_hierarchy_csv,
    parse_hierarchy_geojson,
)

CSV = """\ufeffcode,name_en,name_local,parent_code,latitude,longitude,type
LB-BA-BA-A,Place A,المكان أ,LB-BA-BA,33.9,35.5,Municipality
LB-BA-BA-B,Place B,المكان ب,LB-BA-BA,,,Municipality
LB-BA-BA-C,Place C,المكان ج,LB-BA-BA,not-a-number,,Municipality
LB-BA-BA-A,Duplicate,مكرر,LB-BA-BA,,,Municipality
,Missing code,,LB-BA-BA,,,Municipality
LB-BA-BA-D,,,LB-BA-BA,,,Municipality
"""


def test_csv_import_accepts_aliases_bom_and_arabic():
    rows, rejections = parse_hierarchy_csv(CSV)
    assert [row["code"] for row in rows] == ["LB-BA-BA-A", "LB-BA-BA-B"]
    assert rows[0]["name_local"] == "المكان أ"
    assert rows[0]["latitude"] == 33.9
    assert rows[1]["latitude"] is None
    reasons = [rejection["reason"] for rejection in rejections]
    assert reasons.count("invalid_coordinates") == 1
    assert "duplicate_code" in reasons
    assert "missing_code" in reasons
    assert "missing_name_en" in reasons


def test_csv_import_supports_semicolon_delimiter_and_pcode_alias():
    text = "pcode;label_en;parent\nX-1;Alpha;X\nX-2;Beta;X\n"
    rows, rejections = parse_hierarchy_csv(text)
    assert [row["code"] for row in rows] == ["X-1", "X-2"]
    assert rows[0]["name_en"] == "Alpha"
    assert rejections == []


def test_geojson_import_requires_points_and_properties():
    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"code": "P-1", "name_en": "Point one", "parent_code": "P"},
                "geometry": {"type": "Point", "coordinates": [44.36, 33.31]},
            },
            {
                "type": "Feature",
                "properties": {"code": "A-1", "name_en": "Polygon"},
                "geometry": {"type": "Polygon", "coordinates": []},
            },
            {
                "type": "Feature",
                "properties": {"name_en": "No code"},
                "geometry": {"type": "Point", "coordinates": [1, 1]},
            },
        ],
    }
    rows, rejections = parse_hierarchy_geojson(json.dumps(payload))
    assert len(rows) == 1
    assert rows[0]["latitude"] == 33.31
    assert rows[0]["longitude"] == 44.36
    assert {rejection["reason"] for rejection in rejections} == {
        "unsupported_geometry", "missing_code_or_name",
    }


def test_geojson_import_rejects_invalid_json():
    rows, rejections = parse_hierarchy_geojson("{not json")
    assert rows == []
    assert rejections[0]["reason"] == "invalid_geojson"


def test_seed_session_counts_report_and_checkpoint(tmp_path):
    session = SeedSession("unit", tmp_path)
    session.count("Village", created=2)
    session.count("Village", existing=1)
    session.reject({"row": 7, "code": "V-7"}, "orphaned_parent", "parent missing", level=4)
    session.save_checkpoint(offset=42, done=False)
    summary = session.summary()
    assert summary["created"]["Village"] == 2
    assert summary["existing"]["Village"] == 1
    assert summary["rejected"]["orphaned_parent"] == 1
    assert summary["checkpoint"]["offset"] == 42
    report = session.write_report()
    text = open(report, encoding="utf-8").read()
    assert "orphaned_parent" in text and "V-7" in text
    checkpoint = SeedSession.load_checkpoint(session.checkpoint_path())
    assert checkpoint["offset"] == 42
    assert checkpoint["updated_at"]


def test_seed_session_without_report_dir_is_memory_only():
    session = SeedSession("memory")
    session.reject({"row": 1}, "invalid_geometry", "empty")
    assert session.write_report() is None
    assert session.save_checkpoint(offset=1) is None
    assert session.summary()["rejected"]["invalid_geometry"] == 1
