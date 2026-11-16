"""Pure synthetic Event review, no Frappe or live database."""

import copy
import unittest

from siraj_research.setup.event_transition_plan import PlanError
from siraj_research.setup.event_transition_review import REVIEW_AREAS, review


def meta(name, fields):
	return {"name": name, "module": "Siraj Research", "fields": fields}


def ref(name, target, classification="research", type_field="ref_type"):
	return dict(
		doctype="File",
		name=name,
		type_field=type_field,
		name_field="ref_name",
		type_value="Event",
		target=target,
		classification=classification,
	)


class EventReviewTest(unittest.TestCase):
	def setUp(self):
		self.source = meta(
			"Event",
			[
				{"fieldname": "title", "fieldtype": "Data"},
				{"fieldname": "evidence", "fieldtype": "Table", "options": "Evidence"},
			],
		)
		self.target = meta("Research Event", copy.deepcopy(self.source["fields"]))
		self.coverage = {area: "reviewed" for area in REVIEW_AREAS}

	def test_complete_fixture_never_authorizes_execution_or_mutates_inputs(self):
		events = [{"name": "r", "classification": "research"}, {"name": "c", "classification": "calendar"}]
		refs = [ref("f", "r")]
		inputs = copy.deepcopy((self.source, self.target, events, refs, self.coverage))
		result = review(self.source, self.target, events, refs, [], self.coverage)
		self.assertEqual(result["issues"], [])
		self.assertFalse(result["execution_ready"])
		self.assertIn("unverified", result["warning"])
		self.assertEqual((self.source, self.target, events, refs, self.coverage), inputs)

	def test_all_supplied_conflicts_and_missing_review_areas_are_reported(self):
		target = meta(
			"Research Event",
			[{"fieldname": "title", "fieldtype": "Text"}, {"fieldname": "new", "fieldtype": "Data"}],
		)
		events = [
			{"name": "r", "classification": "research"},
			{"name": "r", "classification": "research"},
			{"name": "u", "classification": "ambiguous"},
		]
		refs = [ref("f", "missing"), ref("f", "r", "calendar")]
		result = review(self.source, target, events, refs, ["r", "r"], {})
		kinds = {x["kind"] for x in result["issues"]}
		self.assertTrue(
			{
				"coverage_unreviewed",
				"field_changed",
				"field_missing",
				"target_only_field",
				"target_name_conflict",
				"event_unclassified",
				"duplicate_event",
				"duplicate_target",
				"orphan_reference",
				"duplicate_reference",
				"reference_classification_conflict",
				"planner_rejected",
			}
			<= kinds
		)
		self.assertFalse(result["execution_ready"])

	def test_unexpected_schema_and_invalid_manifest_fail_closed(self):
		target = meta("Research Event", [])
		target["module"] = "Desk"
		with self.assertRaises(PlanError):
			review(self.source, target, [], [], [], self.coverage)
		with self.assertRaises(PlanError):
			review(self.source, self.target, [], [], [], {"unknown": "reviewed"})
		with self.assertRaises(PlanError):
			review(self.source, self.target, [{"name": "x"}], [], [], {})

	def test_event_owned_reference_requires_review(self):
		event_ref = dict(ref("r", "r"), doctype="Event")
		result = review(
			self.source,
			self.target,
			[{"name": "r", "classification": "research"}],
			[event_ref],
			[],
			self.coverage,
		)
		self.assertIn("event_owned_reference_unhandled", {i["kind"] for i in result["issues"]})

	def test_overlapping_reference_fields_are_rejected_by_underlying_planner(self):
		refs = [ref("x", "r"), dict(ref("x", "r"), type_field="other", name_field="ref_name")]
		result = review(
			self.source, self.target, [{"name": "r", "classification": "research"}], refs, [], self.coverage
		)
		self.assertIn("planner_rejected", {i["kind"] for i in result["issues"]})


if __name__ == "__main__":
	unittest.main()
