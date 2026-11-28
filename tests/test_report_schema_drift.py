"""Unit test for the read-only ``report_schema_drift`` diagnostic (P0b).

Stubs ``frappe`` in ``sys.modules`` so this test runs in the pure-Python
gate (no bench / no real MariaDB). It exercises the drift detection logic
only: Custom Fields not in the app JSON, required (mandatory/reqd) fields
not in the app JSON, and autoname values that differ from the JSON.

The diagnostic itself is read-only — this test also asserts that no write
method on ``frappe.db`` is invoked.
"""

from __future__ import annotations

import sys
import types
import unittest
from unittest import mock

_STUB_KEYS = ("frappe", "frappe.db", "frappe.modules", "frappe.modules.import_file")


class _FakeField(dict):
	"""A DocField row.

	Frappe's ``meta.fields`` items are ``frappe._dict`` rows: dict-style
	access (``.get``, ``[]``) is the canonical surface, so the stub is a
	plain dict to faithfully model that contract (this is what makes the
	test catch a ``getattr``-based impl, which fails on plain dicts).
	"""

	def __init__(self, fieldname, fieldtype="Data", mandatory=0, reqd=0):
		super().__init__(
			fieldname=fieldname,
			fieldtype=fieldtype,
			mandatory=mandatory,
			reqd=reqd,
		)


class _FakeMeta:
	"""Frappe v15 ``Meta``: fields are exposed via the ``.fields`` attribute
	(a list of dict-style rows), NOT via a ``get_fields()`` method. The
	diagnostic must read ``meta.fields`` — a ``get_fields()`` call crashes on
	the live site with ``AttributeError: 'Meta' object has no attribute
	'get_fields'``."""

	def __init__(self, autoname, fields):
		self.autoname = autoname
		self.fields = list(fields)


class TestReportSchemaDrift(unittest.TestCase):
	def setUp(self):
		self._saved = {k: sys.modules.get(k) for k in _STUB_KEYS}
		frappe = types.ModuleType("frappe")
		db = types.ModuleType("frappe.db")
		modules = types.ModuleType("frappe.modules")
		import_file = types.ModuleType("frappe.modules.import_file")
		import_file.import_file_by_path = mock.MagicMock()
		modules.import_file = import_file
		frappe.modules = modules
		frappe.db = db
		self.frappe = frappe
		self.db = db
		for key, value in (
			("frappe", frappe),
			("frappe.db", db),
			("frappe.modules", modules),
			("frappe.modules.import_file", import_file),
		):
			sys.modules[key] = value
		# Import install only after the stub frappe is in place (install.py
		# does a top-level ``import frappe``).
		from siraj_research.setup import install as install_mod

		self.install = install_mod

	def tearDown(self):
		for key, value in self._saved.items():
			if value is None:
				sys.modules.pop(key, None)
			else:
				sys.modules[key] = value

	@staticmethod
	def _json(autoname, reqd_fields):
		"""Build a minimal DocType JSON dict: autoname + required fields."""
		return {
			"autoname": autoname,
			"fields": [{"fieldname": name, "reqd": reqd} for name, reqd in reqd_fields],
		}

	def _patch(self, doctype, json_meta, live_meta, cf_rows):
		# Patch the exact objects report_schema_drift reads: the module-level
		# _doctype_json on install, and get_meta / db.get_all on the frappe
		# module bound inside install (self.install.frappe), not a separate
		# reference, so the patch is guaranteed visible to the function.
		self.install._doctype_json = mock.MagicMock(
			side_effect=lambda dt: json_meta if dt == doctype else None
		)
		self.install.frappe.get_meta = mock.MagicMock(
			side_effect=lambda dt: live_meta if dt == doctype else None
		)
		self.install.frappe.db.get_all = mock.MagicMock(
			side_effect=lambda *a, **k: cf_rows
			if (k.get("dt") == doctype or (a and a[0] == "Custom Field"))
			else []
		)

	def test_custom_field_not_in_json_is_reported(self):
		# governorate_name is a site-only Custom Field, not in the app JSON.
		json_meta = self._json("field:code", [("code", 1), ("label_ar", 1), ("country", 1)])
		live_meta = _FakeMeta(
			"field:name",
			[
				_FakeField("code", reqd=1),
				_FakeField("label_ar", reqd=1),
				_FakeField("country", reqd=1),
				_FakeField("governorate_name", mandatory=1),
			],
		)
		cf_rows = [
			{"fieldname": "governorate_name", "fieldtype": "Data", "mandatory": 1, "reqd": 0},
			{"fieldname": "code", "fieldtype": "Data", "mandatory": 0, "reqd": 1},
		]
		self._patch("Governorate", json_meta, live_meta, cf_rows)

		findings = self.install.report_schema_drift(doctypes=["Governorate"])
		gov = findings["Governorate"]
		self.assertEqual(gov["custom_fields"], ["governorate_name"])
		# governorate_name is mandatory and not in the JSON -> required drift too.
		self.assertEqual(gov["required_not_in_json"], ["governorate_name"])
		# autoname differs: live field:name vs JSON field:code.
		self.assertTrue(gov["autoname_drift"])
		self.assertEqual(gov["json_autoname"], "field:code")
		self.assertEqual(gov["live_autoname"], "field:name")

	def test_custom_field_present_in_json_is_not_flagged(self):
		json_meta = self._json("field:code", [("code", 1), ("governorate_name", 1)])
		live_meta = _FakeMeta(
			"field:code",
			[_FakeField("code", reqd=1), _FakeField("governorate_name", reqd=1)],
		)
		cf_rows = [
			{"fieldname": "governorate_name", "fieldtype": "Data", "mandatory": 0, "reqd": 1},
			{"fieldname": "code", "fieldtype": "Data", "mandatory": 0, "reqd": 1},
		]
		self._patch("Governorate", json_meta, live_meta, cf_rows)

		findings = self.install.report_schema_drift(doctypes=["Governorate"])
		gov = findings["Governorate"]
		self.assertEqual(gov["custom_fields"], [])
		self.assertEqual(gov["required_not_in_json"], [])
		self.assertFalse(gov["autoname_drift"])

	def test_clean_doctype_has_no_drift(self):
		json_meta = self._json("field:name", [("name", 1), ("full_name", 0)])
		live_meta = _FakeMeta(
			"field:name",
			[_FakeField("name", reqd=1), _FakeField("full_name")],
		)
		self._patch("Person", json_meta, live_meta, [])

		findings = self.install.report_schema_drift(doctypes=["Person"])
		person = findings["Person"]
		self.assertEqual(person["custom_fields"], [])
		self.assertEqual(person["required_not_in_json"], [])
		self.assertFalse(person["autoname_drift"])

	def test_diagnostic_is_read_only(self):
		# No write method on frappe.db may be called.
		json_meta = self._json("field:code", [("code", 1)])
		live_meta = _FakeMeta("field:code", [_FakeField("code", reqd=1)])
		self._patch("Governorate", json_meta, live_meta, [])
		for method in (
			"commit", "set_value", "sql", "delete", "update", "truncate",
			"set_single_value", "sql_set",
		):
			setattr(self.db, method, mock.MagicMock(name=method))

		self.install.report_schema_drift(doctypes=["Governorate"])

		for method in ("commit", "set_value", "sql", "delete", "update", "truncate", "set_single_value", "sql_set"):
			getattr(self.db, method).assert_not_called()


if __name__ == "__main__":
	unittest.main()
