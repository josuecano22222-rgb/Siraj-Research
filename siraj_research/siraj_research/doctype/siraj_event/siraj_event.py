# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from siraj_research.utils.display_name import set_display_name


class SirajEvent(Document):
	def before_validate(self):
		set_display_name(self, "title_en", "title_ar")

	def validate(self):
		if not (str(self.get("title_ar") or "").strip() or str(self.get("title_en") or "").strip()):
			frappe.throw(
				_("At least one of Title (Arabic) or Title (English) is required."),
				frappe.ValidationError,
			)
