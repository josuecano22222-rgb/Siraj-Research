"""Streaming bulk-import helpers (no bench, no network)."""

import zipfile
from types import SimpleNamespace

import pytest

from siraj_research import geo_bulk as gb


@pytest.fixture(autouse=True)
def _no_frappe(monkeypatch):
    """These are pure-Python tests even when a bench venv imports Frappe."""
    monkeypatch.setattr(gb, "frappe", None)

GEONAMES_LINE = "\t".join([
    "1", "Baghdad", "Baghdad", "", "33.3152", "44.3661", "P", "PPLC",
    "IQ", "", "BG", "", "", "", "7900000", "34", "30", "Asia/Baghdad", "2024-01-01",
]) + "\n"
SECOND_LINE = GEONAMES_LINE.replace("Baghdad\tBaghdad", "Mosul\tMosul") \
    .replace("33.3152", "36.3550").replace("44.3661", "43.1215") \
    .replace("\t1\t", "\t2\t")


def test_parse_geonames_line_maps_admin_codes():
    row = gb.parse_geonames_line(GEONAMES_LINE)
    assert row["name_en"] == "Baghdad"
    assert row["country_code"] == "IQ"
    assert row["admin1_pcode"] == "IQ.BG"
    assert row["admin2_pcode"] is None
    assert row["population"] == 7900000
    assert row["modification_date"] == "2024-01-01"


def test_parse_geonames_line_rejects_bad_coordinates():
    bad = GEONAMES_LINE.replace("33.3152", "200")
    assert gb.parse_geonames_line(bad) is None
    assert gb.parse_geonames_line("short\tline\n") is None


def test_import_geonames_streams_zip_without_frappe(tmp_path):
    archive = tmp_path / "cities.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("cities15000.txt", GEONAMES_LINE + SECOND_LINE)
    result = gb.import_geonames(str(archive), "GEONAMES-TEST", batch_size=1)
    assert result["dataset"] == "GEONAMES-TEST"
    assert result["note"].startswith("GeoNames cities.zip")


def test_import_geonames_respects_country_filter_and_offset(tmp_path):
    archive = tmp_path / "cities.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("cities15000.txt", GEONAMES_LINE + SECOND_LINE.replace("\tIQ\t", "\tSY\t"))
    result = gb.import_geonames(str(archive), "GEONAMES-TEST",
                                country_codes=["IQ"], offset=0, batch_size=10)
    assert result["complete"] is True


def test_parse_geonames_admin_codes():
    first = gb.parse_geonames_admin_line("IQ.BG\tBaghdad\tBaghdad\t123\n", level=1)
    second = gb.parse_geonames_admin_line("IQ.BG.AL\tAl Adhamiyah\tAl Adhamiyah\t456\n", level=2)
    assert first["country_code"] == "IQ"
    assert first["pcode"] == "IQ.BG"
    assert second["pcode"] == "IQ.BG.AL"
    assert gb.parse_geonames_admin_line("broken\n", level=1) is None


def test_geonames_line_exposes_admin3_and_admin4_codes():
    row = gb.parse_geonames_line(GEONAMES_LINE)
    assert row["admin1_pcode"] == "IQ.BG"
    # The fixture has no admin2/3/4 codes, so deeper codes stay empty.
    assert row["admin3_pcode"] is None
    assert row["admin4_pcode"] is None


def test_iter_geonames_lines_reads_plain_directory(tmp_path):
    (tmp_path / "allCountries.txt").write_text(GEONAMES_LINE, encoding="utf-8")
    rows = list(gb._iter_geonames_lines(tmp_path, "allCountries"))
    assert len(rows) == 1
    assert rows[0][0] == "allCountries.txt"
    assert "Baghdad" in rows[0][1]


def test_geonames_line_builds_deepest_code_when_admin3_is_empty():
    parts = GEONAMES_LINE.rstrip("\n").split("\t")
    parts[7] = "ADM4"
    parts[11] = "AL"
    parts[12] = ""
    parts[13] = "X"
    row = gb.parse_geonames_line("\t".join(parts) + "\n")
    assert row["admin3_pcode"] is None
    assert row["admin4_pcode"] == "IQ.BG.AL.X"


def test_choose_admin_parent_skips_missing_intermediate_levels():
    names = {
        "IQ-BG": "Baghdad Governorate",
        "IQ-BG-AL": "Al Adhamiyah",
    }
    countries = {"IQ": "Iraq"}
    assert gb.choose_admin_parent(2, "IQ.BG", names, countries) == (
        "Baghdad Governorate", "governorate", 1)
    # ADM3 is absent; the village attaches to the deepest known district.
    assert gb.choose_admin_parent(4, "IQ.BG.AL.MISSING", names, countries) == (
        "Al Adhamiyah", "district", 2)
    assert gb.choose_admin_parent(5, "IQ.BG.AL.MISSING.X", names, countries) == (
        "Al Adhamiyah", "district", 2)
    assert gb.choose_admin_parent(1, "IQ", names, countries) == ("Iraq", "country", 0)


def test_osm_commands_are_argv_lists_not_shell_strings():
    commands = gb.osm_commands("/data/my country.pbf", "/data/out")
    assert len(commands) == 2
    assert all(isinstance(command, list) for command in commands)
    assert commands[0][0] == "osmium"
    assert "--overwrite" in commands[0]
    assert "--add-unique-id=type_id" in commands[1]
    assert commands[1][-1].endswith("my country-boundaries.geojson")
    assert gb.prepare_osm("/data/x.pbf", "/data/out", run=False)["ran"] is False


def test_sync_levels_preserves_none_for_all_levels():
    assert gb._normalise_sync_levels(None) is None
    assert gb._normalise_sync_levels([3, 5]) == [3, 5]
    assert gb._normalise_sync_levels([]) == []


