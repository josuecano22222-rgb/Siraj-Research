"""Streaming bulk-import helpers (no bench, no network)."""

import zipfile

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


def test_osm_commands_are_argv_lists_not_shell_strings():
    commands = gb.osm_commands("/data/my country.pbf", "/data/out")
    assert len(commands) == 2
    assert all(isinstance(command, list) for command in commands)
    assert commands[0][0] == "osmium"
    assert commands[1][-1].endswith("my country-boundaries.geojson")
    assert gb.prepare_osm("/data/x.pbf", "/data/out", run=False)["ran"] is False
