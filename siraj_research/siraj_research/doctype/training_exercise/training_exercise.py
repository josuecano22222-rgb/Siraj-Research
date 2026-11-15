# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
import frappe
from frappe import _
from frappe.model.document import Document

from siraj_research.utils.military import subtree_personnel


class TrainingExercise(Document):
	def validate(self):
		self.set_duration()
		self.validate_capacity()

	def set_duration(self):
		"""rules.check_training — duration is *derived* from the inclusive day span."""
		# `frappe.utils.date_diff` is inclusive-exclusive, so add one for the span
		if self.start_date and self.end_date:
			self.duration_days = frappe.utils.date_diff(self.end_date, self.start_date) + 1

	def validate_capacity(self):
		"""Participant count cannot exceed the unit's real personnel total."""
		if not (self.unit and self.participant_count):
			return
		capacity = subtree_personnel("Military Unit", self.unit)
		if capacity and self.participant_count > capacity:
			frappe.throw(
				_("{0} participants exceeds {1}'s total of {2}.").format(
					self.participant_count, self.unit, capacity),
				title=_("Over capacity"),
			)
