"""Read-only coordinate inventory: fake Frappe plus pure value classification."""

import importlib.util
import sys
import types
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(frappe):
	spec = importlib.util.spec_from_file_location(
		"coordinate_audit_test", ROOT / "siraj_research/setup/coordinate_audit.py"
	)
	module = importlib.util.module_from_spec(spec)
	with patch.dict(sys.modules, {"frappe": frappe}):
		spec.loader.exec_module(module)
	return module


class CoordinateAuditTest(unittest.TestCase):
	def test_categories_preserve_partial_invalid_and_ambiguous(self):
		audit = load(types.SimpleNamespace())
		rows = [
			{"latitude": None, "longitude": ""},
			{"latitude": 0.0, "longitude": 0},
			{"latitude": "٣٣٫٢", "longitude": "۴۴.۵"},
			{"latitude": "99", "longitude": "20"},
			{"latitude": None, "longitude": "bad"},
			{"latitude": Decimal("1E-7"), "longitude": "-180"},
			{"latitude": True, "longitude": "NaN"},
		]
		self.assertEqual(
			audit.summarize(rows),
			{
				"rows": 7,
				"both_blank": 1,
				"incomplete": 1,
				"invalid_latitude": 2,
				"invalid_longitude": 2,
				"complete_valid": 3,
				"ambiguous_zero_pair": 1,
			},
		)

	def test_read_only_pagination_and_fixed_bound_schema_query(self):
		calls = []

		class DB:
			db_type = "mariadb"

			def exists(self, doctype, name):
				return name == "Person"

			def sql(self, query, params, as_dict):
				calls.append((query, params))
				return [
					{
						"column_name": field,
						"data_type": "double",
						"numeric_precision": 22,
						"numeric_scale": 6,
						"character_maximum_length": None,
						"is_nullable": "YES",
						"column_default": "0",
					}
					for field in ("latitude", "longitude")
				]

		field = types.SimpleNamespace(fieldtype="Float", precision="6", length=0)
		all_rows = [{"name": str(i).zfill(4), "latitude": i, "longitude": 1} for i in range(250)]

		def get_all(doctype, fields, filters, order_by, limit_page_length):
			assert doctype == "Person" and fields == ["name", "latitude", "longitude"]
			assert order_by == "name asc" and limit_page_length == 200
			start = filters.get("name", [">", ""])[1]
			return [row for row in all_rows if row["name"] > start][:limit_page_length]

		fake = types.SimpleNamespace(
			db=DB(), get_meta=lambda dt: types.SimpleNamespace(get_field=lambda n: field), get_all=get_all
		)
		report = load(fake).inspect_coordinate_migration()
		p = report["doctypes"]["Person"]
		self.assertEqual(p["counts"]["rows"], 250)
		self.assertEqual(p["counts"]["invalid_latitude"], 159)
		self.assertEqual(p["columns"]["latitude"]["data_type"], "double")
		self.assertTrue(p["columns"]["latitude"]["has_default"])
		self.assertNotIn("0000", str(report))
		self.assertEqual(len(calls), 1)
		self.assertEqual(calls[0][1], ("tabPerson", "latitude", "longitude"))
		self.assertEqual(report["doctypes"]["Research Event"]["status"], "doctype_missing")

	def test_unknown_db_or_missing_columns_stops_before_record_scan(self):
		fake = types.SimpleNamespace(
			db=types.SimpleNamespace(db_type="unknown", exists=lambda *a: True),
			get_meta=lambda dt: types.SimpleNamespace(
				get_field=lambda n: types.SimpleNamespace(fieldtype="Float", precision="6", length=0)
			),
			get_all=lambda *a, **kw: self.fail("must not scan"),
		)
		report = load(fake).inspect_coordinate_migration()
		self.assertTrue(
			all(
				entry["status"] == "missing_fields_or_unrecognized_database"
				for entry in report["doctypes"].values()
			)
		)


if __name__ == "__main__":
	unittest.main()
