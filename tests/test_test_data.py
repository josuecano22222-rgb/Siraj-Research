"""Schema and isolation tests for synthetic fixture (not a live Frappe test)."""

import ast
import copy
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = {}
for path in (ROOT / "siraj_research/siraj_research/doctype").glob("*/*.json"):
	data = json.loads(path.read_text(encoding="utf8"))
	SCHEMAS[data["name"]] = data


class FakeDoc:
	def __init__(self, api, values):
		self.api = api
		self.values = dict(values)
		self.doctype = values["doctype"]
		fields = SCHEMAS[self.doctype]["fields"]
		self.meta = types.SimpleNamespace(
			get_table_fields=lambda: [
				types.SimpleNamespace(fieldname=f["fieldname"])
				for f in fields
				if f["fieldtype"] in ("Table", "Table MultiSelect")
			]
		)

	def insert(self, ignore_permissions=False):
		assert ignore_permissions
		if self.api.fail_on == self.doctype:
			raise ValueError("simulated insert failure")
		schema = SCHEMAS[self.doctype]
		fields = {f.get("fieldname"): f for f in schema["fields"]}
		unknown = set(self.values) - set(fields) - {"doctype"}
		if unknown:
			raise AssertionError(f"{self.doctype}: unknown fields {unknown}")
		for name, field in fields.items():
			if not name:
				continue
			val = self.values.get(name, field.get("default"))
			if field.get("reqd") and (val is None or val == ""):
				raise AssertionError(f"{self.doctype}: missing {name}")
			if isinstance(val, str) and field.get("length") and len(val) > field["length"]:
				raise AssertionError(f"{self.doctype}: {name} exceeds length")
			if val and field["fieldtype"] == "Select" and val not in field.get("options", "").splitlines():
				raise AssertionError(f"{self.doctype}: invalid {name}={val}")
			if val and field["fieldtype"] == "Link" and not self.api.exists(field["options"], val):
				raise AssertionError(f"{self.doctype}: missing link {name}={val}")
			if val and field["fieldtype"] == "Dynamic Link":
				if not self.api.exists(self.values[field["options"]], val):
					raise AssertionError(f"{self.doctype}: missing dynamic link {name}={val}")
			if val and field["fieldtype"] in ("Table", "Table MultiSelect"):
				self.values[name] = [FakeChild(self.api, field["options"], row) for row in val]
		auto = schema.get("autoname", "")
		self.name = (
			self.values[auto.split(":", 1)[1]]
			if auto.startswith("field:")
			else self.doctype + "-" + str(len(self.api.records.get(self.doctype, {})) + 1)
		)
		if self.api.exists(self.doctype, self.name):
			raise ValueError("duplicate")
		self.api.records.setdefault(self.doctype, {})[self.name] = self
		return self

	def get(self, field):
		return self.values.get(field)


class FakeChild:
	def __init__(self, api, doctype, values):
		self.doctype = doctype
		self.values = dict(values)
		fields = {f.get("fieldname"): f for f in SCHEMAS[doctype]["fields"]}
		assert not (set(values) - set(fields)), (doctype, values)
		for key, field in fields.items():
			if field.get("reqd") and values.get(key, field.get("default")) in (None, ""):
				raise AssertionError(f"{doctype}: missing {key}")
			val = values.get(key, field.get("default"))
			if val and field["fieldtype"] == "Select" and val not in field.get("options", "").splitlines():
				raise AssertionError(f"{doctype}: invalid select {key}")
			if isinstance(val, str) and field.get("length") and len(val) > field["length"]:
				raise AssertionError(f"{doctype}: {key} exceeds length")
			if (
				values.get(key)
				and field["fieldtype"] == "Link"
				and not api.exists(field["options"], values[key])
			):
				raise AssertionError(f"{doctype}: missing link {key}")


class FakeFrappe(types.ModuleType):
	def __init__(self):
		super().__init__("frappe")
		self.local = types.SimpleNamespace(site="siraj.test.localhost")
		self.conf = {"siraj_test_fixture_site": self.local.site}
		self.records = {
			"Country": {"Iraq": object()},
			"Person Category": {"Military": object()},
			"Workflow State": {"Draft": object()},
			"DocType": {"SIRAJ Settings": object()},
		}
		self.initial = copy.deepcopy(self.records)
		self.fail_on = None
		self.rolled_back = False
		self.db = types.SimpleNamespace(exists=self.exists, rollback=self.rollback)

	def exists(self, doctype, name):
		records = self.records.get(doctype, {})
		if isinstance(name, dict):
			for record_name, record in records.items():
				values = (
					record.values
					if isinstance(record, FakeDoc)
					else record
					if isinstance(record, dict)
					else {}
				)
				if all(values.get(key) == value for key, value in name.items()):
					return record_name
			return None
		return name if name in records else None

	def get_doc(self, values):
		return FakeDoc(self, values)

	def rollback(self):
		self.records = self.initial
		self.rolled_back = True


