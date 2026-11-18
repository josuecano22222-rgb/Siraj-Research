"""Selected upstream v15 field contracts and research identity fixtures."""

import copy
import unittest

from siraj_research.setup.event_compatibility import (
	CORE_FIELDS,
	RESEARCH_FIELDS,
	PlanError,
	inspect,
	research_identity,
)


def meta(name, module, fields):
	return {
		"name": name,
		"module": module,
		"fields": [
			{"fieldname": n, "fieldtype": t, **({"options": o} if o is not None else {})}
			for n, (t, o) in fields.items()
		],
	}


class CompatibilityTests(unittest.TestCase):
	def setUp(self):
		self.core = meta("Event", "Desk", CORE_FIELDS)
		self.research = meta("Research Event", "Siraj Research", RESEARCH_FIELDS)

	def test_separate_core_calendar_and_research_contracts(self):
		before = copy.deepcopy((self.core, self.research))
		result = inspect(self.core, self.research)
		self.assertTrue(result["selected_contracts_match"])
		self.assertFalse(result["execution_ready"])
		self.assertEqual(research_identity(self.core, self.research), "Research Event")
		self.assertEqual((self.core, self.research), before)

	def test_legacy_collision_or_framework_fields_missing_never_alias(self):
		legacy = copy.deepcopy(self.core)
		legacy["module"] = "Siraj Research"
		legacy["fields"] = copy.deepcopy(self.research["fields"])
		result = inspect(legacy, self.research)
		self.assertIn("identity_or_owner_mismatch", {i["kind"] for i in result["issues"]})
		with self.assertRaises(PlanError):
			research_identity(legacy, self.research)
		for field in CORE_FIELDS:
			core = copy.deepcopy(self.core)
			core["fields"] = [f for f in core["fields"] if f["fieldname"] != field]
			with self.subTest(field=field), self.assertRaises(PlanError):
				research_identity(core, self.research)

	def test_conflicting_event_type_and_duplicate_fields_reject(self):
		core = copy.deepcopy(self.core)
		next(f for f in core["fields"] if f["fieldname"] == "event_type")["fieldtype"] = "Link"
		self.assertIn(
			"incompatible_contract_field", {i["kind"] for i in inspect(core, self.research)["issues"]}
		)
		research = copy.deepcopy(self.research)
		research["fields"].append(copy.deepcopy(research["fields"][0]))
		with self.assertRaises(PlanError):
			inspect(self.core, research)

	def test_destination_wrong_identity_is_not_accepted(self):
		target = copy.deepcopy(self.research)
		target["name"] = "Event"
		with self.assertRaises(PlanError):
			research_identity(self.core, target)


if __name__ == "__main__":
	unittest.main()
