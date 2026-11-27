# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
import frappe
from frappe import _
from frappe.model.document import Document

from siraj_research.utils.display_name import set_display_name

#: app/geo_chain.py ADMIN_CHAIN — each level must sit under the level before it
ADMIN_CHAIN = [
	("country", "Country", None),
	("governorate", "Governorate", "country"),
	("district", "District", "governorate"),
	("municipality", "Municipality", "district"),
	("village", "Village", "municipality"),
	("community", "Community", "village"),
]


class Place(Document):
	def before_validate(self):
		set_display_name(self, "name_en", "name_ar")

	def on_trash(self):
		from siraj_research.utils.relationship_delete import block_delete_if_referenced

		block_delete_if_referenced(self.doctype, self.name)

	def validate(self):
		self.validate_admin_chain()
		self.validate_admin_chain()

	def validate_admin_chain(self):
		"""app/geo_chain.expected_parent — the six-level chain, checked end to end.

		               `link_filters` already offer only the children of the level above
		this is the
		               server-side guarantee for records created by API, import or patch.
		"""
		for fieldname, doctype, parent_field in ADMIN_CHAIN:
			value = self.get(fieldname)
			if not value or not parent_field:
				continue
			declared = self.get(parent_field)
			actual = frappe.db.get_value(doctype, value, parent_field)
			if declared and actual and actual != declared:
				frappe.throw(
					_("{0} {1} belongs to {2} {3}, not {4}.").format(
						_(doctype), value, _(parent_field), actual, declared
					),
					title=_("Administrative chain broken"),
				)
