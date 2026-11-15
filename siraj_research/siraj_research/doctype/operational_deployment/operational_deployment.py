# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
import frappe
from frappe import _
from frappe.model.document import Document

from siraj_research.utils.military import DEPLOYMENT_TRANSITIONS, check_transition


class OperationalDeployment(Document):
	def validate(self):
		self.validate_transition()
		self.validate_end_date()
		self.validate_one_current()

	def validate_transition(self):
		"""vocab.DEPLOYMENT_TRANSITIONS — Planned → Active/Suspended → Completed."""
		if self.is_new():
			return
		before = self.get_doc_before_save()
		check_transition(DEPLOYMENT_TRANSITIONS, "status",
		                 before.status if before else None,
		                 self.status, "Operational Deployment")

	def validate_end_date(self):
		"""rules.check_deployment — a Completed deployment needs an end date."""
		if self.status == "Completed" and not self.end_date:
			frappe.throw(_("A completed deployment needs an end date."),
			             title=_("Missing end date"))
		if self.end_date and self.start_date and self.end_date < self.start_date:
			frappe.throw(_("The end date cannot precede the start date."))

	def validate_one_current(self):
		"""rules.check_deployment — at most one current deployment per unit."""
		if not self.is_current:
			return
		other = frappe.db.get_value(
			self.doctype,
			{"unit": self.unit, "is_current": 1, "name": ("!=", self.name)},
			"name",
		)
		if other:
			frappe.throw(
				_("{0} already has a current deployment ({1}). Clear it first.").format(
					self.unit, other),
				title=_("Duplicate current deployment"),
			)
		frappe.db.set_value("Military Unit", self.unit, "current_deployment", self.name)
