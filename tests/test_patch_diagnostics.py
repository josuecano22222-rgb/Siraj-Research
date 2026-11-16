import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class PatchDiagnosticsTest(unittest.TestCase):
	def test_read_only_diagnostic_reports_real_files_and_patch_log(self):
		queries = []

		def exists(doctype, filters):
			queries.append((doctype, filters))
			return filters["patch"].endswith("set_naming_counters")

		fake = types.SimpleNamespace(db=types.SimpleNamespace(exists=exists))
		spec = importlib.util.spec_from_file_location(
			"siraj_patch_diag_test", ROOT / "siraj_research/setup/patch_diagnostics.py"
		)
		module = importlib.util.module_from_spec(spec)
		with patch.dict(sys.modules, {"frappe": fake}):
			spec.loader.exec_module(module)
		result = module.inspect_patch_log()
		self.assertEqual(len(result["patches"]), 4)
		self.assertTrue(result["patches"][0]["logged_completed"])
		self.assertTrue(all(not entry["module_present"] for entry in result["patches"]))
		self.assertEqual(len(queries), 4)
		self.assertTrue(
			all(doctype == "Patch Log" and filters["skipped"] == 0 for doctype, filters in queries)
		)
		self.assertIn("does not prove", result["note"])


if __name__ == "__main__":
	unittest.main()
