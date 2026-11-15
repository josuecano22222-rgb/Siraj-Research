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
	"""Create roles, default workflow state and additive reference data."""
	for role in ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({
				"doctype": "Role",
				"role_name": role,
				"desk_access": 1,
			}).insert(ignore_permissions=True)

	ensure_default_workflow_state()
	# Master data is additive and rerunnable; do not seed synthetic demos.
	from siraj_research.setup.master_data import seed_master_data

	print("SIRAJ reference data:", seed_master_data())
