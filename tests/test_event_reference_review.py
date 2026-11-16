"""Synthetic corpus and snapshots, never a site inventory or migration."""

import copy
import json
import unittest
from pathlib import Path

from siraj_research.setup.event_reference_review import REQUIRED_AREAS, classify, discover, rehearsal
from siraj_research.setup.event_snapshot_projection import inspect_projection, project
from siraj_research.setup.event_transition_plan import PlanError, prepare_transition


def row(dt, name, **values):
	return {"doctype": dt, "name": name, "values": values}


def ref(dt, name, typ, target, value="r", category="research"):
	return dict(
		doctype=dt,
		name=name,
		type_field=typ,
		name_field=target,
		type_value="Event",
		target=value,
		classification=category,
	)


class DiscoveryTest(unittest.TestCase):
	def test_corpus_and_metadata_candidates_are_unclassified(self):
		meta = {
			"fields": [
				{"fieldname": "selector", "fieldtype": "Link", "options": "DocType"},
				{"fieldname": "destination", "fieldtype": "Dynamic Link", "options": "selector"},
				{"fieldname": "legacy", "fieldtype": "Link", "options": "Event"},
				{"fieldname": "kind", "fieldtype": "Select", "options": "Person\nEvent"},
			]
		}
		files = [
			{"path": "app/hooks.py", "text": 'doc_events = {"Event": "integration.handler"}'},
			{"path": "app/report/r.py", "text": 'query("Event")'},
			{"path": "app/integrations/calendar.py", "text": 'target = "Event"'},
			{"path": "app/doctype/example/example.json", "text": json.dumps(meta)},
			{"path": "app/other.py", "text": "function_without_hits()"},
		]
		unchanged = copy.deepcopy(files)
		result = discover(files)
		self.assertEqual(files, unchanged)
		self.assertFalse(result["execution_ready"])
		self.assertEqual(result["files_scanned"], 5)
		self.assertEqual(result["issues"], [])
		self.assertTrue(
			{"hook", "report_dashboard", "integration", "doctype_metadata"}
			<= {x["category"] for x in result["findings"]}
		)
		self.assertTrue(
			{"dynamic_link", "direct_link", "event_selector"} <= {x["kind"] for x in result["findings"]}
		)
		self.assertTrue(all(x["classification"] == "unreviewed" for x in result["findings"]))
		partial = classify(result, [dict(index=0, classification="ambiguous", evidence="unknown ownership")])
		self.assertIn(0, partial["pending"])
		self.assertFalse(partial["execution_ready"])
		complete = classify(
			result,
			[
				dict(index=i, classification="research", evidence="fixture only")
				for i in range(len(result["findings"]))
			],
		)
		self.assertEqual(complete["pending"], [])
		self.assertFalse(complete["execution_ready"])
		with self.assertRaises(PlanError):
			classify(result, [dict(index=0, classification="research", evidence="x")] * 2)

	def test_unknown_selector_malformed_metadata_and_duplicates_block(self):
		invalid = {"fields": [{"fieldname": "target", "fieldtype": "Dynamic Link", "options": "absent"}]}
		d = discover(
			[
				{"path": "app/doctype/one/one.json", "text": json.dumps(invalid)},
				{"path": "app/doctype/two/two.json", "text": "{"},
			]
		)
		self.assertEqual({x["kind"] for x in d["issues"]}, {"missing_dynamic_selector", "invalid_metadata"})
		with self.assertRaises(PlanError):
			discover([{"path": "same", "text": ""}] * 2)

	def test_committed_corpus_smoke(self):
		# Tests run from an isolated committed archive to avoid dirty worktree sources.
		root = Path(__file__).resolve().parents[1]
		paths = [
			"siraj_research/hooks.py",
			"siraj_research/siraj_research/doctype/relationship/relationship.json",
			"siraj_research/siraj_research/report/entity_relationship_graph/entity_relationship_graph.py",
		]
		d = discover([{"path": p, "text": (root / p).read_text()} for p in paths])
		dynamic = [x for x in d["findings"] if x["kind"] == "dynamic_link"]
		self.assertTrue(any(x["field"] == "subject" and x["selector"] == "subject_type" for x in dynamic))
		self.assertTrue(any(x["field"] == "object" and x["selector"] == "object_type" for x in dynamic))
		self.assertTrue(any(x["category"] == "report_dashboard" for x in d["findings"]))
		self.assertFalse(d["execution_ready"])


