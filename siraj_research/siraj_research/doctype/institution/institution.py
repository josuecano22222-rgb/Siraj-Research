# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from siraj_research.utils.display_name import set_display_name


class Institution(Document):
	def before_validate(self):
		set_display_name(self, 'name_en', 'name_ar')
