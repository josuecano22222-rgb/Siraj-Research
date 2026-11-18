"""In-memory fixtures, not real Frappe records or migration tests."""

import copy
import unittest

from siraj_research.setup.event_snapshot_projection import (
	PlanError,
	inspect_projection,
	project,
	rollback_projection,
)


def row(dt, name, **values):
	return {"doctype": dt, "name": name, "values": values}


def ref(dt, name, type_field, name_field, target, classification="research"):
	return dict(
		doctype=dt,
		name=name,
		type_field=type_field,
		name_field=name_field,
		type_value="Event",
		target=target,
		classification=classification,
	)


class ProjectionTests(unittest.TestCase):
	def setUp(self):
		self.events = [dict(name="r", classification="research"), dict(name="c", classification="calendar")]
		self.rows = [
			row(
				"Event",
				"r",
				owner="owner",
				payload={"title": "research", "nested": [None, 0, False]},
				modified="a",
			),
			row("Event", "c", owner="calendar", event_type="Private"),
			row("File", "file", attached_to_doctype="Event", attached_to_name="r", file_url="private-file"),
			row("Comment", "comment", reference_doctype="Event", reference_name="r", content="audit"),
			row("Evidence", "child", parenttype="Event", parent="r", idx=1),
			row("Relationship", "rel", subject_type="Event", subject="c"),
		]
		self.refs = [
			ref("File", "file", "attached_to_doctype", "attached_to_name", "r"),
			ref("Comment", "comment", "reference_doctype", "reference_name", "r"),
			ref("Evidence", "child", "parenttype", "parent", "r"),
			ref("Relationship", "rel", "subject_type", "subject", "c", "calendar"),
		]

	def test_project_preserves_values_and_rollback(self):
		original = copy.deepcopy(self.rows)
		result = project(self.events, self.refs, self.rows)
		self.assertEqual(self.rows, original)
		rows = {(r["doctype"], r["name"]): r for r in result["rows"]}
		self.assertEqual(rows[("Event", "r")]["values"], rows[("Research Event", "r")]["values"])
		self.assertEqual(rows[("File", "file")]["values"]["attached_to_doctype"], "Research Event")
		self.assertEqual(rows[("Evidence", "child")]["values"]["idx"], 1)
		self.assertEqual(rows[("Relationship", "rel")]["values"]["subject_type"], "Event")
		restored = rollback_projection(result["rows"], result["journal"])
		self.assertEqual(
			sorted(restored, key=lambda r: (r["doctype"], r["name"])),
			sorted(original, key=lambda r: (r["doctype"], r["name"])),
		)

	def test_rollback_preserves_unrelated_changes_and_rejects_stale_affected_rows(self):
		result = project(self.events, self.refs, self.rows)
		unrelated = [*copy.deepcopy(result["rows"]), row("Person", "new", value="safe")]
		self.assertIn(row("Person", "new", value="safe"), rollback_projection(unrelated, result["journal"]))
		for dt, name, value in [("File", "file", "changed"), ("Research Event", "r", "changed")]:
			changed = copy.deepcopy(result["rows"])
			next(r for r in changed if (r["doctype"], r["name"]) == (dt, name))["values"]["extra"] = value
			with self.subTest(dt=dt), self.assertRaises(PlanError):
				rollback_projection(changed, result["journal"])

	def test_missing_or_mismatched_and_collision_fail(self):
		cases = [
			(self.events[:-1], self.refs, self.rows),
			(self.events, self.refs, self.rows[1:]),
			(self.events, self.refs, [*self.rows, row("Research Event", "r")]),
			(self.events, [*self.refs, ref("File", "missing", "kind", "target", "r")], self.rows),
		]
		wrong = copy.deepcopy(self.rows)
		wrong[2]["values"]["attached_to_name"] = "c"
		cases.append((self.events, self.refs, wrong))
		for args in cases:
			with self.subTest(args=args), self.assertRaises(PlanError):
				project(*args)

	def test_duplicate_invalid_nonfinite_and_event_owned_reference_fail(self):
		for badrows in [
			[*self.rows, self.rows[0]],
			[*self.rows, row("X", "x", value=float("nan"))],
			[*self.rows, row("X", "x", value={1: "x"})],
		]:
			with self.subTest(badrows=badrows), self.assertRaises(PlanError):
				project(self.events, self.refs, badrows)
		with self.assertRaises(PlanError):
			project(self.events, [*self.refs, ref("Event", "r", "t", "n", "c", "calendar")], self.rows)

	def test_pre_post_report_detects_missing_extra_and_changed_rows(self):
		result = project(self.events, self.refs, self.rows)
		ok = inspect_projection(self.events, self.refs, self.rows, result["rows"])
		self.assertTrue(ok["model_matches"])
		self.assertEqual(ok["pre"]["research_events"], 1)
		changed = copy.deepcopy(result["rows"])
		changed = [r for r in changed if (r["doctype"], r["name"]) != ("File", "file")]
		next(r for r in changed if (r["doctype"], r["name"]) == ("Evidence", "child"))["values"]["idx"] = 2
		changed.append(row("Person", "extra"))
		report = inspect_projection(self.events, self.refs, self.rows, changed)
		self.assertFalse(report["model_matches"])
		self.assertEqual(report["post"]["missing"], [{"doctype": "File", "name": "file"}])
		self.assertEqual(report["post"]["unexpected"], [{"doctype": "Person", "name": "extra"}])
		self.assertEqual(report["post"]["changed"], [{"doctype": "Evidence", "name": "child"}])
		self.assertIn("not a real-site integrity report", report["warning"])

	def test_typed_comparison_does_not_equate_boolean_and_integer(self):
		result = project(self.events, self.refs, self.rows)
		changed = copy.deepcopy(result["rows"])
		copyrow = next(r for r in changed if r["doctype"] == "Research Event")
		copyrow["values"]["payload"]["nested"][2] = 0
		with self.assertRaises(PlanError):
			rollback_projection(changed, result["journal"])


if __name__ == "__main__":
	unittest.main()