def load(fake):
	spec = importlib.util.spec_from_file_location(
		"siraj_test_fixture", ROOT / "siraj_research/setup/test_data.py"
	)
	module = importlib.util.module_from_spec(spec)
	with patch.dict(sys.modules, {"frappe": fake}):
		spec.loader.exec_module(module)
	return module


class FixtureTest(unittest.TestCase):
	def setUp(self):
		self.frappe = FakeFrappe()
		self.module = load(self.frappe)
		# The fixture construction is schema-tested independently, but cannot
		# run on a real site until the Event collision is resolved.
		self.real_event_guard = self.module._assert_event_safe
		self.module._assert_event_safe = lambda: None

	def test_coverage_links_and_repeat_guard(self):
		result = self.module.seed_test_data()
		self.assertEqual(set(result["created"]) | {result["existing_singleton"]}, set(SCHEMAS))
		self.assertEqual(result["created"]["Relationship"], 7)
		self.assertEqual(result["created"]["Military Unit"], 3)
		self.assertEqual(
			result["created"]["Person"], 6 + self.module.FOLD_CLASSIFICATIONS + self.module.FOLD_RECORDS
		)
		self.assertTrue(all(result["created"][name] for name in self.module.CHILD_TYPES))
		with self.assertRaisesRegex(RuntimeError, "Sample identifier already exists"):
			self.module.seed_test_data()

	def test_multilingual_sparse_and_relationship_scenarios(self):
		result = self.module.seed_test_data()
		people = [self.frappe.records["Person"][name] for name in result["created_names"]["Person"]]
		sparse = next(p for p in people if p.values.get("name_ar") == "اختبار شخص عربي فقط")
		self.assertFalse(sparse.values.get("name_en"))
		self.assertFalse(sparse.values.get("latitude"))
		self.assertEqual(sparse.values.get("birth_date_precision"), "approximate")
		self.assertEqual(sparse.values.get("birthplace_as_stated"), "غير معروف")
		mixed = next(p for p in people if p.values.get("name_en") == "TEST Élodie O'Neil & Noor")
		self.assertIn("研究者", mixed.values["name_original"])
		self.assertIn("آزمایش", mixed.values["name_original"])
		self.assertEqual((mixed.values["latitude"], mixed.values["longitude"]), (0, 20))
		devanagari = next(p for p in people if "अनाम" in p.values.get("name_original", ""))
		self.assertEqual((devanagari.values["latitude"], devanagari.values["longitude"]), (0, 0))
		cyrillic = next(p for p in people if "Новак" in p.values.get("name_original", ""))
		self.assertLess(cyrillic.values["latitude"], 0)
		self.assertEqual(cyrillic.values["birth_date_precision"], "year")
		full = next(p for p in people if p.values.get("name_en") == "TEST Layla Al-Sahli")
		self.assertTrue(full.values.get("evidence"))
		self.assertTrue(full.values.get("leadership_assessments"))
		edges = [
			self.frappe.records["Relationship"][name].values
			for name in result["created_names"]["Relationship"]
		]
		self.assertFalse(any(sparse.name in (edge["subject"], edge["object"]) for edge in edges))
		self.assertTrue(any(edge["subject"] == edge["object"] == mixed.name for edge in edges))
		pairs = [
			(edge["subject_type"], edge["subject"], edge["object_type"], edge["object"]) for edge in edges
		]
		self.assertLess(len(set(pairs)), len(pairs))
		self.assertTrue(any(edge.get("end_date") and not edge.get("evidence") for edge in edges))
		self.assertTrue(any(edge.get("evidence") for edge in edges))
		supports = {child.values["support_type"] for edge in edges for child in edge.get("evidence", [])}
		self.assertEqual(supports, {"supports", "contradicts", "contextualizes"})
		for doctype in self.module.LOOKUPS:
			record = self.frappe.records[doctype]["TEST " + doctype]
			self.assertIn("اختبار", record.values["label_ar"])
			self.assertNotIn(doctype, record.values["label_ar"])

	def test_fictional_narrative_and_disputed_evidence_are_connected(self):
		result = self.module.seed_test_data()

		def records(doctype):
			return [self.frappe.records[doctype][name] for name in result["created_names"][doctype]]

		source = next(d for d in records("Source") if d.values.get("publisher"))
		person = next(d for d in records("Person") if d.values.get("name_en") == "TEST Layla Al-Sahli")
		institution = next(
			d for d in records("Institution") if d.values.get("name_en") == "TEST Al-Nur Association"
		)
		event = next(
			d
			for d in records("Siraj Event")
			if d.values.get("title_en") == "TEST Al-Nur Community Outreach Day"
		)
		self.assertEqual(person.values["primary_source"], source.name)
		self.assertEqual(institution.values["primary_source"], source.name)
		self.assertEqual(event.values["primary_source"], source.name)
		self.assertEqual(person.values["birth_date_as_stated"], "1984")
		self.assertEqual(event.values["start_date_as_stated"], "2019-05-18")
		self.assertEqual(event.values["start_date_precision"], "day")
		edges = records("Relationship")
		disputed = next(
			d
			for d in edges
			if any(row.values["support_type"] == "contradicts" for row in d.values.get("evidence", []))
		)
		evidence = disputed.values["evidence"]
		self.assertEqual(len({row.values["source"] for row in evidence}), 2)
		self.assertTrue(all("TEST" in row.values["supported_claim"] for row in evidence))

	def test_fixture_exercises_folded_group_and_record_counts(self):
		from test_visualization import FakeFrappe as VisualizationFrappe
		from test_visualization import load_visualization

		self.module.seed_test_data()
		rows = []
		for name, doc in self.frappe.records["Person"].items():
			values = doc.values
			rows.append(
				{
					"name": name,
					"nationality": values.get("nationality"),
					"classification": values.get("classification"),
					"workflow_state": "Draft",
					"display_name": values.get("display_name")
					or values.get("name_en")
					or values.get("name_ar"),
				}
			)
		viz = load_visualization(VisualizationFrappe())
		dimensions = ("nationality", "classification", "workflow_state")
		counted = viz._structure_counts(rows, dimensions, "display_name")
		children = viz._structure_children(counted, dimensions)
		iraq = next(child for child in children if child["key"] == "Iraq")
		folded_groups = next(child for child in iraq["children"] if child.get("folded_groups"))
		self.assertGreater(folded_groups["folded_groups"], 0)
		self.assertEqual(sum(child["count"] for child in iraq["children"]), iraq["count"])
		common = next(child for child in iraq["children"] if child["label"] == "TEST Person Classification")
		workflow = common["children"][0]
		self.assertGreater(workflow["count"], viz.STRUCTURE_MAX_LEAVES)
		self.assertGreater(workflow["children"][-1]["folded_records"], 0)
		self.assertEqual(sum(child["count"] for child in workflow["children"]), workflow["count"])

	def test_fixture_explorer_graph_and_coordinate_cases(self):
		from test_visualization import FakeFrappe as VisualizationFrappe
		from test_visualization import load_visualization

		result = self.module.seed_test_data()
		types_to_copy = (
			"Person",
			"Institution",
			"Place",
			"Siraj Event",
			"Source",
			"Military Unit",
			"Operational Deployment",
			"Relationship",
		)
		rows = {
			doctype: [{"name": name, **doc.values} for name, doc in self.frappe.records[doctype].items()]
			for doctype in types_to_copy
		}
		viz = load_visualization(VisualizationFrappe(rows))
		graph = viz.relationship_data()
		self.assertEqual(
			len(graph["nodes"]),
			sum(
				result["created"][dt] for dt in ("Person", "Institution", "Place", "Siraj Event", "Source")
			),
		)
		self.assertEqual(len(graph["edges"]), result["created"]["Relationship"])
		points = viz.geographic_data()["points"]
		point_ids = {(point["doctype"], point["name"]) for point in points}
		people = self.frappe.records["Person"]
		zero = next(doc for doc in people.values() if "अनाम" in doc.values.get("name_original", ""))
		single_zero = next(
			doc for doc in people.values() if doc.values.get("name_en") == "TEST Élodie O'Neil & Noor"
		)
		sparse = next(doc for doc in people.values() if doc.values.get("name_ar") == "اختبار شخص عربي فقط")
		self.assertNotIn(("Person", zero.name), point_ids)
		self.assertNotIn(("Person", sparse.name), point_ids)
		self.assertIn(("Person", single_zero.name), point_ids)

	def test_fold_class_collision_is_detected_before_writes(self):
		self.frappe.records["Person Classification"] = {"existing": {"code": "TEST_FOLD_CLASS_16"}}
		with self.assertRaisesRegex(RuntimeError, "Person Classification"):
			self.module.seed_test_data()
		self.assertNotIn("Authentication Level", self.frappe.records)

	def test_collision_blocks_seeding_before_writes(self):
		self.module._assert_event_safe = self.real_event_guard
		before = set(self.frappe.records)
		with self.assertRaisesRegex(RuntimeError, "Event conflicts"):
			self.module.seed_test_data()
		self.assertEqual(set(self.frappe.records), before)

	def test_existing_operational_data_is_preserved_and_samples_are_marked(self):
		self.frappe.local.site = "frappe.com"
		original = {"name_en": "A real record"}
		self.frappe.records["Person"] = {"PER-REAL": original}
		result = self.module.seed_test_data()
		self.assertIs(self.frappe.records["Person"]["PER-REAL"], original)
		self.assertEqual(original, {"name_en": "A real record"})
		for doctype in self.module.OPERATIONAL_TYPES:
			for name in result["created_names"][doctype]:
				doc = self.frappe.records[doctype][name]
				self.assertIn("TEST SAMPLE", doc.values["researcher_notes"])
		self.assertEqual(result["site"], "frappe.com")
		self.assertNotIn("PER-REAL", result["created_names"]["Person"])

	def test_collision_or_missing_prerequisite_rejected_before_writes(self):
		self.frappe.records["Person Status"] = {"custom": {"code": "TEST_PERSON_STATUS"}}
		before = set(self.frappe.records)
		with self.assertRaisesRegex(RuntimeError, "Sample identifier already exists in Person Status"):
			self.module.seed_test_data()
		self.assertEqual(set(self.frappe.records), before)
		del self.frappe.records["Person Status"]
		del self.frappe.records["Country"]["Iraq"]
		with self.assertRaisesRegex(RuntimeError, "Missing fixture prerequisite"):
			self.module.seed_test_data()
		self.assertEqual(set(self.frappe.records), before - {"Person Status"})

	def test_late_name_collision_is_checked_before_any_insertion(self):
		self.frappe.records["Unit Classification"] = {
			"TEST Unit Classification": {"classification_name": "TEST Unit Classification"}
		}
		before = copy.deepcopy(self.frappe.records)
		with self.assertRaisesRegex(RuntimeError, "Unit Classification"):
			self.module.seed_test_data()
		self.assertEqual(self.frappe.records["Unit Classification"], before["Unit Classification"])
		self.assertFalse(self.frappe.rolled_back)
		self.assertNotIn("Authentication Level", self.frappe.records)

	def test_missing_app_is_rejected(self):
		self.frappe.records["DocType"].clear()
		with self.assertRaisesRegex(RuntimeError, "Install siraj_research"):
			self.module.seed_test_data()

	def test_fixture_is_not_a_hook_or_whitelisted_endpoint(self):
		root = ROOT / "siraj_research"
		for path in (root / "hooks.py", root / "setup/install.py", root / "setup/master_data.py"):
			with self.subTest(path=str(path)):
				self.assertNotIn("seed_test_data", path.read_text(encoding="utf8"))
		tree = ast.parse((root / "setup/test_data.py").read_text(encoding="utf8"))
		target = next(
			node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "seed_test_data"
		)
		self.assertEqual(target.decorator_list, [])

	def test_all_seeded_scoped_records_stamp_valid_data_group(self):
		result = self.module.seed_test_data()
		self.assertIn("GD", self.frappe.records["Data Group"])
		for doctype, names in result["created_names"].items():
			has_dg = any(f.get("fieldname") == "data_group" for f in SCHEMAS[doctype]["fields"])
			for name in names:
				doc = self.frappe.records[doctype][name]
				if has_dg:
					self.assertEqual(doc.values.get("data_group"), "GD", f"{doctype}/{name}")

	def test_failure_rolls_back(self):
		self.frappe.records["Person"] = {"PER-REAL": {"name_en": "A real record"}}
		self.frappe.initial = copy.deepcopy(self.frappe.records)
		self.frappe.fail_on = "Mission"
		with self.assertRaisesRegex(ValueError, "simulated"):
			self.module.seed_test_data()
		self.assertTrue(self.frappe.rolled_back)
		self.assertEqual(
			set(self.frappe.records), {"Country", "Person Category", "Workflow State", "DocType", "Person"}
		)
		self.assertEqual(self.frappe.records["Person"]["PER-REAL"]["name_en"], "A real record")


if __name__ == "__main__":
	unittest.main()
