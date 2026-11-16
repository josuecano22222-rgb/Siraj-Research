# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
import frappe
from frappe import _
from frappe.model.document import Document

from siraj_research.utils.military import MISSION_TRANSITIONS, check_transition, is_ancestor


class Mission(Document):
	def validate(self):
		self.validate_transition()
		self.validate_end_date()
		self.validate_deployment()

	def validate_transition(self):
		"""vocab.MISSION_TRANSITIONS — Planned → Ongoing → Executed, or Cancelled."""
		if self.is_new():
			return
		before = self.get_doc_before_save()
		check_transition(
			MISSION_TRANSITIONS, "status", before.status if before else None, self.status, "Mission"
		)

	def validate_end_date(self):
		if self.status == "Executed" and not self.end_date:
			frappe.throw(_("An executed mission needs an end date."))

	def validate_deployment(self):
		"""rules.check_mission — the deployment must belong to this unit or an ancestor."""
		if not self.deployment:
			return
		dep_unit = frappe.db.get_value("Operational Deployment", self.deployment, "unit")
		if not dep_unit:
			return
		if not is_ancestor("Military Unit", dep_unit, self.unit):
			frappe.throw(
				_("Deployment {0} belongs to {1}, which is not {2} or one of its ancestors.").format(
					self.deployment, dep_unit, self.unit
				),
				title=_("Deployment outside the chain of command"),
			)
