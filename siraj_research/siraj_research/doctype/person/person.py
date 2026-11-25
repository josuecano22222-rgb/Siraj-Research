# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from siraj_research.utils.display_name import set_display_name
from siraj_research.utils.family import build_family_summary, derive_is_grandparent
from siraj_research.utils.military import SERVICE_STATUS_TRANSITIONS, check_transition


class Person(Document):
	def before_validate(self):
		set_display_name(self, "name_en", "name_ar")

	def validate(self):
		self.validate_military()
		self.validate_service_status()
		self.validate_leadership_assessments()
		self.validate_family()
		self.validate_additional_fields()

	def validate_military(self):
		"""The six military attributes only apply to a military person (migration 020)."""
		if self.category == "Military":
			return
		if self.service_status or self.rank_title:
			frappe.msgprint(
				_("Rank and service status are only meaningful for a person of the Military category."),
				indicator="orange",
				alert=True,
			)

	def validate_service_status(self):
		"""app/schemas.py SERVICE_STATUS_TRANSITIONS, plus the source's retire guard.

		`_person_service_guard` in `app/military/service.py` refuses to retire a person
		while a current command appointment is open:
		    the evidence lives on another
		DocType, which is why this cannot be a field rule.
		"""
		before = self.get_doc_before_save()
		if not before or before.service_status == self.service_status:
			return
		check_transition(
			SERVICE_STATUS_TRANSITIONS, "service_status", before.service_status, self.service_status, "Person"
		)
		if self.service_status == "Retired":
			open_appointment = frappe.db.get_value(
				"Command Appointment",
				{"commander": self.name, "is_current": 1, "relieved_date": ("is", "not set")},
				"name",
			)
			if open_appointment:
				frappe.throw(
					_("{0} still holds a current appointment ({1}). Relieve them first.").format(
						self.name, open_appointment
					),
					title=_("Cannot retire"),
				)

	def validate_leadership_assessments(self):
		"""rules.check_trait — an assessment needs a basis and cannot be future-dated."""
		today = getdate()
		for row in self.get("leadership_assessments") or []:
			if not (row.assessed_by or row.assessed_at or row.evidence_note):
				frappe.throw(
					_(
						"Row {0}: a leadership assessment needs a basis — an assessor, a date or evidence."
					).format(row.idx),
					title=_("Assessment without a basis"),
				)
			if row.assessed_at and getdate(row.assessed_at) > today:
				frappe.throw(_("Row {0}: an assessment cannot be dated in the future.").format(row.idx))

	def validate_additional_fields(self):
		"""Keep per-person custom labels clear and unambiguous."""
		seen = set()
		for row in self.get("additional_fields") or []:
			label = (row.field_label or "").strip()
			if not label:
				frappe.throw(_("Row {0}: a custom field needs a label.").format(row.idx))
			row.field_label = label
			key = label.casefold()
			if key in seen:
				frappe.throw(
					_("Row {0}: custom field label '{1}' is already used on this Person.").format(
						row.idx, label
					),
					title=_("Duplicate custom field label"),
				)
			seen.add(key)

	def validate_family(self):
		"""Family tab: date sanity, person-exclusive rules, derived fields.

		Spouse/children/grandchildren are embedded rows — they never Link to
		another Person, so a person's family stays exclusive to their record.
		Siblings may optionally link (a sibling can be a subject in their own
		right). Marital status only gates the UI: hidden values are kept.
		"""
		today = getdate()
		if self.marriage_date and getdate(self.marriage_date) > today:
			frappe.throw(_("Marriage date cannot be in the future."))
		if (self.marriage_date and self.birth_date
				and getdate(self.marriage_date) < getdate(self.birth_date)):
			frappe.throw(_("Marriage date cannot precede the person's birth date."))
		if self.spouse_birth_date and getdate(self.spouse_birth_date) > today:
			frappe.throw(_("Spouse date of birth cannot be in the future."))

		children = self.get("children") or []
		child_births = {}
		for row in children:
			if row.child_name:
				child_births[row.child_name] = row.birth_date
			if not row.birth_date:
				continue
			bd = getdate(row.birth_date)
			if bd > today:
				frappe.throw(
					_("Row {0}: a child's date of birth cannot be in the future.").format(row.idx),
					title=_("Family data"),
				)
			if self.birth_date and bd < getdate(self.birth_date):
				frappe.throw(
					_("Row {0}: a child cannot be born before the person.").format(row.idx),
					title=_("Family data"),
				)

		child_names = set(child_births)
		for row in self.get("grandchildren") or []:
			if row.through_child and row.through_child not in child_names:
				frappe.throw(
					_("Row {0}: 'Through' must name one of this person's children.").format(row.idx),
					title=_("Family data"),
				)
			if row.birth_date:
				bd = getdate(row.birth_date)
				if bd > today:
					frappe.throw(
						_("Row {0}: a grandchild's date of birth cannot be in the future.").format(row.idx),
						title=_("Family data"),
					)
				if self.birth_date and bd < getdate(self.birth_date):
					frappe.throw(
						_("Row {0}: a grandchild cannot be born before the person.").format(row.idx),
						title=_("Family data"),
					)
				parent_birth = child_births.get(row.through_child)
				if parent_birth and bd < getdate(parent_birth):
					frappe.throw(
						_("Row {0}: a grandchild cannot be born before their parent.").format(row.idx),
						title=_("Family data"),
					)

		for row in self.get("siblings") or []:
			if row.person and self.name and row.person == self.name:
				frappe.throw(
					_("Row {0}: a person cannot be listed as their own sibling.").format(row.idx),
					title=_("Family data"),
				)
			if not row.sibling_name and row.person:
				# Convenience only: fill the visible name from the linked Person when readable.
				if frappe.has_permission("Person", "read", doc=row.person):
					row.sibling_name = (
						frappe.db.get_value("Person", row.person, "display_name")
						or frappe.db.get_value("Person", row.person, "name_en")
						or row.person
					)

		# Derived, recomputed on every save so every surface agrees.
		self.is_grandparent = derive_is_grandparent(
			row.number_of_children for row in children
		)
		self.family_summary = build_family_summary(
			{
				"marital_status": self.marital_status,
				"spouse_name": self.spouse_name,
				"children_count": len(children),
				"grandchildren_count": len(self.get("grandchildren") or []),
				"siblings_count": len(self.get("siblings") or []),
			},
			translate=_,
		)
