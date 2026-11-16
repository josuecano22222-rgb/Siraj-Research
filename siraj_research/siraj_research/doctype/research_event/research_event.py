# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from siraj_research.utils.display_name import set_display_name


class ResearchEvent(Document):
	def before_validate(self):
		set_display_name(self, "title_en", "title_ar")
