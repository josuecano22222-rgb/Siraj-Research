# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
"""Bench-side behaviour of the Person Family tab (needs a real site).

Run with:
    bench --site frappe.com run-tests --module siraj_research.tests.test_person_family

The pure JSON/helper contracts live in the repo-root tests/test_person_family.py;
this module covers what only a live controller can: hidden-value preservation,
validation throws, sibling autofill and the stored family_summary.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.tests.utils import FrappeTestCase

from siraj_research.utils.family import build_family_summary


class TestPersonFamily(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("Data Group", "GD"):
			frappe.get_doc({"doctype": "Data Group", "group_name": "GD"}).insert(
				ignore_permissions=True
			)

	def make_person(self, **kwargs) -> frappe.Document:
		payload = {
			"doctype": "Person",
			"name_ar": "اختبار بيانات العائلة",
			"birth_date": "1950-01-01",
			"marital_status": "Single",
			"data_group": "GD",
		}
		payload.update(kwargs)
		doc = frappe.get_doc(payload)
		doc.insert()
		return doc

	def test_profile_is_saveable_without_optional_person_details(self):
		doc = frappe.get_doc({"doctype": "Person", "data_group": "GD"})
		doc.insert()
		doc.reload()
		self.assertFalse(doc.name_ar)
		self.assertFalse(doc.birth_date_as_stated)
		self.assertFalse(doc.birthplace)
		self.assertFalse(doc.birthplace_as_stated)
		self.assertFalse(doc.current_residence)
		self.assertFalse(doc.nationality)
		self.assertFalse(doc.gender)
		self.assertFalse(doc.personal_id_number)
		self.assertFalse(doc.phone_numbers)

	def test_custom_fields_allow_labelled_rows_without_values(self):
		doc = self.make_person(
			additional_fields=[
				{"field_label": "Preferred alias", "field_value": "Alias A"},
				{"field_label": "Unknown custom value"},
			]
		)
		doc.reload()
		self.assertEqual(doc.additional_fields[0].field_label, "Preferred alias")
		self.assertEqual(doc.additional_fields[0].field_value, "Alias A")
		self.assertEqual(doc.additional_fields[1].field_label, "Unknown custom value")
		self.assertFalse(doc.additional_fields[1].field_value)

	def test_duplicate_custom_field_labels_are_rejected_case_insensitively(self):
		with self.assertRaises(frappe.ValidationError):
			self.make_person(
				additional_fields=[
					{"field_label": "Reference"},
					{"field_label": " reference "},
				]
			)

	# -- marital status gates the UI, never the data ----------------------

	def test_single_status_keeps_hidden_family_data(self):
		"""Switching to Single must hide sections but never clear values."""
		doc = self.make_person(
			marital_status="Married",
			spouse_name="أمينة الحاج",
			marriage_date="1972-06-01",
			children=[{"child_name": "أحمد", "birth_date": "1973-05-05"}],
			siblings=[{"sibling_name": "فاطمة", "relation": "Sister"}],
		)
		doc.reload()
		self.assertEqual(doc.spouse_name, "أمينة الحاج")
		self.assertEqual(len(doc.children), 1)

		doc.marital_status = "Single"
		doc.save()
		doc.reload()
		# Hidden, not cleared.
		self.assertEqual(doc.marital_status, "Single")
		self.assertEqual(doc.spouse_name, "أمينة الحاج")
		self.assertEqual(len(doc.children), 1)
		self.assertEqual(len(doc.siblings), 1)

		doc.marital_status = "Married"
		doc.save()
		doc.reload()
		self.assertEqual(doc.spouse_name, "أمينة الحاج")
		self.assertEqual(doc.children[0].child_name, "أحمد")

	# -- validation throws -------------------------------------------------

	def test_future_marriage_date_throws(self):
		future = frappe.utils.add_years(frappe.utils.today(), 3)
		with self.assertRaises(frappe.ValidationError):
			self.make_person(
				marital_status="Married",
				spouse_name="X",
				marriage_date=future,
			)

	def test_child_birth_before_person_throws(self):
		with self.assertRaises(frappe.ValidationError):
			self.make_person(
				marital_status="Married",
				spouse_name="X",
				children=[{"child_name": "أحمد", "birth_date": "1940-01-01"}],
			)

	def test_grandchild_through_child_must_be_recorded(self):
		with self.assertRaises(frappe.ValidationError):
			self.make_person(
				marital_status="Married",
				spouse_name="X",
				children=[{"child_name": "أحمد", "birth_date": "1973-05-05"}],
				grandchildren=[
					{"grandchild_name": "سامي", "through_child": "غير موجود"}
				],
			)

	def test_sibling_cannot_link_self(self):
		doc = self.make_person()
		doc.append("siblings", {"sibling_name": "شقيق", "person": doc.name})
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	# -- derived fields ----------------------------------------------------

	def test_is_grandparent_and_summary_recomputed_on_save(self):
		doc = self.make_person(
			marital_status="Married",
			spouse_name="أمينة الحاج",
			children=[
				{"child_name": "أحمد", "birth_date": "1973-05-05", "number_of_children": 2},
				{"child_name": "سعاد", "birth_date": "1975-02-02", "number_of_children": 0},
			],
			grandchildren=[
				{"grandchild_name": "سامي", "through_child": "أحمد", "birth_date": "2000-01-01"},
				{"grandchild_name": "ليلى", "through_child": "أحمد", "birth_date": "2003-01-01"},
			],
			siblings=[{"sibling_name": "فاطمة", "relation": "Sister"}],
		)
		doc.reload()
		self.assertEqual(doc.is_grandparent, 1)
		expected = build_family_summary(
			{
				"marital_status": doc.marital_status,
				"spouse_name": doc.spouse_name,
				"children_count": 2,
				"grandchildren_count": 2,
				"siblings_count": 1,
			},
			translate=_,
		)
		self.assertEqual(doc.family_summary, expected)
		self.assertIn(" · ", doc.family_summary)

	def test_single_person_summary_is_bare(self):
		doc = self.make_person(siblings=[{"sibling_name": "فاطمة"}])
		doc.reload()
		self.assertEqual(doc.is_grandparent, 0)
		expected = build_family_summary(
			{
				"marital_status": "Single",
				"spouse_name": None,
				"children_count": 0,
				"grandchildren_count": 0,
				"siblings_count": 1,
			},
			translate=_,
		)
		self.assertEqual(doc.family_summary, expected)

	# -- sibling convenience link ------------------------------------------

	def test_sibling_name_autofills_from_linked_person(self):
		brother = self.make_person(name_ar="الشقيق المرتبط")
		doc = self.make_person()
		doc.append("siblings", {"relation": "Brother", "person": brother.name})
		doc.save()
		doc.reload()
		self.assertEqual(doc.siblings[0].sibling_name, brother.display_name)

	def test_sibling_autofill_does_not_overwrite_stated_name(self):
		brother = self.make_person(name_ar="الشقيق المرتبط")
		doc = self.make_person()
		doc.append(
			"siblings",
			{"sibling_name": "الاسم كما ورد", "relation": "Brother", "person": brother.name},
		)
		doc.save()
		doc.reload()
		self.assertEqual(doc.siblings[0].sibling_name, "الاسم كما ورد")

	# -- search integration -------------------------------------------------

	def test_family_summary_reaches_desk_search(self):
		"""The stored summary is part of search_fields — filter on it."""
		spouse_name = "زوجة الاختبار الفريدة"
		doc = self.make_person(
			marital_status="Married",
			spouse_name=spouse_name,
		)
		doc.reload()
		self.assertIn(spouse_name, doc.family_summary)
		hits = frappe.get_all(
			"Person",
			filters={"name": doc.name, "family_summary": ["like", f"%{spouse_name}%"]},
			pluck="name",
		)
		self.assertEqual(hits, [doc.name])
