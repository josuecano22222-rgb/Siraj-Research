# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
import frappe
from frappe import _
from frappe.utils import getdate
from frappe.model.document import Document

from siraj_research.utils.display_name import set_display_name

from siraj_research.utils.military import SERVICE_STATUS_TRANSITIONS, check_transition


class Person(Document):
	def before_validate(self):
		set_display_name(self, 'name_en', 'name_ar')

	def validate(self):
		self.validate_military()
		self.validate_service_status()
		self.validate_leadership_assessments()

	def validate_military(self):
		"""The six military attributes only apply to a military person (migration 020)."""
		if self.category == "Military":
			return
		if self.service_status or self.rank_title:
			frappe.msgprint(
				_("Rank and service status are only meaningful for a person of the "
				  "Military category."), indicator="orange", alert=True)

	def validate_service_status(self):
		"""app/schemas.py SERVICE_STATUS_TRANSITIONS, plus the source's retire guard.

		`_person_service_guard` in `app/military/service.py` refuses to retire a person
		while a current command appointment is open: the evidence lives on another
		DocType, which is why this cannot be a field rule.
		"""
		before = self.get_doc_before_save()
		if not before or before.service_status == self.service_status:
			return
		check_transition(SERVICE_STATUS_TRANSITIONS, "service_status",
		                 before.service_status, self.service_status, "Person")
		if self.service_status == "Retired":
			open_appointment = frappe.db.get_value(
				"Command Appointment",
				{"commander": self.name, "is_current": 1, "relieved_date": ("is", "not set")},
				"name",
			)
			if open_appointment:
				frappe.throw(
					_("{0} still holds a current appointment ({1}). Relieve them first.")
					.format(self.name, open_appointment),
					title=_("Cannot retire"),
				)

	def validate_leadership_assessments(self):
		"""rules.check_trait — an assessment needs a basis and cannot be future-dated."""
		today = getdate()
		for row in self.get("leadership_assessments") or []:
			if not (row.assessed_by or row.assessed_at or row.evidence_note):
				frappe.throw(
					_("Row {0}: a leadership assessment needs a basis — an assessor, a "
					  "date or evidence.").format(row.idx),
					title=_("Assessment without a basis"),
				)
			if row.assessed_at and getdate(row.assessed_at) > today:
				frappe.throw(_("Row {0}: an assessment cannot be dated in the future.")
				             .format(row.idx))
