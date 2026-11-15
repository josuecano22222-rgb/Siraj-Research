# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
"""Shared rules for the military DocTypes.

Everything here is a *state machine* or a *tree helper*, i.e. the parts of the
source's `app/military/vocab.py` and `app/military/rules.py` that cannot be
expressed as DocType metadata. Kept in one module so each transition table is
defined exactly once.
"""
from __future__ import annotations

import frappe
from frappe import _

#: `app/military/vocab.py` DEPLOYMENT_TRANSITIONS  an empty tuple is a terminal state
DEPLOYMENT_TRANSITIONS: dict[str, tuple[str, ...]] = {
	"Planned": ("Active", "Suspended"),
	"Active": ("Completed", "Suspended"),
	"Suspended": ("Active", "Completed"),
	"Completed": (),
}

#: `app/military/vocab.py` MISSION_TRANSITIONS
MISSION_TRANSITIONS: dict[str, tuple[str, ...]] = {
	"Planned": ("Ongoing", "Cancelled"),
	"Ongoing": ("Executed", "Cancelled"),
	"Executed": (),
	"Cancelled": (),
}

#: `app/schemas.py` SERVICE_STATUS_TRANSITIONS  Retired is terminal
SERVICE_STATUS_TRANSITIONS: dict[str, tuple[str, ...]] = {
	"Active": ("Reserve", "Retired"),
	"Reserve": ("Active", "Retired"),
	"Retired": (),
}


def check_transition(table: dict[str, tuple[str, ...]], field: str, old: str | None,
                     new: str | None, label: str) -> None:
	"""Refuse a status change the source's transition table does not allow."""
	if not old or old == new:
		return
	allowed = table.get(old, ())
	if new not in allowed:
		frappe.throw(
			_("{0}: {1} cannot become {2}. Allowed from {3}: {4}.").format(
				_(label), old, new, old,
				", ".join(allowed) if allowed else _("nothing  this state is terminal"),
			),
			title=_("Invalid status change"),
		)


def _check_unit_tree(doctype: str) -> None:
	if doctype != "Military Unit":
		frappe.throw(_("Unsupported military hierarchy type"), frappe.ValidationError)


def ancestors(doctype: str, name: str | None) -> list[str]:
	"""Walk actual parent links, rejecting a cycle rather than looping forever."""
	_check_unit_tree(doctype)
	result, seen = [], set()
	while name:
		if name in seen:
			frappe.throw(_("The military unit hierarchy contains a cycle."), frappe.ValidationError)
		seen.add(name)
		result.append(name)
		name = frappe.db.get_value(doctype, name, "parent_unit")
	return result


def descendants(doctype: str, name: str) -> list[str]:
	"""Return descendants using parent_unit, without assuming nested-set indexes."""
	_check_unit_tree(doctype)
	seen, found, frontier = {name}, [], [name]
	while frontier:
		children = frappe.get_all(
			doctype, filters={"parent_unit": ("in", frontier)},
			pluck="name", order_by="name asc", limit_page_length=0,
		)
		frontier = []
		for child in children:
			if child in seen:
				frappe.throw(_("The military unit hierarchy contains a cycle."), frappe.ValidationError)
			seen.add(child)
			found.append(child)
			frontier.append(child)
	return found


def is_ancestor(doctype: str, ancestor: str, name: str) -> bool:
	"""True when ancestor is the unit itself or is in its parent chain."""
	return ancestor in ancestors(doctype, name)


def subtree_personnel(doctype: str, name: str) -> int:
	"""Sum direct personnel over the persisted parent-linked subtree."""
	names = [name, *descendants(doctype, name)]
	total = frappe.get_all(
		doctype, filters={"name": ("in", names)}, fields=["sum(direct_personnel) as total"],
		limit_page_length=0,
	)
	return int((total[0].total if total else 0) or 0)


def military_person(person: str | None) -> bool:
	"""A commander must be a person of the military category (`rules.check_commander_person`)."""
	if not person:
		return True
	return frappe.db.get_value("Person", person, "category") == "Military"
