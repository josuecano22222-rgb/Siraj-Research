"""Fake inspection results; not live Frappe authorization evidence."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / "siraj_research/setup/permission_assertions.py"


class PermissionAssertionsTest(unittest.TestCase):
	def setUp(self):
		stub = types.ModuleType("siraj_research.setup.permission_review")
		stub.DOCTYPES = ("Person",)
		stub.OPERATIONS = ("read", "create")
		stub.DOCUMENT_OPERATIONS = ("read", "write")
		self.calls = []

		def inspect(user, dt, name):
			self.calls.append((user, dt, name))
			return {
				"doctypes": {
					dt: {
						"status": "checked",
						"doctype_permissions": {"read": True, "create": False},
						"document_permissions": {"read": True, "write": False},
						"list_contains_record": False,
					}
				}
			}

		stub.inspect_permissions = inspect
		spec = importlib.util.spec_from_file_location("permission_assertion_fixture", PATH)
		self.m = importlib.util.module_from_spec(spec)
		with patch.dict(sys.modules, {"siraj_research.setup.permission_review": stub}):
			spec.loader.exec_module(self.m)
		self.case = {
			"user": "reader",
			"doctype": "Person",
			"record_name": "secret",
			"expect": {
				"doctype.read": True,
				"doctype.create": False,
				"document.read": True,
				"document.write": False,
				"list_contains_record": False,
			},
		}

	def test_boolean_assertions_and_redacted_results(self):
		result = self.m.check([self.case], confirm="ISOLATED-TEST-APPROVED")
		self.assertTrue(result["passed"])
		self.assertEqual(result["cases"][0]["assertions"], 5)
		self.assertNotIn("secret", str(result))
		self.assertNotIn("reader", str(result))
		self.assertEqual(len(self.calls), 1)

	def test_mismatches_are_reported_not_raised_or_hidden(self):
		case = dict(self.case, expect={"document.read": False, "list_contains_record": True})
		result = self.m.check([case], confirm="ISOLATED-TEST-APPROVED")
		self.assertFalse(result["passed"])
		self.assertEqual(result["cases"][0]["failures"], ["document.read", "list_contains_record"])

	def test_all_cases_validated_before_any_access(self):
		for bad in [
			dict(self.case, expect={"document.unknown": True}),
			dict(self.case, expect={"doctype.read": 1}),
			dict(self.case, user="Guest"),
			dict(self.case, record_name=""),
		]:
			with self.subTest(bad=bad), self.assertRaises(ValueError):
				self.m.check([self.case, bad], confirm="ISOLATED-TEST-APPROVED")
		self.assertEqual(self.calls, [])
		with self.assertRaises(ValueError):
			self.m.check([self.case])
		self.assertEqual(self.calls, [])


if __name__ == "__main__":
	unittest.main()
