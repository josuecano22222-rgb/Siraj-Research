"""Synthetic metadata; no site, file content or real URLs."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / "siraj_research/setup/imagery_inventory.py"


class ImageryInventoryTest(unittest.TestCase):
	def setUp(self):
		f = types.ModuleType("frappe")
		f.session = types.SimpleNamespace(user="Administrator")
		f.db = types.SimpleNamespace(exists=lambda dt, name: name in ("Person", "Place"))
		f.get_meta = lambda dt: types.SimpleNamespace(get_field=lambda name: dt == "Person")
		self.rows = {
			"File": [
				{"name": "a", "file_url": "https://secret.test/x.png?token=secret", "is_private": 1},
				{"name": "b", "file_url": "/files/private.jpg", "is_private": 0},
				{"name": "c", "file_url": None, "is_private": None},
			],
			"Person": [
				{"name": "x", "image_url": "https://secret.test/path?secret=1"},
				{"name": "y", "image_url": ""},
			],
		}
		self.calls = []

		def get_all(dt, fields, filters, order_by, limit_page_length):
			self.calls.append(dt)
			after = filters.get("name", [">", ""])[1]
			return [{k: r[k] for k in fields} for r in self.rows[dt] if r["name"] > after][:limit_page_length]

		f.get_all = get_all
		self.f = f
		spec = importlib.util.spec_from_file_location("imagery_inventory_test", PATH)
		self.m = importlib.util.module_from_spec(spec)
		with patch.dict(sys.modules, {"frappe": f}):
			spec.loader.exec_module(self.m)

	def test_aggregates_without_urls_or_names(self):
		result = self.m.inspect("ISOLATED-TEST-APPROVED")
		self.assertEqual(result["file_counts"]["records"], 3)
		self.assertEqual(result["file_counts"]["extension_png"], 1)
		self.assertEqual(result["file_counts"]["private"], 1)
		self.assertEqual(result["file_counts"]["privacy_unknown"], 1)
		self.assertEqual(result["image_url_fields"]["Person"]["counts"]["url_external_http"], 1)
		self.assertEqual(result["image_url_fields"]["Place"]["status"], "field_missing")
		self.assertNotIn("secret", str(result))
		self.assertNotIn("private.jpg", str(result))

	def test_authorization_and_confirmation_before_any_read(self):
		with self.assertRaises(ValueError):
			self.m.inspect()
		self.f.session.user = "reader"
		with self.assertRaises(PermissionError):
			self.m.inspect("ISOLATED-TEST-APPROVED")
		self.assertEqual(self.calls, [])

	def test_bounded_and_unstable_paging(self):
		self.m.LIMIT = 1
		result = self.m.inspect("ISOLATED-TEST-APPROVED")
		self.assertTrue(result["file_truncated"])
		self.assertTrue(result["image_url_fields"]["Person"]["truncated"])
		self.m.LIMIT = 5
		self.rows["File"] = [
			{"name": "b", "file_url": "", "is_private": 0},
			{"name": "a", "file_url": "", "is_private": 0},
		]
		with self.assertRaises(ValueError):
			self.m.inspect("ISOLATED-TEST-APPROVED")

	def test_malformed_urls_never_escape_as_values(self):
		self.assertEqual(self.m._bucket("http://[invalid"), "invalid")
		self.assertEqual(self.m._bucket("data:image/png;base64,secret"), "other")
		self.assertEqual(self.m._image_type("https://example.test/p.PNG?x=1"), "png")


if __name__ == "__main__":
	unittest.main()
