"""Local-pack HTTP security with stubs; not a real Frappe integration test."""

import importlib.util
import json
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PNG = b"\x89PNG\r\n\x1a\n" + b"data"


class FakeResponse:
	def __init__(self, data=None, status=200, content_type=None, headers=None):
		self.data, self.status_code, self.content_type, self.headers = (
			data,
			status,
			content_type,
			headers or {},
		)


class LocalMapsTest(unittest.TestCase):
	def setUp(self):
		self.tmp = tempfile.TemporaryDirectory()
		self.addCleanup(self.tmp.cleanup)
		self.root = Path(self.tmp.name)
		self.private = self.root / "private"
		self.private.mkdir()
		self.packdir = self.private / "siraj_maps"
		self.packdir.mkdir()
		self.f = types.ModuleType("frappe")
		self.f.session = types.SimpleNamespace(user="reader")
		self.f.conf = {}
		self.f.PermissionError = PermissionError
		self.f.ValidationError = ValueError
		self.f.whitelist = lambda **kw: lambda fn: fn
		self.f.has_permission = lambda *args: True
		self.f.get_site_path = lambda name: str(self.private)
		self.f.throw = lambda message, error: (_ for _ in ()).throw(error(message))
		rate = types.ModuleType("frappe.rate_limiter")
		rate.rate_limit = lambda **kwargs: lambda fn: fn
		response = types.ModuleType("werkzeug.wrappers")
		response.Response = FakeResponse
		spec = importlib.util.spec_from_file_location(
			"local_maps_test", ROOT / "siraj_research/local_maps.py"
		)
		self.module = importlib.util.module_from_spec(spec)
		with patch.dict(
			sys.modules,
			{
				"frappe": self.f,
				"frappe.rate_limiter": rate,
				"werkzeug": types.ModuleType("werkzeug"),
				"werkzeug.wrappers": response,
			},
		):
			spec.loader.exec_module(self.module)

	def create_pack(self, name="standard.mbtiles", indexed=True):
		path = self.packdir / name
		with sqlite3.connect(path) as db:
			db.execute("CREATE TABLE metadata (name TEXT, value TEXT)")
			db.executemany(
				"INSERT INTO metadata VALUES (?,?)",
				[("name", "<example>"), ("format", "png"), ("attribution", "Offline source")],
			)
			db.execute(
				"CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB)"
			)
			if indexed:
				db.execute("CREATE UNIQUE INDEX tile_index ON tiles (zoom_level,tile_column,tile_row)")
			db.execute("INSERT INTO tiles VALUES (1,0,1,?)", (PNG,))
		return path

	def test_authorization_and_no_path_traversal(self):
		self.create_pack()
		self.f.session.user = "Guest"
		with self.assertRaises(PermissionError):
			self.module.available_packs()
		with self.assertRaises(PermissionError):
			self.module.tile("standard", "1", "0", "0")
		self.f.session.user = "user"
		self.f.has_permission = lambda *args: False
		with self.assertRaises(PermissionError):
			self.module.available_packs()
		self.f.has_permission = lambda *args: True
		with self.assertRaises(ValueError):
			self.module.tile("../standard", "1", "0", "0")
		with self.assertRaises(ValueError):
			self.module.tile("standard", "1", "-1", "0")
		self.assertEqual(self.module.tile("standard", "1", "1", "0").status_code, 404)

	def test_indexed_pack_and_safe_tile_response(self):
		self.create_pack()
		reply = self.module.available_packs()
		self.assertEqual(reply.headers["Cache-Control"], "private, no-store")
		metadata = json.loads(reply.data)["message"]
		self.assertEqual(
			metadata,
			[
				{
					"kind": "standard",
					"name": "<example>",
					"attribution": "Offline source",
					"format": "png",
					"minzoom": 1,
					"maxzoom": 1,
					"download_allowed": False,
				}
			],
		)
		self.f.conf["siraj_offline_map_downloads"] = ["standard"]
		self.assertTrue(json.loads(self.module.available_packs().data)["message"][0]["download_allowed"])
		self.f.conf["siraj_offline_map_downloads"] = "standard"
		self.assertFalse(json.loads(self.module.available_packs().data)["message"][0]["download_allowed"])
		response = self.module.tile("standard", "1", "0", "0")
		self.assertEqual(response.data, PNG)
		self.assertEqual(response.content_type, "image/png")
		self.assertEqual(response.headers["Cache-Control"], "private, no-store")
		self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")

	def test_symlink_and_unindexed_pack_are_not_served(self):
		outside = self.root / "outside.mbtiles"
		outside.write_bytes(b"not an image")
		(self.packdir / "aerial.mbtiles").symlink_to(outside)
		self.create_pack(indexed=False)
		self.assertEqual(
			json.loads(self.module.available_packs().data)["message"],
			[{"kind": "standard", "unavailable": True}],
		)
		with self.assertRaises(ValueError):
			self.module.tile("standard", "1", "0", "0")
		self.assertEqual(self.module.tile("aerial", "1", "0", "0").status_code, 404)


if __name__ == "__main__":
	unittest.main()
