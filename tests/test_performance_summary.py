"""Aggregation tests with a stub probe: no Frappe, site or SQL."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / "siraj_research/setup/performance_summary.py"


class PerformanceSummaryTests(unittest.TestCase):
	def setUp(self):
		stub = types.ModuleType("siraj_research.setup.link_query_probe")
		self.calls = []

		def measure(user, workload, repetitions, parent, confirm):
			self.calls.append((user, workload, repetitions, parent, confirm))
			return {
				"samples": [
					{"elapsed_ms": x, "sql_calls": x, "sql_wall_ms": x / 2, "result_rows": 10}
					for x in (1, 3, 5)
				]
			}

		stub.measure = measure
		spec = importlib.util.spec_from_file_location("performance_summary_fixture", PATH)
		self.m = importlib.util.module_from_spec(spec)
		with patch.dict(sys.modules, {"siraj_research.setup.link_query_probe": stub}):
			spec.loader.exec_module(self.m)

	def test_percentiles_counts_and_redaction(self):
		r = self.m.run(
			"secret-user", "place_tree", "secret-parent", batches=2, confirm="ISOLATED-TEST-APPROVED"
		)
		self.assertEqual(r["sample_count"], 6)
		self.assertEqual(r["elapsed_ms"], {"median": 3.0, "p95_nearest_rank": 5})
		self.assertEqual(r["sql_calls"], {"min": 1, "max": 5})
		self.assertEqual(r["result_rows"], {"min": 10, "max": 10})
		self.assertNotIn("secret", str(r))
		self.assertEqual(len(self.calls), 2)

	def test_missing_confirmation_and_invalid_batch_reject_before_access(self):
		for kwargs in (
			{},
			{"confirm": "ISOLATED-TEST-APPROVED", "batches": 0},
			{"confirm": "ISOLATED-TEST-APPROVED", "batches": 4},
			{"confirm": "ISOLATED-TEST-APPROVED", "batches": True},
		):
			with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
				self.m.run("user", "place_tree", "parent", **kwargs)
		self.assertEqual(self.calls, [])


if __name__ == "__main__":
	unittest.main()
