# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestMilitaryServiceStatus(FrappeTestCase):
	def test_doctype_loads(self):
		"""The DocType exists, its JSON is valid and its controller imports."""
		self.assertTrue(frappe.get_meta("Military Service Status").fields)
