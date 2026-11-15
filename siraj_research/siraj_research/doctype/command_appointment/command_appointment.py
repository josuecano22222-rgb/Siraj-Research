# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
import frappe
from frappe import _
from frappe.model.document import Document

from siraj_research.utils.military import military_person


class CommandAppointment(Document):
	def validate(self):
		self.validate_commander()
		self.validate_dates()
		self.validate_overlap()

	def validate_commander(self):
		"""rules.check_commander_person — the appointee must be a military person."""
		if not military_person(self.commander):
			frappe.throw(_("{0} is not a person of the Military category.").format(self.commander),
			             title=_("Invalid commander"))

	def validate_dates(self):
		if self.relieved_date and self.assigned_date and self.relieved_date < self.assigned_date:
			frappe.throw(_("The relieved date cannot precede the assigned date."))

	def validate_overlap(self):
		"""rules.check_assignment — no two overlapping appointments for one (unit, role).

		An empty `relieved_date` means the appointment is open-ended, so it overlaps
		anything that starts before "forever".
		"""
		filters = {
			"unit": self.unit,
			"role": self.role,
			"name": ("!=", self.name),
			"docstatus": ("<", 2),
		}
		for other in frappe.get_all(
			self.doctype, filters=filters,
			fields=["name", "commander", "assigned_date", "relieved_date"],
		):
			if self.assigned_date and other.relieved_date and \
					other.relieved_date < self.assigned_date:
				continue
			if self.relieved_date and other.assigned_date and \
					self.relieved_date < other.assigned_date:
				continue
			frappe.throw(
				_("{0} is already {1} of {2} from {3} to {4}.").format(
					other.commander, other.role, self.unit,
					other.assigned_date, other.relieved_date or _("now"),
				),
				title=_("Overlapping appointment"),
			)
