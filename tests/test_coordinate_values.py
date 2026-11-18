"""Coordinate parsing and schema checks without a live Frappe database."""

import json
import unittest
from pathlib import Path

from test_visualization import FakeFrappe, load_visualization

ROOT = Path(__file__).resolve().parents[1]


class CoordinateValueTest(unittest.TestCase):
	def test_text_values_in_explorer_are_normalized_only_for_rendering(self):
		values = [
			{"name": "ar", "display_name": "Arabic", "latitude": "٣٣٫١٢٣٤٥٦٧٨٩٠١٢٣٤٥", "longitude": "۴۴٫۲۵"},
			{"name": "zero", "latitude": "0", "longitude": "20"},
			{"name": "ambiguous", "latitude": "0", "longitude": "0"},
			{"name": "out-of-range", "latitude": "90.00000000000000000001", "longitude": "20"},
			{"name": "missing", "latitude": "", "longitude": "20"},
		]
		api = FakeFrappe({"Person": values})
		points = load_visualization(api).geographic_data()["points"]
		self.assertEqual({p["name"] for p in points}, {"ar", "zero"})
		point = next(p for p in points if p["name"] == "ar")
		self.assertAlmostEqual(point["latitude"], 33.123456789012345)
		self.assertEqual(point["longitude"], 44.25)
		self.assertEqual(values[0]["latitude"], "٣٣٫١٢٣٤٥٦٧٨٩٠١٢٣٤٥")

	def test_no_invented_precision_for_legacy_numeric_values(self):
		viz = load_visualization(FakeFrappe())
		self.assertEqual(viz._coordinate(1e-7, 90), 1e-7)
		self.assertIsNone(viz._coordinate("1e-7", 90))
		self.assertIsNone(viz._coordinate("nan", 90))
		self.assertIsNone(viz._coordinate("180.0000000000000001", 180))
		self.assertEqual(viz._coordinate("180.0000", 180), 180)


if __name__ == "__main__":
	unittest.main()