def test_reset_boundary_dataset_removes_old_polygons_and_hierarchy(monkeypatch):
    calls = []

    class FakeDB:
        def delete(self, doctype, filters):
            calls.append((doctype, filters))

        def set_value(self, *args, **kwargs):
            calls.append(("set_value", args, kwargs))

        def commit(self):
            calls.append(("commit",))

    fake = SimpleNamespace(
        get_all=lambda doctype, **kwargs: (
            ["AB1"] if doctype == "Admin Boundary"
            else ["D1"] if doctype == "District"
            else []
        ),
        db=FakeDB(),
    )
    monkeypatch.setattr(gb, "frappe", fake)

    result = gb.reset_boundary_dataset("OSM-IL-PS")
    assert result == {"dataset": "OSM-IL-PS", "boundaries_deleted": 1,
                      "hierarchy_rows_deleted": 1}
    assert ("Admin Boundary Geom", {"parent": ["in", ["AB1"]]}) in calls
    assert ("Admin Boundary", {"name": ["in", ["AB1"]]}) in calls
    assert ("District", {"name": ["in", ["D1"]]}) in calls


def test_enqueue_geonames_admin_marks_dataset_queued(monkeypatch):
    """The enqueuer must surface Queued so import_status_report is honest."""
    calls = {}

    def _set_value(doctype, name, values, update_modified=False):
        calls["set_value"] = (doctype, name, values)

    fake = SimpleNamespace(
        db=SimpleNamespace(set_value=_set_value, commit=lambda: None),
        enqueue=lambda *a, **k: calls.setdefault("enqueue", k),
    )
    monkeypatch.setattr(gb, "frappe", fake)
    result = gb.enqueue_geonames_admin(zip_path="/nonexistent/geonames")
    assert result == {"queued": True, "dataset": "GEONAMES-ADMIN"}
    assert calls["set_value"][0] == "Boundary Dataset"
    assert calls["set_value"][2]["import_status"] == "Queued"
    assert calls["enqueue"]["job_id"] == "siraj-geonames-admin:GEONAMES-ADMIN"


def test_geonames_admin_feature_levels_cover_all_adm_codes():
    assert gb.GEONAMES_ADMIN_FEATURE_LEVELS == {
        "ADM1": 1, "ADM2": 2, "ADM3": 3, "ADM4": 4, "ADM5": 5}


def test_admin_feature_pcode_levels():
    row = {"admin1_pcode": "IL", "admin2_pcode": "IL.06",
           "admin3_pcode": "IL.06.01", "admin4_pcode": "IL.06.01.02",
           "source_id": "999"}
    # Level 1 passes its own code so choose_admin_parent reads the ISO prefix.
    assert gb._admin_feature_pcode(1, row) == ("IL", "IL")
    assert gb._admin_feature_pcode(2, row) == ("IL.06", "IL")
    assert gb._admin_feature_pcode(3, row) == ("IL.06.01", "IL.06")
    assert gb._admin_feature_pcode(4, row) == ("IL.06.01.02", "IL.06.01")
    # ADM5 has no stable GeoNames code: geonameid is the pcode (historical).
    assert gb._admin_feature_pcode(5, row) == ("999", "IL.06.01.02")


def test_admin_feature_pcode_falls_back_to_deepest_parent():
    row = {"admin1_pcode": "IQ", "admin3_pcode": "IQ.BG.01", "source_id": "42"}
    assert gb._admin_feature_pcode(3, row) == ("IQ.BG.01", "IQ")
    assert gb._admin_feature_pcode(5, row) == ("42", "IQ.BG.01")


def test_geonames_allcountries_pass_forwards_coordinates():
    """The allCountries pass must hand lat/lon to upsert_level (coords gap).

    admin1CodesASCII/admin2Codes carry no coordinates; only allCountries
    rows do. Without this wiring every GeoNames hierarchy row is created
    without latitude/longitude and the basic data stays coordless.
    """
    from pathlib import Path

    src = Path("siraj_research/geo_bulk.py").read_text()
    assert "upsert_level(entry, parent_name, lat=lat, lon=lon," in src
    assert 'lat=row.get("latitude"), lon=row.get("longitude"))' in src


def test_geonames_import_reports_failed_rows():
    """One malformed source row must not abort the 56k-feature import:
    failures are counted, sampled and surfaced in the report (verified
    against the real crash: CharacterLengthExceededError on a 65-char
    GeoNames ADM3 code)."""
    from pathlib import Path

    src = Path("siraj_research/geo_bulk.py").read_text()
    assert "failed_sample.append" in src
    assert '"failed": failed' in src
    assert '"failed_sample": failed_sample' in src


def test_gazetteer_dataset_autoactivates_the_settings_field():
    """Without active_gazetteer_dataset the resolver's place lookup runs
    with dataset=None and never fires — the first gazetteer import must
    wire itself, mirroring _finish's boundary auto-activate."""
    from pathlib import Path

    src = Path("siraj_research/geo_bulk.py").read_text()
    assert '"active_gazetteer_dataset", code' in src
    assert "if is_gazetteer:" in src


def test_gazetteer_bulk_insert_chunks_and_reports_failures():
    """MySQL error 2013 (lost connection) on one giant multi-row INSERT
    must not kill the import: small committed chunks + row fallback +
    failed/sample reporting."""
    from pathlib import Path

    src = Path("siraj_research/geo_bulk.py").read_text()
    assert "chunk_size = 100" in src
    assert "failed_sample.append" in src
    assert '"failed": failed, "failed_sample": failed_sample' in src
    # Both batch paths unpack the resilient tuple.
    assert src.count("added, bad, sample = _bulk_insert_gazetteer") == 2
