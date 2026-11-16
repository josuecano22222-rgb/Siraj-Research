import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class InventoryTest(unittest.TestCase):
	def test_counts_effective_fields_for_both_targets_and_surfaces_gaps(self):
		f = types.ModuleType("frappe")
		rows = [
			{"name": n, "issingle": n == "Single", "is_virtual": n == "Virtual"}
			for n in ("A", "Single", "Virtual", "Missing", "Broken")
		]
		f.get_all = lambda doctype, **kw: rows

		def meta(name):
			if name == "Broken":
				raise ValueError("secret: metadata failure")
			return types.SimpleNamespace(
				fields=[
					{"fieldname": "event", "fieldtype": "Link", "options": "Event"},
					{"fieldname": "research_event", "fieldtype": "Link", "options": "Research Event"},
					{"fieldname": "reference_type", "fieldtype": "Link", "options": "DocType"},
					{
						"fieldname": "reference",
						"fieldtype": "Dynamic Link",
						"options": "reference_type",
					},
					{
						"fieldname": "subject_type",
						"fieldtype": "Select",
						"options": "Person\nEvent\nResearch Event\nPlace",
					},
					{"fieldname": "hidden_type", "fieldtype": "Dynamic Link", "options": "no_column"},
				]
			)

		f.get_meta = meta
		queries = []

		def count(doctype, filters):
			queries.append((doctype, filters))
			# Direct Link "event" -> Event target: 3 rows
			if filters == {"event": ["is", "set"]}:
				return 3
			# Direct Link "research_event" -> Research Event: 5 rows
			if filters == {"research_event": ["is", "set"]}:
				return 5
			# Selector field set to Event: 0
			if filters == {"subject_type": "Event"}:
				return 0
			# Selector field set to Research Event: 2
			if filters == {"subject_type": "Research Event"}:
				return 2
			return 0

		f.db = types.SimpleNamespace(
			table_exists=lambda name: name != "Missing",
			has_column=lambda name, field: field != "no_column",
			count=count,
		)
		path = ROOT / "siraj_research/setup/event_reference_inventory.py"
		spec = importlib.util.spec_from_file_location("event_reference_inventory_test", path)
		module = importlib.util.module_from_spec(spec)
		with patch.dict(sys.modules, {"frappe": f}):
			spec.loader.exec_module(module)
		result = module.inspect_metadata_event_references()
		self.assertEqual(
			result["nonzero_counts"],
			[
				{"doctype": "A", "field": "event", "kind": "direct", "target": "Event", "count": 3},
				{
					"doctype": "A",
					"field": "research_event",
					"kind": "direct",
					"target": "Research Event",
					"count": 5,
				},
				{
					"doctype": "A",
					"field": "subject_type",
					"kind": "selector",
					"target": "Research Event",
					"count": 2,
				},
			],
		)
		# 2 direct (Event + Research Event) + 2 selectors (reference_type, subject_type) x 2 targets = 6
		self.assertEqual(result["checked_fields"], 6)
		self.assertIn(("A", {"event": ["is", "set"]}), queries)
		self.assertIn(("A", {"research_event": ["is", "set"]}), queries)
		self.assertIn(("A", {"subject_type": "Event"}), queries)
		self.assertIn(("A", {"subject_type": "Research Event"}), queries)
		self.assertIn(("A", {"reference_type": "Event"}), queries)
		self.assertIn(("A", {"reference_type": "Research Event"}), queries)
		skip_doctypes = {x["doctype"] for x in result["skipped"]}
		self.assertEqual(skip_doctypes, {"A", "Single", "Virtual", "Missing", "Broken"})
		self.assertNotIn("secret", str(result))
		self.assertIn("not proof", result["note"])
		self.assertEqual(result["targets"], ("Event", "Research Event"))

	def test_count_failure_is_reported_not_zero(self):
		f = types.ModuleType("frappe")
		f.get_all = lambda *a, **kw: [{"name": "A"}]
		f.get_meta = lambda name: types.SimpleNamespace(
			fields=[{"fieldname": "ref", "fieldtype": "Link", "options": "Event"}]
		)

		def fail(*args):
			raise RuntimeError("secret value")

		f.db = types.SimpleNamespace(
			table_exists=lambda name: True, has_column=lambda *args: True, count=fail
		)
		path = ROOT / "siraj_research/setup/event_reference_inventory.py"
		spec = importlib.util.spec_from_file_location("event_reference_inventory_failure_test", path)
		module = importlib.util.module_from_spec(spec)
		with patch.dict(sys.modules, {"frappe": f}):
			spec.loader.exec_module(module)
		result = module.inspect_metadata_event_references()
		self.assertEqual(result["nonzero_counts"], [])
		self.assertEqual(result["checked_fields"], 0)
		self.assertEqual(result["skipped"][0]["reason"], "count unavailable")
		self.assertNotIn("secret", str(result))


if __name__ == "__main__":
	unittest.main()
