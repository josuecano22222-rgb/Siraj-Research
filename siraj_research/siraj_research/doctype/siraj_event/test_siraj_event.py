# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt

from __future__ import annotations

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from siraj_research.api import entity_profile, relationship_profile


class TestSirajEvent(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		if not frappe.db.exists("Data Group", "GD"):
			frappe.get_doc({"doctype": "Data Group", "group_name": "GD"}).insert(
				ignore_permissions=True
			)
		if not frappe.db.exists("Workflow State", "Draft"):
			frappe.get_doc(
				{"doctype": "Workflow State", "workflow_state_name": "Draft"}
			).insert(ignore_permissions=True)

	def _event_type(self) -> str:
		existing = frappe.db.get_value("Event Type", {}, "name")
		if existing:
			return existing
		return (
			frappe.get_doc(
				{
					"doctype": "Event Type",
					"code": "siraj_evt_test_type",
					"label_en": "Test Event Type",
					"label_ar": "نوع حدث اختباري",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def _rel_type(self) -> str:
		existing = frappe.db.get_value("Relationship Type", {}, "name")
		if existing:
			return existing
		return (
			frappe.get_doc(
				{
					"doctype": "Relationship Type",
					"code": "siraj_evt_test_rel",
					"label_en": "Test Rel Type",
					"label_ar": "نوع علاقة اختباري",
					"direction": "Directed",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def _ensure_role_user(self, email: str, role: str) -> str:
		if not frappe.db.exists("Role", role):
			frappe.get_doc(
				{"doctype": "Role", "role_name": role, "desk_access": 1}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Role", "Group Member"):
			frappe.get_doc(
				{"doctype": "Role", "role_name": "Group Member", "desk_access": 1}
			).insert(ignore_permissions=True)
		if frappe.db.exists("User", email):
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)
		for up in frappe.get_all("User Permission", filters={"user": email}, pluck="name"):
			frappe.delete_doc("User Permission", up, force=True, ignore_permissions=True)
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": role,
				"enabled": 1,
				"user_type": "System User",
				"send_welcome_email": 0,
				"roles": [{"role": "Group Member"}, {"role": role}],
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": user.name,
				"allow": "Data Group",
				"for_value": "GD",
				"apply_to_all_doctypes": 1,
			}
		).insert(ignore_permissions=True)
		return user.name

	def test_doctype_schema_and_removed_legacy_fields(self):
		meta = frappe.get_meta("Siraj Event")
		self.assertEqual(meta.autoname, "naming_series:")
		self.assertEqual(meta.title_field, "display_name")
		self.assertIsNone(meta.get_field("title"))
		self.assertIsNone(meta.get_field("linked_place"))
		for fn in (
			"naming_series",
			"display_name",
			"title_ar",
			"title_en",
			"start_date",
			"start_date_as_stated",
			"start_date_precision",
			"end_date",
			"end_date_as_stated",
			"end_date_precision",
			"place",
			"place_as_stated",
			"status",
			"significance",
			"image",
			"image_url",
			"image_alt",
			"researcher_notes",
			"workflow_state",
			"data_group",
		):
			self.assertIsNotNone(meta.get_field(fn), f"Missing field {fn} on Siraj Event")
		self.assertEqual(meta.get_field("start_date").fieldtype, "Datetime")
		self.assertEqual(meta.get_field("end_date").fieldtype, "Datetime")
		self.assertEqual(meta.get_field("researcher_notes").permlevel, 1)
		self.assertEqual(meta.get_field("workflow_state").default, "Draft")
		self.assertFalse(frappe.db.exists("DocType", "Research Event"))

	def test_display_name_computation_and_title_requirement(self):
		frappe.set_user("Administrator")
		et = self._event_type()

		# Neither title_ar nor title_en -> rejected by controller
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Siraj Event",
					"event_type": et,
					"data_group": "GD",
				}
			).insert(ignore_permissions=True)

		# Arabic-only -> valid, display_name == title_ar
		ar_only = frappe.get_doc(
			{
				"doctype": "Siraj Event",
				"title_ar": "مؤتمر الأرشيف الإقليمي",
				"event_type": et,
				"data_group": "GD",
			}
		).insert(ignore_permissions=True)
		try:
			self.assertTrue(ar_only.name.startswith("EVT-"))
			self.assertEqual(ar_only.display_name, "مؤتمر الأرشيف الإقليمي")
			self.assertEqual(ar_only.workflow_state, "Draft")
		finally:
			frappe.delete_doc("Siraj Event", ar_only.name, force=True, ignore_permissions=True)

		# English + Arabic -> display_name prefers title_en
		both = frappe.get_doc(
			{
				"doctype": "Siraj Event",
				"title_ar": "ندوة التوثيق",
				"title_en": "Documentation Symposium",
				"event_type": et,
				"data_group": "GD",
			}
		).insert(ignore_permissions=True)
		try:
			self.assertEqual(both.display_name, "Documentation Symposium")
		finally:
			frappe.delete_doc("Siraj Event", both.name, force=True, ignore_permissions=True)

	def test_researcher_notes_permlevel_1_across_entity_and_relationship_profiles(self):
		frappe.set_user("Administrator")
		et = self._event_type()
		rt = self._rel_type()
		viewer = self._ensure_role_user("siraj-evt-viewer@example.com", "SIRAJ Viewer")
		researcher = self._ensure_role_user("siraj-evt-researcher@example.com", "SIRAJ Researcher")
		reviewer = self._ensure_role_user("siraj-evt-reviewer@example.com", "SIRAJ Reviewer")

		evt = frappe.get_doc(
			{
				"doctype": "Siraj Event",
				"title_en": "Permlevel Probe Event",
				"title_ar": "حدث اختبار الصلاحيات",
				"event_type": et,
				"researcher_notes": "EVT-PERMLEVEL1-REVIEWER-SECRET",
				"data_group": "GD",
			}
		).insert(ignore_permissions=True)
		person = frappe.get_doc(
			{
				"doctype": "Person",
				"name_en": "Permlevel Probe Person",
				"name_ar": "شخص اختبار الصلاحيات",
				"data_group": "GD",
			}
		).insert(ignore_permissions=True)
		rel = frappe.get_doc(
			{
				"doctype": "Relationship",
				"relationship_type": rt,
				"subject_type": "Person",
				"subject": person.name,
				"object_type": "Siraj Event",
				"object": evt.name,
				"researcher_notes": "REL-EVT-PERMLEVEL1-REVIEWER-SECRET",
				"data_group": "GD",
			}
		).insert(ignore_permissions=True)
		try:
			for denied_user in (viewer, researcher):
				frappe.set_user(denied_user)
				ent_json = json.dumps(
					entity_profile.get_entity_profile("Siraj Event", evt.name), default=str
				)
				rel_json = json.dumps(
					relationship_profile.get_relationship_profile(rel.name), default=str
				)
				self.assertNotIn("EVT-PERMLEVEL1-REVIEWER-SECRET", ent_json)
				self.assertNotIn("REL-EVT-PERMLEVEL1-REVIEWER-SECRET", rel_json)

			frappe.set_user(reviewer)
			rev_ent_json = json.dumps(
				entity_profile.get_entity_profile("Siraj Event", evt.name), default=str
			)
			rev_rel_json = json.dumps(
				relationship_profile.get_relationship_profile(rel.name), default=str
			)
			self.assertIn("EVT-PERMLEVEL1-REVIEWER-SECRET", rev_ent_json)
			self.assertIn("REL-EVT-PERMLEVEL1-REVIEWER-SECRET", rev_rel_json)
		finally:
			frappe.set_user("Administrator")
			frappe.delete_doc("Relationship", rel.name, force=True, ignore_permissions=True)
			frappe.delete_doc("Person", person.name, force=True, ignore_permissions=True)
			frappe.delete_doc("Siraj Event", evt.name, force=True, ignore_permissions=True)
			for email in (viewer, researcher, reviewer):
				for up in frappe.get_all("User Permission", filters={"user": email}, pluck="name"):
					frappe.delete_doc("User Permission", up, force=True, ignore_permissions=True)
				if frappe.db.exists("User", email):
					frappe.delete_doc("User", email, force=True, ignore_permissions=True)

	def test_delete_research_event_patch_fresh_existing_nonempty_and_developer_mode(self):
		from siraj_research.patches.v2_1 import delete_research_event

		frappe.set_user("Administrator")
		# (a) Fresh site where Research Event does not exist -> clean no-op
		self.assertFalse(frappe.db.exists("DocType", "Research Event"))
		self.assertFalse(frappe.db.table_exists("Research Event", cached=False))
		delete_research_event.execute()

		# Simulate (b) an already-migrated site that still has the Research Event DocType + table,
		# and (c) developer_mode=1 (verifying delete_doc does not crash when controller files were already removed),
		# plus row-refusal guard when tabResearch Event holds rows.
		prev_dev_mode = frappe.conf.get("developer_mode")
		prev_in_migrate = getattr(frappe.flags, "in_migrate", False)
		try:
			frappe.conf.developer_mode = 1
			frappe.flags.in_migrate = False
			custom_dt = frappe.get_doc(
				{
					"doctype": "DocType",
					"name": "Research Event",
					"module": "Siraj Research",
					"custom": 1,
					"fields": [{"fieldname": "title_ar", "fieldtype": "Data", "label": "Title"}],
					"permissions": [{"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1}],
				}
			).insert(ignore_permissions=True)
			# Flip custom=0 in DB so delete_doc exercises the standard-DocType developer_mode=1 branch
			# (frappe/model/delete_doc.py:100-113 -> delete_controllers catches OSError when folder is gone).
			frappe.db.set_value("DocType", custom_dt.name, "custom", 0, update_modified=False)
			self.assertTrue(frappe.db.table_exists("Research Event", cached=False))

			# Non-empty table must fail loudly and leave both row and DocType intact!
			frappe.db.sql(
				"INSERT INTO `tabResearch Event` (`name`, `docstatus`, `idx`) VALUES (%s, 0, 0)",
				("EVT-LEGACY-0001",),
			)
			with self.assertRaises(RuntimeError):
				delete_research_event.execute()
			self.assertTrue(frappe.db.exists("DocType", "Research Event"))
			self.assertTrue(frappe.db.table_exists("Research Event", cached=False))

			# Empty table -> deletes DocType metadata AND drops tabResearch Event cleanly
			# even with developer_mode=1 and in_migrate=False.
			frappe.db.sql("DELETE FROM `tabResearch Event`")
			delete_research_event.execute()
			self.assertFalse(frappe.db.exists("DocType", "Research Event"))
			self.assertFalse(frappe.db.table_exists("Research Event", cached=False))
		finally:
			frappe.conf.developer_mode = prev_dev_mode
			frappe.flags.in_migrate = prev_in_migrate
			if frappe.db.exists("DocType", "Research Event"):
				frappe.delete_doc("DocType", "Research Event", force=True, ignore_permissions=True)
			if frappe.db.table_exists("Research Event", cached=False):
				frappe.db.transaction_writes = 0
				frappe.db.sql("DROP TABLE IF EXISTS `tabResearch Event`")
			frappe.clear_cache()
