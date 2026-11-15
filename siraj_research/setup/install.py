# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
"""Hooks that run on `bench --site <site> install-app siraj_research`."""
from __future__ import annotations

import frappe

ROLES = ("SIRAJ Viewer", "SIRAJ Researcher", "SIRAJ Reviewer", "SIRAJ Administrator")


def ensure_default_workflow_state():
	"""Provide the Link target used by SIRAJ DocTypes' default state.

	Preserve an existing site's Draft state and its settings. This creates only the
	Link target; it does not configure or activate a review workflow.
	"""
	if not frappe.db.exists("Workflow State", "Draft"):
		frappe.get_doc({
			"doctype": "Workflow State",
			"workflow_state_name": "Draft",
		}).insert(ignore_permissions=True)


def after_install():
	"""Create the four SIRAJ roles.

	Roles are data in Frappe and every DocPerm row names one, so they must exist before
	a user is granted one. Idempotent, which is what `bench reinstall` needs.
	"""
	for role in ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({
				"doctype": "Role",
				"role_name": role,
				"desk_access": 1,
			}).insert(ignore_permissions=True)

	ensure_default_workflow_state()
