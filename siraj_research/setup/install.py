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
