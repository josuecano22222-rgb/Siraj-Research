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

GROUP_MEMBER_ROLE = "Group Member"
DATA_GROUPS = ("GD", "GC")
SECTION_USERS = {
	"GD": ("GD1", "GD2", "GD3", "GD4", "GD5"),
	"GC": ("GC1", "GC2", "GC3", "GC4", "GC5"),
}


def setup(password: str):
	"""Idempotently create demo groups, members and native User Permissions.

	Run with::

	    bench --site SITE execute siraj_research.setup.install.setup \
	        --kwargs '{"password": "a-strong-password"}'
	"""
	if not password:
		frappe.throw("A non-empty password is required")

	if not frappe.db.exists("Role", GROUP_MEMBER_ROLE):
		frappe.get_doc(
			{"doctype": "Role", "role_name": GROUP_MEMBER_ROLE, "desk_access": 1}
		).insert(ignore_permissions=True)

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
						"roles": [{"role": GROUP_MEMBER_ROLE}],
					}
				).insert(ignore_permissions=True)
			else:
				user = frappe.get_doc("User", email)
				user.username = display_name.lower()
				user.enabled = 1
				user.user_type = "System User"
				user.new_password = password
				if GROUP_MEMBER_ROLE not in {row.role for row in user.roles}:
					user.append("roles", {"role": GROUP_MEMBER_ROLE})
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
	frappe.db.commit()
	return {"groups": len(DATA_GROUPS), "users": sum(map(len, SECTION_USERS.values()))}
