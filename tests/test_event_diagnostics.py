import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class EventDiagnosticsTest(unittest.TestCase):
	def test_aggregates_both_event_types_and_reports_collision(self):
		queries = []

		def has_column(doctype, field):
			if doctype == "Event":
				return field in {"subject", "starts_on", "sync_with_google_calendar"}
			if doctype == "Research Event":
				return field in {"title_ar", "event_type", "researcher_notes"}
			return field == "researcher_notes" and doctype != "Source"

		def count(doctype, filters=None):
			queries.append((doctype, filters))
			if doctype == "Research Event" and filters is None:
				return 3
			if doctype == "Event" and filters is None:
				return 0
			return 0

		meta_module = {"Event": "Desk", "Research Event": "Siraj Research"}

		def get_meta(doctype):
			fields_by_doctype = {
				"Event": {"subject", "starts_on", "sync_with_google_calendar"},
				"Research Event": {"title_ar", "event_type", "researcher_notes"},
			}
			return types.SimpleNamespace(
				module=meta_module.get(doctype),
				get_field=lambda field, _d=doctype: (
					field if field in fields_by_doctype.get(_d, set()) else None
				),
			)

		frappe = types.ModuleType("frappe")
		frappe.db = types.SimpleNamespace(
			has_column=has_column, count=count, table_exists=lambda doctype: True
		)
		frappe.get_meta = get_meta
		test_data = types.ModuleType("siraj_research.setup.test_data")
		test_data.OPERATIONAL_TYPES = ("Research Event", "Source")
		spec = importlib.util.spec_from_file_location(
			"event_diag_test", ROOT / "siraj_research/setup/event_diagnostics.py"
		)
		module = importlib.util.module_from_spec(spec)
		with patch.dict(sys.modules, {"frappe": frappe, "siraj_research.setup.test_data": test_data}):
			spec.loader.exec_module(module)
		output = module.inspect_event_collision()
		self.assertEqual(output["core_event"]["module"], "Desk")
		self.assertEqual(output["core_event"]["total"], 0)
		self.assertEqual(output["research_event"]["module"], "Siraj Research")
		self.assertEqual(output["research_event"]["total"], 3)
		self.assertFalse(output["collision_detected"])
		self.assertEqual(output["test_sample_marker_counts"], {"Research Event": 0})
		self.assertEqual(output["research_event"]["fields"]["title_ar"], {"metadata": True, "column": True})
		self.assertEqual(
			output["core_event"]["fields"]["sync_with_google_calendar"],
			{"metadata": True, "column": True},
		)
		self.assertIn("collision", output["note"])

	def test_collision_flag_true_when_core_event_is_siraj_owned(self):
		frappe = types.ModuleType("frappe")
		frappe.db = types.SimpleNamespace(
			has_column=lambda d, f: True,
			count=lambda d, filters=None: 0,
			table_exists=lambda d: True,
		)
		frappe.get_meta = lambda d: types.SimpleNamespace(module="Siraj Research", get_field=lambda f: True)
		test_data = types.ModuleType("siraj_research.setup.test_data")
		test_data.OPERATIONAL_TYPES = ()
		spec = importlib.util.spec_from_file_location(
			"event_diag_collision", ROOT / "siraj_research/setup/event_diagnostics.py"
		)
		module = importlib.util.module_from_spec(spec)
		with patch.dict(sys.modules, {"frappe": frappe, "siraj_research.setup.test_data": test_data}):
			spec.loader.exec_module(module)
		output = module.inspect_event_collision()
		self.assertTrue(output["collision_detected"])

	def test_known_reference_scan_counts_both_targets(self):
		queries = []

		def table_exists(doctype):
			return doctype not in {"Event Participants", "Server Script"}

		def has_column(doctype, field):
			return (doctype, field) != ("Property Setter", "doc_type")

		def count(doctype, filters):
			queries.append((doctype, filters))
			if (doctype, filters) == ("Relationship", {"subject_type": "Event"}):
				return 4
			if (doctype, filters) == ("Relationship", {"subject_type": "Research Event"}):
				return 2
			return 0

		frappe = types.ModuleType("frappe")
		frappe.db = types.SimpleNamespace(table_exists=table_exists, has_column=has_column, count=count)
		test_data = types.ModuleType("siraj_research.setup.test_data")
		test_data.OPERATIONAL_TYPES = ()
		spec = importlib.util.spec_from_file_location(
			"event_ref_diag_test", ROOT / "siraj_research/setup/event_diagnostics.py"
		)
		module = importlib.util.module_from_spec(spec)
		with patch.dict(sys.modules, {"frappe": frappe, "siraj_research.setup.test_data": test_data}):
			spec.loader.exec_module(module)
		result = module.inspect_known_event_references()
		rows = {(row["doctype"], row["field"], row["target"]): row["count"] for row in result["references"]}
		self.assertEqual(rows["Relationship", "subject_type", "Event"], 4)
		self.assertEqual(rows["Relationship", "subject_type", "Research Event"], 2)
		self.assertEqual(rows["Relationship", "object_type", "Event"], 0)
		self.assertIsNone(rows["Event Participants", "parenttype", None])
		self.assertIsNone(rows["Property Setter", "doc_type", None])
		self.assertIn("not an authorization", result["note"])


if __name__ == "__main__":
	unittest.main()
