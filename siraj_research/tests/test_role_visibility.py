# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
"""Four-role DocPerm matrix and API boundary tests (Phase 4).

The four SIRAJ roles come from ``setup/install.py::ROLES`` and the shipped
DocPerm rows on every DocType (hooks.py references the same matrix). Every
behavioural test runs as an **explicit non-Administrator user** holding only
that one role; users are created once for the class and removed afterwards:

* declared-vs-effective matrix scan over all shipped DocTypes;
* behavioural create / write / delete / export boundaries per role;
* field-level (permlevel 1) visibility through the audit history;
* the Audit, Explorer and relationship-graph API gates.

Run with:
    bench --site frappe.com run-tests --module siraj_research.tests.test_role_visibility
"""

from __future__ import annotations

import glob
import json
import os

import frappe
from frappe.tests.utils import FrappeTestCase

from siraj_research.api.audit import collect_history, document_history
from siraj_research.api.map_relations import get_entity_network
from siraj_research.setup.install import ROLES
from siraj_research.visualization import record_detail, relationship_data

PROBE_TAG = "Role Probe"

# Created once per class (first use), removed in tearDownClass.
_CREATED_USERS: dict[str, str] = {}


def _app_doctype_jsons() -> list[dict]:
	base = frappe.get_app_path("siraj_research", "siraj_research", "doctype")
	out = []
	for path in sorted(glob.glob(os.path.join(base, "*", "*.json"))):
		with open(path, encoding="utf-8") as handle:
			out.append(json.load(handle))
	return out


class RoleUser:
	"""Act as a freshly created user holding exactly one SIRAJ role."""

	def __init__(self, role: str):
		self.role = role
		self.email = _CREATED_USERS.get(role, "")

	def __enter__(self) -> str:
		if not self.email:
			slug = self.role.lower().replace(" ", "-")
			email = f"siraj-role-test-{slug}@example.com"
			if not frappe.db.exists("Role", self.role):
				frappe.get_doc(
					{"doctype": "Role", "role_name": self.role, "desk_access": 1}
				).insert(ignore_permissions=True)
			if frappe.db.exists("User", email):
				frappe.delete_doc("User", email, force=True, ignore_permissions=True)
			user = frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": f"Role test {self.role}",
					"user_type": "System User",
					"enabled": 1,
				}
			)
			user.insert(ignore_permissions=True)
			user.add_roles(self.role)
			frappe.db.commit()
			_CREATED_USERS[self.role] = email
			self.email = email
		frappe.set_user(self.email)
		return self.email

	def __exit__(self, *exc) -> None:
		frappe.set_user("Administrator")


def _probe_person() -> str:
	doc = frappe.get_doc(
		{
			"doctype": "Person",
			"display_name": PROBE_TAG,
			"name_en": PROBE_TAG,
			"name_ar": PROBE_TAG,
		}
	)
	doc.insert(ignore_permissions=True)
	# One permlevel-0 change and one permlevel-1 (researcher_notes) change
	# in a single save: audit tests assert exactly this split per role.
	doc.name_variants = "role probe variant"
	doc.researcher_notes = "role probe restricted notes"
	# ignore_version=False: frappe sets ignore_version=flags.in_test by
	# default, so plain saves during tests never write Version rows.
	doc.save(ignore_permissions=True, ignore_version=False)
	frappe.db.commit()
	return doc.name


