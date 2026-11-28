# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
"""Hooks that run on `bench --site <site> install-app siraj_research`."""

from __future__ import annotations

import frappe

ROLES = ("SIRAJ Viewer", "SIRAJ Researcher", "SIRAJ Reviewer", "SIRAJ Administrator")


def ensure_default_workflow_state():
	"""Provide the Link target used by SIRAJ DocTypes' default state.

	       Preserve an existing site's Draft state and its settings. This creates only the
	       Link target
	it does not configure or activate a review workflow.
	"""
	if not frappe.db.exists("Workflow State", "Draft"):
		frappe.get_doc(
			{
				"doctype": "Workflow State",
				"workflow_state_name": "Draft",
			}
		).insert(ignore_permissions=True)


def sync_insight_widgets():
	"""Import the Number Card / Dashboard Chart JSON shipped with the app.

	Frappe v15's module walk has no ``importable_doctypes`` hook (added in
	later releases), so without this the workspace's live-insight widgets
	never reach the database on migrate. Safe to re-run: each JSON imports
	over its existing document by name.
	"""
	import glob
	import os

	from frappe.modules.import_file import import_file_by_path

	base = frappe.get_app_path("siraj_research", "siraj_research")
	imported = 0
	for kind in ("number_card", "dashboard_chart"):
		for path in sorted(glob.glob(os.path.join(base, kind, "*", "*.json"))):
			try:
				if import_file_by_path(path, force=1, ignore_version=True):
					imported += 1
			except Exception:
				frappe.logger().warning("widget import failed: %s", path, exc_info=True)
	frappe.db.commit()
	print(f"SIRAJ insight widgets: {imported} imported")
	return imported


def after_install():
	"""Create roles, default workflow state and additive reference data."""
	for role in ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc(
				{
					"doctype": "Role",
					"role_name": role,
					"desk_access": 1,
				}
			).insert(ignore_permissions=True)

	ensure_default_workflow_state()
	# Master data is additive and rerunnable; do not seed synthetic demos.
	from siraj_research.setup.master_data import seed_master_data

	print("SIRAJ reference data:", seed_master_data())


# Admin-hierarchy DocTypes whose name is derived from their ``code`` field.
HIERARCHY_AUTONAME_DOCTYPHS = ("Governorate", "District", "Municipality", "Village", "Community")


def ensure_hierarchy_autoname():
	"""Align the admin-hierarchy DocTypes' ``autoname`` with the on-disk JSON.

	Frappe's DocType sync does **not** update ``autoname`` for DocTypes that
	already exist in the database -- ``autoname`` is only applied at first
	creation. Sites created before the hierarchy JSON shipped
	``autoname: field:code`` therefore keep the default ``field:name``, so
	inserting a hierarchy record that carries ``code`` but no ``name`` throws
	"<Doctype> Name is required" at ``set_new_name`` (the root cause of the
	``test_23`` seeding failure). This idempotent migrate hook sets
	``autoname = field:code`` for the five hierarchy DocTypes so the DB
	matches the JSON. Safe to re-run; no-op once aligned.
	"""
	changed = []
	for dt in HIERARCHY_AUTONAME_DOCTYPHS:
		if not frappe.db.exists("DocType", dt):
			continue
		if (frappe.get_meta(dt).autoname or "") != "field:code":
			frappe.db.set_value("DocType", dt, "autoname", "field:code")
			frappe.clear_cache(doctype=dt)
			changed.append(dt)
	if changed:
		frappe.db.commit()
		print("SIRAJ hierarchy autoname set to field:code:", ", ".join(changed))
	return changed


GROUP_MEMBER_ROLE = "Group Member"
APP_ADMIN_ROLE = "SIRAJ Administrator"
OFFICIAL_ROLE = "SIRAJ Official"
OFFICIAL_ROLE_PROFILE = "SIRAJ Official"
DATA_GROUPS = ("GD", "GC")
SECTION_USERS = {
	"GD": ("GD1", "GD2", "GD3", "GD4", "GD5"),
	"GC": ("GC1", "GC2", "GC3", "GC4", "GC5"),
}


def setup(password: str, commit: bool = True):
	"""Idempotently provision isolated SIRAJ sections and native permissions.

	``commit`` is disabled by the integration tests so setup remains inside
	Frappe's test transaction. Normal ``bench execute`` calls should keep the
	default so all provisioned users are immediately available.

	Run with::

	    bench --site SITE execute siraj_research.setup.install.setup \
	        --kwargs '{"password": "a-strong-password"}'
	"""
	if not password:
		frappe.throw("A non-empty password is required")

	for role in (GROUP_MEMBER_ROLE, APP_ADMIN_ROLE, OFFICIAL_ROLE):
		if not frappe.db.exists("Role", role):
			frappe.get_doc(
				{"doctype": "Role", "role_name": role, "desk_access": 1}
			).insert(ignore_permissions=True)

	# Assign this profile to supervisors who must see both GD and GC. The
	# Official role bypasses row isolation; SIRAJ Administrator supplies all
	# application permissions without granting Frappe System Manager access.
	if frappe.db.exists("Role Profile", OFFICIAL_ROLE_PROFILE):
		profile = frappe.get_doc("Role Profile", OFFICIAL_ROLE_PROFILE)
		profile.set("roles", [])
	else:
		profile = frappe.get_doc(
			{"doctype": "Role Profile", "role_profile": OFFICIAL_ROLE_PROFILE}
		)
	for role in (GROUP_MEMBER_ROLE, APP_ADMIN_ROLE, OFFICIAL_ROLE):
		profile.append("roles", {"role": role})
	if profile.is_new():
		profile.insert(ignore_permissions=True)
	else:
		profile.save(ignore_permissions=True)

	for group in DATA_GROUPS:
		if not frappe.db.exists("Data Group", group):
			frappe.get_doc(
				{"doctype": "Data Group", "group_name": group}
			).insert(ignore_permissions=True)

	for group, names in SECTION_USERS.items():
		for display_name in names:
			email = f"{display_name.lower()}@example.com"
			if not frappe.db.exists("User", email):
				user = frappe.get_doc(
					{
						"doctype": "User",
						"email": email,
						"username": display_name.lower(),
						"first_name": display_name,
						"enabled": 1,
						"user_type": "System User",
						"send_welcome_email": 0,
						"new_password": password,
						"roles": [{"role": GROUP_MEMBER_ROLE}, {"role": APP_ADMIN_ROLE}],
					}
				).insert(ignore_permissions=True)
			else:
				user = frappe.get_doc("User", email)
				user.username = display_name.lower()
				user.enabled = 1
				user.user_type = "System User"
				user.new_password = password
				assigned_roles = {row.role for row in user.roles}
				for role in (GROUP_MEMBER_ROLE, APP_ADMIN_ROLE):
					if role not in assigned_roles:
						user.append("roles", {"role": role})
				user.save(ignore_permissions=True)

			if not frappe.db.exists(
				"User Permission",
				{"user": email, "allow": "Data Group", "for_value": group},
			):
				frappe.get_doc(
					{
						"doctype": "User Permission",
						"user": email,
						"allow": "Data Group",
						"for_value": group,
						"apply_to_all_doctypes": 1,
					}
				).insert(ignore_permissions=True)

	# Sharing can bypass User Permissions; these settings complete the boundary.
	frappe.db.set_single_value("System Settings", "disable_document_sharing", 1)
	frappe.db.set_single_value("System Settings", "apply_strict_user_permissions", 0)
	frappe.clear_cache()
	if commit:
		frappe.db.commit()
	return {"groups": len(DATA_GROUPS), "users": sum(map(len, SECTION_USERS.values()))}
