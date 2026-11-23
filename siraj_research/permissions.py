"""Fail-closed row-level isolation for group-scoped DocTypes."""

from __future__ import annotations

import frappe
from frappe import _

DATA_GROUP_DOCTYPE = "Data Group"
DATA_GROUP_FIELD = "data_group"


def _user(user: str | None = None) -> str:
	return user or frappe.session.user or "Guest"


def get_user_data_group(user: str | None = None) -> str | None:
	"""Return the user's Data Group User Permission, or None.

	The setup creates exactly one such permission per member. ``get_value`` is
	intentional: this helper is called in request permission paths and never
	bypasses permissions with SQL, ``get_all`` or ``ignore_permissions``.
	"""
	user = _user(user)
	if user in ("Administrator", "Guest"):
		return None
	return frappe.db.get_value(
		"User Permission",
		{"user": user, "allow": DATA_GROUP_DOCTYPE},
		"for_value",
	)


def get_permission_query_conditions(user: str | None = None) -> str:
	"""SQL condition used by lists, reports, searches, exports and counts."""
	user = _user(user)
	if user == "Administrator":
		return ""
	data_group = get_user_data_group(user)
	if not data_group:
		return "1=0"
	# The unqualified field makes this one hook reusable for every scoped DocType.
	# Frappe's list query has the protected DocType as its primary table.
	return f"`{DATA_GROUP_FIELD}` = {frappe.db.escape(data_group)}"


def has_permission(doc, user: str | None = None, permission_type: str | None = None):
	"""Deny cross-group/scope-less documents; defer positive role checks to Frappe.

	Returning ``None`` is deny-only hook semantics. A blank group is permitted
	on a new document only so ``before_validate`` can stamp it.
	"""
	user = _user(user)
	if user == "Administrator":
		return None
	data_group = get_user_data_group(user)
	if not data_group:
		return False
	# Any client value is accepted only until before_validate rewrites it.
	if doc.is_new() and permission_type == "create":
		return None
	if doc.get(DATA_GROUP_FIELD) != data_group:
		return False
	return None


def stamp_and_lock_data_group(doc, method: str | None = None) -> None:
	"""Server-stamp new rows and prohibit changing the immutable group."""
	if doc.doctype == DATA_GROUP_DOCTYPE:
		return

	if doc.is_new():
		if frappe.session.user == "Administrator":
			return
		data_group = get_user_data_group()
		if not data_group:
			frappe.throw(_("A Data Group membership is required."), frappe.PermissionError)
		doc.set(DATA_GROUP_FIELD, data_group)
		return

	original = frappe.db.get_value(doc.doctype, doc.name, DATA_GROUP_FIELD)
	if doc.get(DATA_GROUP_FIELD) != original:
		frappe.throw(_("Data Group cannot be changed after creation."), frappe.PermissionError)
