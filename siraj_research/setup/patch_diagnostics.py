"""Read-only diagnostics for placeholder legacy migration entries.

This is a bench-execute helper, not a web endpoint and not a migration. Frappe
marks an app's patch names complete on normal fresh installation without
executing their code, so Patch Log alone never proves legacy data was migrated.
"""

from pathlib import Path

import frappe

PATCHES = (
	"siraj_research.patches.v1_0.set_naming_counters",
	"siraj_research.patches.v1_0.fold_commanders",
	"siraj_research.patches.v1_0.migrate_person_traits",
	"siraj_research.patches.v1_0.map_notes_to_comments",
)


def inspect_patch_log():
	"""Report whether the declared files and non-skipped Patch Log entries exist."""
	package = Path(__file__).resolve().parents[1]
	rows = []
	for patch in PATCHES:
		file_path = package.joinpath(*patch.split(".")[1:]).with_suffix(".py")
		rows.append(
			{
				"patch": patch,
				"module_present": file_path.is_file(),
				"logged_completed": bool(frappe.db.exists("Patch Log", {"patch": patch, "skipped": 0})),
			}
		)
	return {
		"patches": rows,
		"note": "A completed Patch Log entry does not prove data was migrated: fresh installs mark patches complete without executing them.",
	}
