# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt

from frappe.tests.utils import FrappeTestCase


class TestLeadershipQualityAssessment(FrappeTestCase):
	def test_doctype_loads(self):
		"""The DocType exists, its JSON is valid and its controller imports."""
		self.assertTrue(frappe.get_meta("Leadership Quality Assessment").fields)
