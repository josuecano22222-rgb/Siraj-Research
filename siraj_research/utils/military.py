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


def descendants(doctype: str, name: str) -> list[str]:
	"""Every descendant of a NestedSet node, by name.

	NestedSet stores `lft`/`rgt`; the subtree of a node is the range between them,
	which is what the source computed recursively in `rules.subtree_ids()`.
	"""
	lft, rgt = frappe.db.get_value(doctype, name, ["lft", "rgt"])
	if lft is None:
		return []
	return frappe.get_all(
		doctype, filters={"lft": (">", lft), "rgt": ("<", rgt)},
		pluck="name", order_by="lft asc",
	)


def is_ancestor(doctype: str, ancestor: str, name: str) -> bool:
	"""True when `ancestor` is `name` or one of its ancestors."""
	if ancestor == name:
		return True
	return ancestor in set(
		frappe.get_all(
			doctype, filters={"lft": ("<=", frappe.db.get_value(doctype, name, "lft")),
			                  "rgt": (">=", frappe.db.get_value(doctype, name, "rgt"))},
			pluck="name",
		)
	)


def subtree_personnel(doctype: str, name: str) -> int:
	"""S direct_personnel over a node and its descendants (`rules.descendant_personnel`)."""
	names = [name, *descendants(doctype, name)]
	if not names:
		return 0
	total = frappe.db.get_all(
		doctype, filters={"name": ("in", names)}, fields=["sum(direct_personnel) as total"]
	)
	return int((total[0].total if total else 0) or 0)


def military_person(person: str | None) -> bool:
	"""A commander must be a person of the military category (`rules.check_commander_person`)."""
	if not person:
		return True
	return frappe.db.get_value("Person", person, "category") == "Military"