class RehearsalTest(unittest.TestCase):
	def setUp(self):
		self.events = [dict(name="r", classification="research"), dict(name="c", classification="calendar")]
		self.rows = [
			row("Event", "r", title="research", custom_field="custom", owner="owner", modified="before"),
			row("Event", "c", subject="calendar"),
			row("File", "f", attached_to_doctype="Event", attached_to_name="r", url="private"),
			row("Comment", "m", reference_doctype="Event", reference_name="r", content="comment"),
			row("Evidence", "e", parenttype="Event", parent="r", parentfield="evidence", idx=1),
			row("Relationship", "rel", subject_type="Event", subject="c"),
		]
		self.refs = [
			ref("File", "f", "attached_to_doctype", "attached_to_name"),
			ref("Comment", "m", "reference_doctype", "reference_name"),
			ref("Evidence", "e", "parenttype", "parent"),
			ref("Relationship", "rel", "subject_type", "subject", "c", "calendar"),
		]
		self.coverage = {a: "reviewed" for a in REQUIRED_AREAS}
		self.discovery = classify(discover([]), [])
		self.schema = {
			"source_meta": {
				"name": "Event",
				"module": "Siraj Research",
				"fields": [{"fieldname": "custom_field", "fieldtype": "Data"}],
			},
			"target_meta": {
				"name": "Research Event",
				"module": "Siraj Research",
				"fields": [{"fieldname": "custom_field", "fieldtype": "Data"}],
			},
		}

	def test_fixture_gates_and_data_preserved_not_execution_ready(self):
		before = copy.deepcopy((self.events, self.refs, self.rows, self.coverage, self.discovery))
		projected = project(self.events, self.refs, self.rows)
		self.assertFalse(projected["execution_ready"])
		self.assertFalse(prepare_transition(self.events, self.refs, [])["execution_ready"])
		self.assertFalse(
			inspect_projection(self.events, self.refs, self.rows, projected["rows"])["execution_ready"]
		)
		result = rehearsal(
			self.events,
			self.refs,
			self.rows,
			self.coverage,
			self.discovery,
			after=projected["rows"],
			**self.schema,
		)
		self.assertTrue(all(result["gates"].values()))
		self.assertEqual(result["blockers"], [])
		self.assertFalse(result["execution_ready"])
		target = next(r for r in projected["rows"] if r["doctype"] == "Research Event")
		self.assertEqual(target["values"]["custom_field"], "custom")
		self.assertEqual((self.events, self.refs, self.rows, self.coverage, self.discovery), before)

	def test_ambiguous_or_missing_records_and_duplicate_target_fail(self):
		cases = [
			(self.events, [*self.refs, ref("File", "missing", "type", "target")], self.rows),
			([*self.events, self.events[0]], self.refs, self.rows),
			(self.events, self.refs, [*self.rows, row("Research Event", "r")]),
			([dict(name="r", classification="ambiguous")], [], self.rows),
			(self.events, self.refs, [*self.rows, self.rows[-1]]),
		]
		for events, refs, rows in cases:
			with self.subTest(events=events, refs=refs, rows=rows):
				result = rehearsal(events, refs, rows, self.coverage, self.discovery, **self.schema)
				self.assertFalse(result["gates"]["preflight"])
				self.assertFalse(result["execution_ready"])

	def test_missing_changed_children_comments_files_and_rollback_conflicts(self):
		projected = project(self.events, self.refs, self.rows)
		for dt, name in [("File", "f"), ("Comment", "m"), ("Evidence", "e"), ("Research Event", "r")]:
			changed = copy.deepcopy(projected["rows"])
			next(r for r in changed if (r["doctype"], r["name"]) == (dt, name))["values"]["edit"] = "conflict"
			result = rehearsal(
				self.events,
				self.refs,
				self.rows,
				self.coverage,
				self.discovery,
				after=changed,
				rollback_rows=changed,
				**self.schema,
			)
			self.assertFalse(result["gates"]["postflight"])
			self.assertFalse(result["gates"]["rollback"])
			self.assertFalse(result["execution_ready"])
		missing = [r for r in projected["rows"] if r["doctype"] != "Comment"]
		self.assertFalse(
			rehearsal(
				self.events, self.refs, self.rows, self.coverage, self.discovery, after=missing, **self.schema
			)["gates"]["postflight"]
		)

	def test_custom_field_schema_mismatch_and_missing_postflight_block(self):
		schema = copy.deepcopy(self.schema)
		schema["target_meta"]["fields"][0]["fieldtype"] = "Text"
		result = rehearsal(self.events, self.refs, self.rows, self.coverage, self.discovery, **schema)
		self.assertFalse(result["gates"]["schema"])
		self.assertFalse(result["gates"]["preflight"])
		self.assertFalse(result["gates"]["postflight"])
		self.assertIn("postflight_not_supplied", result["blockers"])
		missing = rehearsal(self.events, self.refs, self.rows, self.coverage, self.discovery)
		self.assertIn("schema_not_supplied", missing["blockers"])
		self.assertFalse(missing["execution_ready"])

	def test_incomplete_claims_and_unreviewed_candidates_block(self):
		found = discover([{"path": "app/hooks.py", "text": "Event"}])
		result = rehearsal(self.events, self.refs, self.rows, {}, found)
		self.assertFalse(result["gates"]["coverage"])
		self.assertFalse(result["gates"]["discovery"])
		self.assertFalse(result["execution_ready"])


if __name__ == "__main__":
	unittest.main()
