from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from siraj_research.setup.install import setup


class TestSharedRecordIsolation(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		setup("Isolation-Test-Password-2026!", commit=False)

	def setUp(self):
		frappe.set_user("Administrator")
		for name in frappe.get_list("Shared Record", pluck="name"):
			frappe.delete_doc("Shared Record", name, force=True)

	def tearDown(self):
		frappe.set_user("Administrator")

	def _insert_as(self, user, title, data_group=None):
		frappe.set_user(user)
		return frappe.get_doc(
			{
				"doctype": "Shared Record",
				"title": title,
				"details": "test details",
				"data_group": data_group,
			}
		).insert()

	def test_same_group_can_list_and_edit_each_others_record(self):
		record = self._insert_as("gd1@example.com", "GD shared")
		frappe.set_user("gd2@example.com")
		self.assertIn(record.name, frappe.get_list("Shared Record", pluck="name"))
		other_users_doc = frappe.get_doc("Shared Record", record.name)
		other_users_doc.details = "edited by GD2"
		other_users_doc.save()
		self.assertEqual(other_users_doc.details, "edited by GD2")

	def test_other_group_cannot_list_open_or_edit(self):
		record = self._insert_as("gd1@example.com", "GD private")
		frappe.set_user("gc1@example.com")
		self.assertNotIn(record.name, frappe.get_list("Shared Record", pluck="name"))
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc("Shared Record", record.name).check_permission("read")
		foreign_doc = frappe.get_doc("Shared Record", record.name)
		foreign_doc.details = "forbidden"
		with self.assertRaises(frappe.PermissionError):
			foreign_doc.save()

	def test_forged_group_is_rewritten(self):
		record = self._insert_as("gd3@example.com", "Forged", data_group="GC")
		self.assertEqual(record.data_group, "GD")
		self.assertEqual(frappe.db.get_value("Shared Record", record.name, "data_group"), "GD")

	def test_record_cannot_move_groups(self):
		record = self._insert_as("gd4@example.com", "Locked")
		record.data_group = "GC"
		with self.assertRaises(frappe.PermissionError):
			record.save()

	def test_empty_group_is_invisible_to_normal_users(self):
		frappe.set_user("Administrator")
		record = frappe.get_doc(
			{"doctype": "Shared Record", "title": "Orphan", "data_group": "GD"}
		).insert()
		# Simulate legacy/corrupt data; application saves cannot create this state.
		frappe.db.set_value("Shared Record", record.name, "data_group", None)

		for user in ("gd1@example.com", "gc1@example.com"):
			frappe.set_user(user)
			self.assertNotIn(record.name, frappe.get_list("Shared Record", pluck="name"))
			with self.assertRaises(frappe.PermissionError):
				frappe.get_doc("Shared Record", record.name).check_permission("read")

		frappe.set_user("Administrator")
		frappe.get_doc("Shared Record", record.name).check_permission("read")
