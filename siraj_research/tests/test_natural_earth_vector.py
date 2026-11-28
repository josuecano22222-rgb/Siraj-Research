# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
"""Tests for the Natural Earth Vector integration.

Covers the catalog, the bundled 1:110m tier, pack manifest handling,
scale-tier selection, layer serving and hermetic local-mirror provisioning
(with the site paths mocked to a temp directory, so no real pack is
written during the test run).
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
import unittest
from unittest import mock

import frappe

from siraj_research import natural_earth_vector as nev
from siraj_research.natural_earth_catalog import (
    LAYERS,
    SCALES,
    get_layer,
    layers_for_scale,
    scale_for_zoom,
)


class TestNaturalEarthCatalog(unittest.TestCase):
    def test_full_catalog_size(self):
        assert len(LAYERS) == 206, "catalog must cover the full Natural Earth GeoJSON set"

    def test_scale_counts(self):
        assert len(layers_for_scale("110m")) == 32
        assert len(layers_for_scale("50m")) == 45
        assert len(layers_for_scale("10m")) == 129

    def test_scales_declared(self):
        assert set(SCALES) == {"10m", "50m", "110m"}

    def test_every_layer_has_metadata(self):
        for name, meta in LAYERS.items():
            assert name.startswith("ne_"), name
            assert meta["scale"] in SCALES, name
            assert meta["category"] in ("cultural", "physical"), name
            assert meta["description"], name

    def test_get_layer(self):
        assert get_layer("ne_110m_land.geojson")["scale"] == "110m"
        assert get_layer("ne_does_not_exist.geojson") is None

    def test_scale_for_zoom_tiers(self):
        assert scale_for_zoom(0) == "110m"
        assert scale_for_zoom(3.99) == "110m"
        assert scale_for_zoom(4) == "50m"
        assert scale_for_zoom(6.99) == "50m"
        assert scale_for_zoom(7) == "10m"
        assert scale_for_zoom(20) == "10m"


class TestBundledTier(unittest.TestCase):
    def test_bundled_manifest_complete(self):
        manifest = nev.bundled_manifest()
        assert manifest["kind"] == "bundle"
        assert manifest["scale"] == "110m"
        layers = manifest["layers"]
        assert len(layers) == 32, "bundled tier must ship all 1:110m layers"
        for name, meta in layers.items():
            assert get_layer(name), f"bundled layer {name} not in catalog"
            assert meta["sha256"] and meta["bytes"] > 0
        assert manifest["stats"]["file_count"] == len(layers)

    def test_read_bundled_layer(self):
        text = nev.read_layer("ne_110m_land.geojson")
        assert text is not None
        geojson = json.loads(text)
        assert geojson["type"] == "FeatureCollection"
        assert len(geojson["features"]) > 0

    def test_unknown_layer_raises(self):
        try:
            nev.read_layer("ne_99m_not_a_layer.geojson")
            raise AssertionError("unknown layer must raise")
        except nev.NaturalEarthPackError:
            pass

    def test_layer_etag(self):
        etag = nev.layer_etag("ne_110m_land.geojson")
        assert etag and etag.startswith("ne-ne_110m_land.geojson:")

    def test_available_layers_110m(self):
        layers = nev.available_layers("110m")
        assert len(layers) == 32
        assert all(l["source"] == "bundle" for l in layers)


class TestManifestValidation(unittest.TestCase):
    def _base(self, **over):
        manifest = {
            "name": "natural_earth_vector",
            "scales": ["110m"],
            "source": {"repo": "r", "ref": "m", "data_version": "v", "license": "public domain"},
            "layers": {},
            "stats": {"file_count": 0, "total_bytes": 0},
        }
        manifest.update(over)
        return manifest

    def test_valid(self):
        m = self._base(layers={"ne_110m_land.geojson": {"sha256": "ab", "bytes": 1}},
                       stats={"file_count": 1, "total_bytes": 1})
        assert nev.validate_manifest(m) is m

    def test_missing_key(self):
        m = self._base()
        del m["layers"]
        try:
            nev.validate_manifest(m)
            raise AssertionError()
        except nev.NaturalEarthPackError:
            pass

    def test_bad_scale(self):
        try:
            nev.validate_manifest(self._base(scales=["99m"]))
            raise AssertionError()
        except nev.NaturalEarthPackError:
            pass

    def test_unknown_layer(self):
        try:
            nev.validate_manifest(self._base(layers={"ne_bad.geojson": {"sha256": "x"}},
                                             stats={"file_count": 1, "total_bytes": 0}))
            raise AssertionError()
        except nev.NaturalEarthPackError:
            pass

    def test_stats_mismatch(self):
        try:
            nev.validate_manifest(self._base(
                layers={"ne_110m_land.geojson": {"sha256": "ab", "bytes": 1}},
                stats={"file_count": 5, "total_bytes": 1}))
            raise AssertionError()
        except nev.NaturalEarthPackError:
            pass


class TestLocalMirrorProvisioning(unittest.TestCase):
    """Provisioning into a temp pack dir with mocked site paths."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ne-pack-test-"))
        self.site = self.tmp / "site"
        self.mirror = self.tmp / "mirror"
        (self.mirror / "geojson").mkdir(parents=True)
        self.pack = self.site / "private" / "natural_earth_vector"
        self._patches = [
            mock.patch.object(nev, "_site_root", return_value=self.site),
            mock.patch.object(nev, "pack_root", return_value=self.pack),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _copy_bundled(self, *names):
        for name in names:
            src = nev.bundled_root() / name
            assert src.is_file(), f"bundled source missing: {name}"
            shutil.copy(src, self.mirror / "geojson" / name)

    def test_provision_local_mirror(self):
        self._copy_bundled("ne_110m_land.geojson", "ne_110m_lakes.geojson")
        manifest = nev.provision_pack(
            ["110m"],
            layers=["ne_110m_land.geojson", "ne_110m_lakes.geojson"],
            source="local_mirror",
            mirror_path=str(self.mirror),
        )
        assert manifest["stats"]["file_count"] == 2
        assert (self.pack / "ne_110m_land.geojson").is_file()
        assert (self.pack / "manifest.json").is_file()

        # The pack is readable and its manifest validates.
        loaded = nev.read_manifest()
        assert loaded["stats"]["file_count"] == 2
        text = nev.read_layer("ne_110m_land.geojson")
        assert text and json.loads(text)["type"] == "FeatureCollection"

        # Offline ZIP archive compiled from the pack.
        assert nev.zip_path().is_file()

    def test_provision_skips_missing_layers(self):
        self._copy_bundled("ne_110m_land.geojson")
        manifest = nev.provision_pack(
            ["110m"],
            layers=["ne_110m_land.geojson", "ne_110m_lakes.geojson"],
            source="local_mirror",
            mirror_path=str(self.mirror),
        )
        assert manifest["stats"]["file_count"] == 1
        assert "ne_110m_lakes.geojson" in manifest["missing"]

    def test_provision_rejects_mirror_outside_site(self):
        outside = self.tmp / "elsewhere"
        outside.mkdir()
        try:
            nev.provision_pack(
                ["110m"],
                layers=["ne_110m_land.geojson"],
                source="local_mirror",
                mirror_path=str(outside),
            )
            raise AssertionError("mirror outside the site must be rejected")
        except nev.NaturalEarthPackError:
            pass

    def test_provision_empty_result_raises(self):
        try:
            nev.provision_pack(
                ["110m"],
                layers=["ne_110m_land.geojson"],
                source="local_mirror",
                mirror_path=str(self.mirror),
            )
            raise AssertionError("no provisionable layers must raise")
        except nev.NaturalEarthPackError:
            pass


class TestScaleFallback(unittest.TestCase):
    def test_falls_back_to_available_tier(self):
        with mock.patch.object(nev, "available_scales", return_value=["110m"]):
            assert nev.scale_for_zoom_with_fallback(8) == "110m"
        with mock.patch.object(nev, "available_scales",
                               return_value=["110m", "50m"]):
            assert nev.scale_for_zoom_with_fallback(8) == "50m"
            assert nev.scale_for_zoom_with_fallback(2) == "110m"


class TestApiEndpoints(unittest.TestCase):
    def test_layer_endpoint_serves_bundled(self):
        from siraj_research.api.natural_earth_vector import layer
        resp = layer("ne_110m_land.geojson")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        geojson = json.loads(body)
        assert geojson["type"] == "FeatureCollection"

    def test_layer_endpoint_404_unknown(self):
        from siraj_research.api.natural_earth_vector import layer
        resp = layer("ne_99m_missing.geojson")
        assert resp.status_code == 404

    def test_catalog_endpoint(self):
        from siraj_research.api.natural_earth_vector import catalog
        data = catalog()
        assert data["layer_count"] == 206
        assert "110m" in data["available_scales"]

    def test_index_endpoint(self):
        from siraj_research.api.natural_earth_vector import index
        data = index("110m")
        assert data["count"] == 32

    def test_provision_endpoint_requires_admin(self):
        from siraj_research.api.natural_earth_vector import provision
        try:
            with mock.patch.object(frappe.session, "user", "Guest"):
                provision()
            raise AssertionError("Guest must be rejected")
        except frappe.PermissionError:
            pass


class TestDocTypeController(unittest.TestCase):
    def test_get_catalog_layers(self):
        from siraj_research.natural_earth_vector_pack.natural_earth_vector_pack import (
            get_catalog_layers,
        )
        layers = get_catalog_layers("110m")
        assert len(layers) == 32
        assert all(l["scale"] == "110m" for l in layers)

    def test_doctype_registered(self):
        if not frappe.db.exists("DocType", "Natural Earth Vector Pack"):
            return  # not migrated on this site; nothing to assert
        doc = frappe.get_doc({
            "doctype": "Natural Earth Vector Pack",
            "source": "local_mirror",
            "scale_110m": 1,
        })
        doc.insert(ignore_permissions=True)
        self.addCleanup(lambda: frappe.delete_doc(
            "Natural Earth Vector Pack", doc.name, force=1, ignore_permissions=True
        ) if frappe.db.exists("Natural Earth Vector Pack", doc.name) else None)
        assert doc.name
