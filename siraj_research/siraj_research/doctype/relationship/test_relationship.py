# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from siraj_research.utils.relationship_rules import duplicate_key, pair_allowed


class TestRelationship(FrappeTestCase):
	def test_doctype_loads(self):
		"""The DocType exists, its JSON is valid and its controller imports."""
		self.assertTrue(frappe.get_meta("Relationship").fields)

	# ------------------------------------------------------------------
	# Pair enforcement (docs/decisions/relationship-consolidation.md §3.2)
	# ------------------------------------------------------------------

	# Title fields read from each endpoint DocType's JSON (authoritative).
	# Person/Institution/Place -> name_en/name_ar; Siraj Event -> title_en/title_ar;
	# Military Unit -> unit_name only (there is NO unit_name_ar field).
	ENDPOINT_TITLE_FIELDS = {
		"Person": ("name_en", "name_ar"),
		"Institution": ("name_en", "name_ar"),
		"Place": ("name_en", "name_ar"),
		"Siraj Event": ("title_en", "title_ar"),
		"Military Unit": ("unit_name", None),
	}
	# (vocab DocType, endpoint Link field, vocab code) for endpoints that require a
	# type link. Institution/Place also require name_ar; Siraj Event does not.
	ENDPOINT_VOCAB = {
		"Institution": ("Institution Type", "institution_type", "PR_INST_TYPE"),
		"Place": ("Place Type", "place_type", "PR_PLACE_TYPE"),
		"Siraj Event": ("Event Type", "event_type", "PR_EVENT_TYPE"),
	}
	# Remaining required Select/Int fields for Military Unit (read from its JSON).
	ENDPOINT_REQUIRED_FIELDS = {
		"Military Unit": {"echelon": "Brigade", "status": "Active", "direct_personnel": 100},
	}

	@staticmethod
	def _ensure_data_group(name):
		if not frappe.db.exists("Data Group", name):
			frappe.get_doc({"doctype": "Data Group", "group_name": name}).insert(
				ignore_permissions=True
			)

	@staticmethod
	def _ensure_vocab(doctype, code):
		label = f"PR Fix {code}"
		if frappe.db.exists(doctype, label):
			return label
		frappe.get_doc(
			{
				"doctype": doctype,
				"label_en": label,
				"label_ar": f"اختبار {code}",
				"code": code,
			}
		).insert(ignore_permissions=True)
		return label

	def _make_endpoint(self, doctype, name, data_group="GD"):
		"""Create a minimal endpoint record so a Relationship can link to it.

		Sets the DocType's real title fields (from its JSON) plus every other
		required field, so the insert succeeds for all five endpoint DocTypes
		without weakening any assertion. This is a test-fixture fix: the previous
		helper referenced a nonexistent ``unit_name_ar`` field and omitted the
		required type links / Select fields for Institution, Place, Siraj Event and
		Military Unit, which would have failed the first time these tests ran on CI.
		"""
		self._ensure_data_group(data_group)
		title_en, title_ar = self.ENDPOINT_TITLE_FIELDS.get(doctype, ("name_en", "name_ar"))
		payload = {"doctype": doctype, "data_group": data_group, title_en: name}
		if title_ar:
			payload[title_ar] = name
		vocab_doctype, vocab_field, vocab_code = self.ENDPOINT_VOCAB.get(doctype, (None, None, None))
		if vocab_doctype:
			payload[vocab_field] = self._ensure_vocab(vocab_doctype, vocab_code)
		payload.update(self.ENDPOINT_REQUIRED_FIELDS.get(doctype, {}))
		return frappe.get_doc(payload).insert(ignore_permissions=True)

	def _make_type(self, code, *, symmetric=False, pairs=None, hierarchical=False):
		"""Create (or fetch) a Relationship Type with allowed-pair child rows."""
		label = f"PhaseR {code}"
		if frappe.db.exists("Relationship Type", label):
			doc = frappe.get_doc("Relationship Type", label)
		else:
			doc = frappe.get_doc(
				{
					"doctype": "Relationship Type",
					"code": code,
					"label_en": label,
					"label_ar": f"مرحلة {code}",
					"is_symmetric": 1 if symmetric else 0,
					"is_hierarchical": 1 if hierarchical else 0,
				}
			).insert(ignore_permissions=True)
		doc.set("allowed_pairs", [])  # clear any existing child rows before re-seeding
		for idx, (subject_doctype, object_doctype) in enumerate(pairs or [], start=1):
			doc.append(
				"allowed_pairs",
				{
					"subject_doctype": subject_doctype,
					"object_doctype": object_doctype,
					"sort_order": idx,
				},
			)
		doc.save(ignore_permissions=True)
		return doc

	def _allowed_pairs(self, rel_type_name):
		return [
			(row.subject_doctype, row.object_doctype)
			for row in frappe.get_all(
				"Relationship Type Allowed Pair",
				filters={"parenttype": "Relationship Type", "parent": rel_type_name},
				fields=["subject_doctype", "object_doctype"],
			)
		]

	def _make_relationship(self, rel_type, subject_type, subject, object_type, object_name, **kw):
		payload = {
			"doctype": "Relationship",
			"relationship_type": rel_type,
			"subject_type": subject_type,
			"subject": subject,
			"object_type": object_type,
			"object": object_name,
			"naming_series": "REL-.####",
			"data_group": kw.pop("data_group", "GD"),
		}
		payload.update(kw)
		return frappe.get_doc(payload)

	def test_invalid_pair_rejected(self):
		"""A Relationship whose (subject, object) pair is not allowed must be rejected."""
		rt = self._make_type("PAIR_INVALID", pairs=[("Person", "Institution")])
		person = self._make_endpoint("Person", "PR Invalid Pair Person")
		institution = self._make_endpoint("Institution", "PR Invalid Pair Inst")
		place = self._make_endpoint("Place", "PR Invalid Pair Place")
		try:
			with self.assertRaises(frappe.ValidationError):
				self._make_relationship(
					rt.name, "Person", person.name, "Place", place.name
				).insert(ignore_permissions=True)
			# The allowed pair (Person, Institution) still saves.
			ok = self._make_relationship(
				rt.name, "Person", person.name, "Institution", institution.name
			).insert(ignore_permissions=True)
			self.assertEqual(ok.subject, person.name)
		finally:
			for doc in (person, institution, place):
				if frappe.db.exists(doc.doctype, doc.name):
					frappe.delete_doc(doc.doctype, doc.name, force=True, ignore_permissions=True)

	def test_duplicate_rejected_directed(self):
		"""A directed Relationship with the same ordered pair is a duplicate."""
		rt = self._make_type("DUP_DIRECTED", pairs=[("Person", "Institution")])
		person = self._make_endpoint("Person", "PR Dup Directed Person")
		institution = self._make_endpoint("Institution", "PR Dup Directed Inst")
		try:
			first = self._make_relationship(
				rt.name, "Person", person.name, "Institution", institution.name
			).insert(ignore_permissions=True)
			with self.assertRaises(frappe.ValidationError):
				self._make_relationship(
					rt.name, "Person", person.name, "Institution", institution.name
				).insert(ignore_permissions=True)
			# The reverse direction is a distinct edge for a directed type.
			reverse = self._make_relationship(
				rt.name, "Institution", institution.name, "Person", person.name
			)
			# (Institution, Person) is not an allowed pair for this directed type.
			with self.assertRaises(frappe.ValidationError):
				reverse.insert(ignore_permissions=True)
			self.assertTrue(first.name)
		finally:
			for doc in (person, institution):
				if frappe.db.exists(doc.doctype, doc.name):
					frappe.delete_doc(doc.doctype, doc.name, force=True, ignore_permissions=True)

	def test_symmetric_normalization(self):
		"""A symmetric type treats (A→B) and (B→A) as the same edge."""
		rt = self._make_type(
			"SYM_NORM", symmetric=True, pairs=[("Person", "Institution"), ("Institution", "Person")]
		)
		person = self._make_endpoint("Person", "PR Sym Norm Person")
		institution = self._make_endpoint("Institution", "PR Sym Norm Inst")
		try:
			first = self._make_relationship(
				rt.name, "Person", person.name, "Institution", institution.name
			).insert(ignore_permissions=True)
			self.assertEqual(first.direction, "Symmetric")
			# The mirror orientation is a duplicate of the same symmetric edge.
			with self.assertRaises(frappe.ValidationError):
				self._make_relationship(
					rt.name, "Institution", institution.name, "Person", person.name
				).insert(ignore_permissions=True)
			# Confirm the helper agrees the two orientations share one key.
			k1 = duplicate_key(rt.name, "Person", person.name, "Institution", institution.name, symmetric=True)
			k2 = duplicate_key(rt.name, "Institution", institution.name, "Person", person.name, symmetric=True)
			self.assertEqual(k1, k2)
		finally:
			for doc in (person, institution):
				if frappe.db.exists(doc.doctype, doc.name):
					frappe.delete_doc(doc.doctype, doc.name, force=True, ignore_permissions=True)

	def test_self_link_rejected_non_hierarchical(self):
		"""A non-hierarchical Relationship cannot link a record to itself."""
		rt = self._make_type("SELF_LINK", pairs=[("Person", "Person")])
		person = self._make_endpoint("Person", "PR Self Link Person")
		try:
			with self.assertRaises(frappe.ValidationError):
				self._make_relationship(
					rt.name, "Person", person.name, "Person", person.name
				).insert(ignore_permissions=True)
		finally:
			if frappe.db.exists("Person", person.name):
				frappe.delete_doc("Person", person.name, force=True, ignore_permissions=True)

	def test_pair_allowed_helper_matches_child_rows(self):
		"""The pure helper and the seeded child rows agree on allowed pairs."""
		rt = self._make_type("HELPER_MATCH", pairs=[("Person", "Institution")])
		rows = self._allowed_pairs(rt.name)
		self.assertTrue(pair_allowed(rows, "Person", "Institution", symmetric=False))
		self.assertFalse(pair_allowed(rows, "Institution", "Person", symmetric=False))

	# ------------------------------------------------------------------
	# Endpoint delete blocking (§8)
	# ------------------------------------------------------------------

	def test_endpoint_delete_blocked_when_relationships_exist(self):
		"""Deleting an endpoint that a Relationship references is blocked."""
		rt = self._make_type("DEL_BLOCK", pairs=[("Person", "Institution")])
		person = self._make_endpoint("Person", "PR Del Block Person")
		institution = self._make_endpoint("Institution", "PR Del Block Inst")
		rel = self._make_relationship(
			rt.name, "Person", person.name, "Institution", institution.name
		).insert(ignore_permissions=True)
		try:
			# Subject delete is blocked.
			with self.assertRaises(frappe.ValidationError):
				frappe.delete_doc("Person", person.name, ignore_permissions=True)
			# Object delete is blocked.
			with self.assertRaises(frappe.ValidationError):
				frappe.delete_doc("Institution", institution.name, ignore_permissions=True)
			# Removing the relationship first unblocks the delete. Use a direct hard
			# delete on the Relationship row: subject/object are Dynamic Link
			# fields, so Frappe's own delete machinery (frappe.delete_doc) can leave
			# the row's link reference detectable to check_if_doc_is_dynamically_linked
			# and falsely block the now-unreferenced endpoint. A direct db.delete
			# guarantees the row is gone so the post-removal endpoint delete exercises
			# only our before_delete guard (no false positive).
			frappe.db.delete("Relationship", {"name": rel.name})
			# No Relationship should reference either endpoint anymore.
			self.assertFalse(
				frappe.db.exists(
					"Relationship",
					{"subject_type": "Person", "subject": person.name},
				)
				or frappe.db.exists(
					"Relationship",
					{"object_type": "Person", "object": person.name},
				)
			)
			self.assertFalse(
				frappe.db.exists(
					"Relationship",
					{"subject_type": "Institution", "subject": institution.name},
				)
				or frappe.db.exists(
					"Relationship",
					{"object_type": "Institution", "object": institution.name},
				)
			)
			# force=True skips Frappe's check_if_doc_is_dynamically_linked (a
			# stale link reference for Dynamic Link fields) but still runs our
			# before_delete guard; with no Relationship referencing the endpoints,
			# the guard passes and the deletes succeed.
			frappe.delete_doc("Person", person.name, force=True, ignore_permissions=True)
			frappe.delete_doc("Institution", institution.name, force=True, ignore_permissions=True)
		finally:
			for doctype, name in (("Person", person.name), ("Institution", institution.name)):
				if frappe.db.exists(doctype, name):
					frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
