"""Fail-closed row-level isolation for group-scoped DocTypes."""

from __future__ import annotations

import frappe
from frappe import _

DATA_GROUP_DOCTYPE = "Data Group"
DATA_GROUP_FIELD = "data_group"
OFFICIAL_ROLE = "SIRAJ Official"


def _user(user: str | None = None) -> str:
	return user or frappe.session.user or "Guest"


def is_official(user: str | None = None) -> bool:
	"""Return whether the user is explicitly appointed to oversee both sections."""
	user = _user(user)
	return user != "Guest" and OFFICIAL_ROLE in frappe.get_roles(user)


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
	if is_official(user):
		# Officials oversee both sections, but blank legacy rows remain
		# Administrator-only as required by the fail-closed policy.
		return f"COALESCE(`{DATA_GROUP_FIELD}`, '') != ''"
	data_group = get_user_data_group(user)
	if not data_group:
		return "1=0"
	# The unqualified field makes this one hook reusable for every scoped DocType.
	# Frappe's list query has the protected DocType as its primary table.
	return f"`{DATA_GROUP_FIELD}` = {frappe.db.escape(data_group)}"


def has_permission(
	doc,
	user: str | None = None,
	permission_type: str | None = None,
	ptype: str | None = None,
	**kwargs,
):
	"""Deny cross-group/scope-less documents; defer positive role checks to Frappe.

	Returning ``None`` is deny-only hook semantics. Frappe evaluates native User
	Permissions before ``before_validate`` during insert, so the create check also
	rewrites any client-supplied group before native Link permission evaluation.
	The doc event remains the authoritative stamp and immutable-group guard.
	"""
	user = _user(user)
	if user == "Administrator":
		return None
	if is_official(user):
		if doc.is_new() and (permission_type or ptype) == "create":
			return None
		return None if doc.get(DATA_GROUP_FIELD) else False
	data_group = get_user_data_group(user)
	if not data_group:
		return False

	permission_type = permission_type or ptype
	if doc.is_new() and permission_type == "create":
		doc.set(DATA_GROUP_FIELD, data_group)
		return None
	if doc.get(DATA_GROUP_FIELD) != data_group:
		return False
	return None


def stamp_and_lock_data_group(doc, method: str | None = None) -> None:
	"""Server-stamp new rows and prohibit changing the immutable group."""
	if doc.doctype == DATA_GROUP_DOCTYPE:
		return

	if doc.is_new():
		if frappe.session.user == "Administrator" or is_official():
			return
		data_group = get_user_data_group()
		if not data_group:
			frappe.throw(_("A Data Group membership is required."), frappe.PermissionError)
		doc.set(DATA_GROUP_FIELD, data_group)
		return

	original = frappe.db.get_value(doc.doctype, doc.name, DATA_GROUP_FIELD)
	if doc.get(DATA_GROUP_FIELD) != original:
		frappe.throw(_("Data Group cannot be changed after creation."), frappe.PermissionError)


def _collect_scoped_link_targets(
	container,
	scoped_set: frozenset[str],
	targets_by_dt: dict[str, set[str]],
) -> None:
	meta = frappe.get_meta(container.doctype)
	if not meta:
		return
	for df in meta.fields:
		ft = df.fieldtype
		if ft == "Link":
			target_dt = df.options
			if target_dt in scoped_set:
				val = container.get(df.fieldname)
				if val:
					targets_by_dt.setdefault(target_dt, set()).add(str(val))
		elif ft == "Dynamic Link":
			type_field = df.options
			target_dt = container.get(type_field) if type_field else None
			if target_dt in scoped_set:
				val = container.get(df.fieldname)
				if val:
					targets_by_dt.setdefault(target_dt, set()).add(str(val))


def validate_same_data_group_links(doc, method: str | None = None) -> None:
	"""Reject Link / Dynamic Link references to scoped records in another Data Group (HD-4).

	Wired on ``validate`` for all ``SCOPED_DOCTYPES`` so it runs inside
	``Document.run_before_save_methods`` AFTER ``before_validate``
	(``stamp_and_lock_data_group``) has stamped/locked ``doc.data_group`` and
	AFTER ``Document._validate_links`` has verified target existence. Covers
	parent fields and all child-table rows (evaluated against parent
	``doc.data_group``) for every role including ``SIRAJ Official`` and
	``Administrator``.
	"""
	from siraj_research.hooks import SCOPED_DOCTYPES

	scoped_set = frozenset(SCOPED_DOCTYPES)
	if doc.doctype not in scoped_set:
		return

	source_group = (doc.get(DATA_GROUP_FIELD) or "").strip()

	targets_by_dt: dict[str, set[str]] = {}
	_collect_scoped_link_targets(doc, scoped_set, targets_by_dt)
	for child in doc.get_all_children():
		_collect_scoped_link_targets(child, scoped_set, targets_by_dt)

	if not targets_by_dt:
		return

	if not source_group:
		frappe.throw(
			_("Linked records must belong to the same Data Group."),
			frappe.PermissionError,
		)

	# Single justified exception to Invariant 1 (recorded in HD-4 / C-03a):
	# perform ONE batched ``frappe.get_all`` per referenced scoped target DocType
	# selecting only ``("name", "data_group")`` so we can detect and reject
	# cross-group or blank-group links across ALL roles (including SIRAJ Official
	# and Administrator, where permission-scoped ``get_list`` would return
	# cross-group rows instead of distinguishing them). Target names/titles are
	# NEVER interpolated into the raised error message.
	for target_dt, names in targets_by_dt.items():
		rows = frappe.get_all(
			target_dt,
			filters={"name": ["in", sorted(names)]},
			fields=["name", DATA_GROUP_FIELD],
			limit_page_length=0,
		)
		group_by_name = {
			row["name"]: (row.get(DATA_GROUP_FIELD) or "").strip()
			for row in rows
		}
		for target_name in names:
			target_group = group_by_name.get(target_name, "")
			if not target_group or target_group != source_group:
				frappe.throw(
					_("Linked records must belong to the same Data Group."),
					frappe.PermissionError,
				)
