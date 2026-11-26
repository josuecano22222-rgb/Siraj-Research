# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
import frappe
from frappe import _
from frappe.model.document import Document

from siraj_research.report_access import readable_rows
from siraj_research.utils.military import (
	ancestors,
	descendants,
	military_person,
	subtree_personnel,
)


class MilitaryUnit(Document):
	def before_delete(self):
		from siraj_research.utils.relationship_delete import block_delete_if_referenced

		block_delete_if_referenced(self.doctype, self.name)

	def validate(self):
		self.validate_parent()
		self.validate_parent()
		self.validate_commander()
		self.validate_personnel()
		self.validate_holdings()
		self.subtree_personnel = self.compute_subtree_personnel()

	def validate_parent(self):
		parent_unit = self.get("parent_unit")
		if parent_unit and self.name in ancestors(self.doctype, parent_unit):
			frappe.throw(_("A military unit cannot be its own ancestor."), frappe.ValidationError)

	def validate_holdings(self):
		"""015_military_org.sql UNIQUE(unit_id, armament_id): one row per pair.

		Frappe has no composite unique, so the pair is checked over the parent's own
		child rows — which is also why it cannot live on the child controller.
		"""
		seen = set()
		for row in self.get("armaments") or []:
			if not row.armament:
				continue
			if row.armament in seen:
				frappe.throw(
					_("Row {0}: {1} is already held by this unit.").format(row.idx, row.armament),
					title=_("Duplicate armament"),
				)
			seen.add(row.armament)
			if (row.quantity or 0) <= 0:
				frappe.throw(_("Row {0}: quantity must be greater than zero.").format(row.idx))

	def on_trash(self):
		"""rules.delete blocked by dependents — Frappe blocks Links, not child rows
		and not a tree's children, so both are checked here."""
		if frappe.db.exists(self.doctype, {"parent_unit": self.name}):
			frappe.throw(_("{0} still has subordinate units.").format(self.name), title=_("Cannot delete"))
		for doctype in ("Operational Deployment", "Mission", "Training Exercise", "Command Appointment"):
			if frappe.db.exists(doctype, {"unit": self.name}):
				frappe.throw(
					_("{0} still has {1} records.").format(self.name, _(doctype)), title=_("Cannot delete")
				)

	def validate_commander(self):
		"""rules.check_commander_person — only a military person may command a unit."""
		commander = self.get("commander")
		if commander and not military_person(commander):
			frappe.throw(
				_("The commander of {0} must be a person of the Military category.").format(self.name),
				title=_("Invalid commander"),
			)

	def validate_personnel(self):
		if (self.get("direct_personnel") or 0) < 0:
			frappe.throw(_("Direct personnel cannot be negative."))

	def compute_subtree_personnel(self) -> int:
		"""Use submitted direct personnel plus persisted subordinate personnel."""
		if self.is_new():
			return int(self.get("direct_personnel") or 0)
		return (
			subtree_personnel(self.doctype, self.name)
			- int(frappe.db.get_value(self.doctype, self.name, "direct_personnel") or 0)
			+ int(self.get("direct_personnel") or 0)
		)

	def update_ancestor_totals(self, *parents):
		# Both old and new chains matter when a unit is reparented.
		updated = set()
		for parent in parents:
			for ancestor in ancestors(self.doctype, parent):
				if ancestor not in updated:
					frappe.db.set_value(
						self.doctype,
						ancestor,
						"subtree_personnel",
						subtree_personnel(self.doctype, ancestor),
						update_modified=False,
					)
					updated.add(ancestor)

	def on_update(self):
		before = self.get_doc_before_save()
		self.update_ancestor_totals(self.get("parent_unit"), before.get("parent_unit") if before else None)

	def after_delete(self):
		self.update_ancestor_totals(self.get("parent_unit"))

	@frappe.whitelist()
	def get_descendants(self):
		self.check_permission("read")
		names = descendants(self.doctype, self.name)
		if not names:
			return []
		return [row["name"] for row in readable_rows(self.doctype, [], {"name": ["in", names]})]
