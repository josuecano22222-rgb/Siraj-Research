# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from siraj_research.utils.display_name import set_relationship_display_name
from siraj_research.utils.relationship_rules import duplicate_key, pair_allowed


class Relationship(Document):
	def before_validate(self):
		set_relationship_display_name(self)

	def validate(self):
		# Never trust a value supplied by a browser or API client for this
		# read-only field. Link validation still handles a missing type.
		symmetric = False
		hierarchical = False
		if self.relationship_type:
			symmetric = bool(frappe.db.get_value("Relationship Type", self.relationship_type, "is_symmetric"))
			hierarchical = bool(frappe.db.get_value("Relationship Type", self.relationship_type, "is_hierarchical"))
			if frappe.db.get_value("Relationship Type", self.relationship_type, "is_symmetric") is not None:
				self.direction = "Symmetric" if symmetric else "Directed"

		self.validate_allowed_pair(symmetric, hierarchical)
		self.validate_duplicate(symmetric)

	def _allowed_pairs(self) -> list[tuple[str, str]]:
		"""Return the (subject_doctype, object_doctype) rows for this type.

		Empty when the type has no `allowed_pairs` child rows yet — during the
		consolidation migration (step 3 seeds them) such a type is unconstrained,
		preserving the pre-consolidation behaviour so existing edges keep saving.
		"""
		if not self.relationship_type:
			return []
		return [
			(row.subject_doctype, row.object_doctype)
			for row in frappe.get_all(
				"Relationship Type Allowed Pair",
				filters={"parenttype": "Relationship Type", "parent": self.relationship_type},
				fields=["subject_doctype", "object_doctype"],
			)
		]

	def validate_allowed_pair(self, symmetric: bool, hierarchical: bool) -> None:
		"""Enforce the Relationship Type's allowed (subject, object) pairs (§3.2).

		- Pair membership: the row ``(subject_type, object_type)`` must exist in
		  the type's allowed-pairs child table. Symmetric types accept either
		  orientation. Skipped when the type defines no pairs (migration window).
		- Self-links: a non-hierarchical type cannot link a record to itself.
		"""
		allowed = self._allowed_pairs()
		if allowed:
			if not pair_allowed(
				allowed, self.subject_type, self.object_type, symmetric=symmetric
			):
				frappe.throw(
					frappe._(
						"Relationship type '{0}' does not allow a {1} → {2} link."
					).format(self.relationship_type, self.subject_type, self.object_type),
					frappe.ValidationError,
					title=frappe._("Pair not allowed"),
				)

			# Self-links are rejected once the type is constrained (pairs
			# seeded). During the migration window an unconstrained type keeps
			# the pre-consolidation behaviour so existing edges keep saving.
			if not hierarchical and self.subject_type == self.object_type and self.subject == self.object:
				frappe.throw(
					frappe._("A non-hierarchical relationship cannot link a record to itself."),
					frappe.ValidationError,
					title=frappe._("Self link"),
				)

	def validate_duplicate(self, symmetric: bool) -> None:
		"""Reject a duplicate edge for the same Relationship Type (§8).

		Directed types reject a repeat of the exact ordered pair; symmetric
		types normalize the endpoints so ``(A→B)`` and ``(B→A)`` are one edge.
		"""
		if not self.relationship_type or not self.subject or not self.object:
			return
		allowed = self._allowed_pairs()
		if not allowed:
			return  # unconstrained type (migration window): no duplicate rule yet

		key = duplicate_key(
			self.relationship_type,
			self.subject_type,
			self.subject,
			self.object_type,
			self.object,
			symmetric=symmetric,
		)

		if symmetric:
			# Fetch by type + endpoint names, then compare normalized keys so
			# both orientations of a symmetric edge are detected.
			existing = frappe.get_all(
				"Relationship",
				filters={
					"relationship_type": self.relationship_type,
					"name": ["!=", self.name or ""],
				},
				fields=["name", "relationship_type", "subject_type", "subject", "object_type", "object"],
				limit_page_length=0,
			)
			for row in existing:
				if duplicate_key(
					row.relationship_type,
					row.subject_type,
					row.subject,
					row.object_type,
					row.object,
					symmetric=True,
				) == key:
					frappe.throw(
						frappe._(
							"A symmetric relationship for '{0}' → '{1}' already exists."
						).format(self.subject, self.object),
						frappe.ValidationError,
						title=frappe._("Duplicate relationship"),
					)
		else:
			exists = frappe.db.exists(
				"Relationship",
				{
					"relationship_type": self.relationship_type,
					"subject_type": self.subject_type,
					"subject": self.subject,
					"object_type": self.object_type,
					"object": self.object,
					"name": ["!=", self.name or ""],
				},
			)
			if exists:
				frappe.throw(
					frappe._(
						"A relationship '{0}' → '{1}' already exists for this type."
					).format(self.subject, self.object),
					frappe.ValidationError,
					title=frappe._("Duplicate relationship"),
				)