class TestRoleVisibility(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		for role in ROLES:
			if not frappe.db.exists("Role", role):
				frappe.get_doc(
					{"doctype": "Role", "role_name": role, "desk_access": 1}
				).insert(ignore_permissions=True)
		frappe.db.commit()
		cls.person = _probe_person()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		if cls.person and frappe.db.exists("Person", cls.person):
			try:
				frappe.delete_doc(
					"Person", cls.person, force=True, ignore_permissions=True
				)
			except Exception:
				pass
		for email in list(_CREATED_USERS.values()):
			try:
				if frappe.db.exists("User", email):
					frappe.delete_doc(
						"User", email, force=True, ignore_permissions=True
					)
			except Exception:
				pass
		_CREATED_USERS.clear()
		frappe.db.commit()

	# -- declared vs effective matrix ----------------------------------

	def test_every_declared_role_permission_matches_effective(self):
		"""Shipped DocPerm rows must equal what the framework enforces.

		Covers read for every role/DocType pair — including absent rows
		(declared False) — and the write/create/delete/export flags for
		Person, the highest-traffic DocType.
		"""
		check_flags = {"read", "write", "create", "delete", "export"}
		for doctype in _app_doctype_jsons():
			name = doctype.get("name")
			if not name or doctype.get("istable"):
				continue
			# Frappe's get_role_permissions only considers permlevel-0 rows
			# and ORs them per ptype (Person has a second permlevel-1 row per
			# role that must not shadow the base row).
			rows = doctype.get("permissions") or []
			ptypes = sorted(check_flags) if name == "Person" else ["read"]
			for role in ROLES:
				applicable = [
					row
					for row in rows
					if row.get("role") == role and not (row.get("permlevel") or 0)
				]
				with RoleUser(role):
					for ptype in ptypes:
						declared = any(bool(row.get(ptype)) for row in applicable)
						effective = frappe.has_permission(name, ptype)
						self.assertEqual(
							effective,
							declared,
							f"{role} {ptype} on {name}: declared {declared} "
							f"!= effective {effective}",
						)

	# -- behavioural boundaries ----------------------------------------

	def test_viewer_is_read_only_with_export(self):
		with RoleUser("SIRAJ Viewer"):
			self.assertTrue(frappe.has_permission("Person", "read"))
			self.assertTrue(frappe.has_permission("Person", "export"))
			self.assertFalse(frappe.has_permission("Person", "create"))
			self.assertFalse(frappe.has_permission("Person", "write"))
			self.assertFalse(frappe.has_permission("Person", "delete"))
			# No ignore_permissions: the denial under test IS the check.
			with self.assertRaises(frappe.PermissionError):
				frappe.get_doc(
					{
						"doctype": "Person",
						"display_name": "viewer insert",
						"name_en": "viewer insert",
						"name_ar": "viewer insert",
					}
				).insert()
			person = frappe.get_doc("Person", self.person)
			person.name_variants = "viewer write attempt"
			with self.assertRaises(frappe.PermissionError):
				person.save()
			with self.assertRaises(frappe.PermissionError):
				frappe.delete_doc("Person", self.person, force=True)

	def test_researcher_cannot_delete(self):
		with RoleUser("SIRAJ Researcher"):
			self.assertTrue(frappe.has_permission("Person", "create"))
			self.assertTrue(frappe.has_permission("Person", "write"))
			self.assertFalse(frappe.has_permission("Person", "delete"))
			with self.assertRaises(frappe.PermissionError):
				frappe.delete_doc("Person", self.person, force=True)

	def test_administrator_can_delete(self):
		with RoleUser("SIRAJ Administrator"):
			self.assertTrue(frappe.has_permission("Person", "delete"))
			# Dedicated record so the shared probe stays intact.
			temp = frappe.get_doc(
				{
					"doctype": "Person",
					"display_name": f"{PROBE_TAG} temp",
					"name_en": f"{PROBE_TAG} temp",
					"name_ar": f"{PROBE_TAG} temp",
				}
			)
			temp.insert(ignore_permissions=True)
			frappe.delete_doc("Person", temp.name, force=True, ignore_permissions=True)
			self.assertFalse(frappe.db.exists("Person", temp.name))

	# -- audit history field-level boundary ----------------------------

	def test_audit_history_filters_permlevel_one_per_role(self):
		# Reviewer holds permlevel-1 read/write on Person.researcher_notes;
		# Viewer and Researcher hold no permlevel-1 rows at all.
		with RoleUser("SIRAJ Reviewer"):
			reviewer = collect_history("Person", self.person, limit=10)
			reviewer_fields = {
				c["field"] for e in reviewer["history"] for c in e["changes"]
			}
			self.assertIn("researcher_notes", reviewer_fields)
			self.assertIn("name_variants", reviewer_fields)
		for role in ("SIRAJ Viewer", "SIRAJ Researcher"):
			with RoleUser(role):
				result = collect_history("Person", self.person, limit=10)
				fields = {c["field"] for e in result["history"] for c in e["changes"]}
				self.assertIn(
					"name_variants", fields, f"{role} must see permlevel-0 diffs"
				)
				self.assertNotIn(
					"researcher_notes",
					fields,
					f"{role} must not see permlevel-1 diffs",
				)

	def test_personal_identifiers_require_reviewer_level(self):
		person = frappe.get_doc("Person", self.person)
		fields = ("personal_id_number", "phone_numbers", "current_residence")
		for role in ("SIRAJ Viewer", "SIRAJ Researcher"):
			with RoleUser(role):
				for field in fields:
					self.assertFalse(
						person.has_permlevel_access_to(field),
						f"{role} must not access Person.{field}",
					)
		with RoleUser("SIRAJ Reviewer"):
			for field in fields:
				self.assertTrue(
					person.has_permlevel_access_to(field),
					f"Reviewer must access Person.{field}",
				)

	def test_audit_history_denies_unreadable_doctype(self):
		# Evidence is a child DocType without Viewer rows: no history access.
		with RoleUser("SIRAJ Viewer"):
			with self.assertRaises(frappe.PermissionError):
				collect_history("Evidence", "any-row-name")
		# Unknown DocTypes are rejected outright.
		with RoleUser("SIRAJ Administrator"):
			with self.assertRaises(frappe.ValidationError):
				document_history("Not A Doctype", "x")

	# -- Explorer / graph / audit API gates ----------------------------

	def test_explorer_and_graph_endpoints_for_viewer(self):
		with RoleUser("SIRAJ Viewer"):
			payload = relationship_data()
			self.assertIn("nodes", payload)
			self.assertIn("edges", payload)
			self.assertTrue(
				all("doctype" in n and "name" in n for n in payload["nodes"])
			)
			network = get_entity_network("Person", self.person, depth=1)
			self.assertIn("nodes", network)
			self.assertTrue(
				any(n.get("name") == self.person for n in network["nodes"]),
				"seed record must appear in its own network",
			)
			detail = record_detail("Person", self.person)
			self.assertEqual(detail["name"], self.person)
			history = document_history("Person", self.person, limit=5)
			self.assertIn("history", history)

	def test_graph_and_history_do_not_leak_unreadable_records(self):
		with RoleUser("SIRAJ Viewer"):
			payload = relationship_data()
			self.assertNotIn(
				"Evidence", {n.get("doctype") for n in payload["nodes"]}
			)
			with self.assertRaises(frappe.PermissionError):
				collect_history("Evidence", "any-row-name")
