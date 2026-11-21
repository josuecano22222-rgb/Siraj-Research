"""export_offline_package must never clobber the served package (no bench)."""

import sys
import types
from types import SimpleNamespace

import pytest


@pytest.fixture()
def geo_package(monkeypatch):
    # api.geo_package imports frappe unconditionally and decorates
    # whitelisted endpoints at module level.
    stub = types.ModuleType("frappe")
    stub.whitelist = lambda *a, **k: (lambda fn: fn)
    monkeypatch.setitem(sys.modules, "frappe", stub)
    from siraj_research.api import geo_package as mod

    return mod


def _activate(monkeypatch, mod, dataset="OSM-IL-PS"):
    monkeypatch.setattr(
        mod, "_settings",
        lambda: {"active_boundary": dataset, "active_gazetteer": None})


def _frappe_with_status(monkeypatch, mod, status):
    monkeypatch.setattr(mod, "frappe", SimpleNamespace(
        db=SimpleNamespace(get_value=lambda *a, **k: status)))


def test_export_refuses_while_import_queued(monkeypatch, geo_package, tmp_path):
    _activate(monkeypatch, geo_package)
    _frappe_with_status(monkeypatch, geo_package, "Queued")
    target = tmp_path / "pkg.json"
    out = geo_package.export_offline_package(str(target))
    assert out["written"] is False
    assert out["skipped"] == "import_in_progress"
    assert not target.exists()


def test_export_refuses_empty_polygon_package(monkeypatch, geo_package, tmp_path):
    _activate(monkeypatch, geo_package)
    _frappe_with_status(monkeypatch, geo_package, "Complete")
    monkeypatch.setattr(
        geo_package, "build_package",
        lambda ds, gz=None: {"dataset": ds, "version": 3, "places": [],
                             "polygons": [], "etag": f"{ds}:3"})
    target = tmp_path / "pkg.json"
    out = geo_package.export_offline_package(str(target))
    assert out["written"] is False
    assert out["skipped"] == "empty_package"
    assert not target.exists()


def test_export_writes_non_empty_package(monkeypatch, geo_package, tmp_path):
    _activate(monkeypatch, geo_package)
    _frappe_with_status(monkeypatch, geo_package, "Complete")
    monkeypatch.setattr(
        geo_package, "build_package",
        lambda ds, gz=None: {"dataset": ds, "version": 4, "places": [],
                             "polygons": [[0, "OSM-X", "", "n", None, [], None]],
                             "etag": f"{ds}:4"})
    target = tmp_path / "pkg.json"
    out = geo_package.export_offline_package(str(target))
    assert out["written"] is True
    assert out["polygons"] == 1
    assert target.exists()
