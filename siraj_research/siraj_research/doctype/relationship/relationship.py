# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Relationship(Document):
	def validate(self):
		# Never trust a value supplied by a browser or API client for this
		# read-only field. Link validation still handles a missing type.
		if self.relationship_type:
			symmetric = frappe.db.get_value("Relationship Type", self.relationship_type, "is_symmetric")
			if symmetric is not None:
				self.direction = "Symmetric" if symmetric else "Directed"
