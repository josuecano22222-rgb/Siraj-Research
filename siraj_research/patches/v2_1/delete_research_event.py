"""Remove obsolete Research Event DocType and its empty SQL table (HD-1 / Decision E).

Runs in ``[post_model_sync]`` after ``relationship.json``, ``workspace``, and
``onboarding_step`` have synced so no stale metadata references ``Research Event``.

Verified against Frappe v15.128.0:
  * ``frappe.delete_doc("DocType", "Research Event", force=True)`` deletes metadata
    rows (``tabDocType``, ``tabDocField``, ``tabDocPerm``, etc.) and skips missing
    controller files under ``developer_mode=1`` (``delete_doc.py:100-113`` catches
    ``OSError``), while ``patch_handler.run_single`` also sets ``conf.developer_mode = 0``.
  * ``frappe.delete_doc("DocType", ...)`` does NOT drop ``tabResearch Event`` from
    MariaDB (verified in ``delete_doc.py:86-113`` and live test).
  * In MariaDB, ``frappe.db.check_implicit_commit`` (``database.py:451-456``) raises
    ``ImplicitCommitError`` if ``DROP TABLE`` runs when ``transaction_writes > 0``.
    Dropping ``tabResearch Event`` right after verifying ``row_count == 0`` (while
    ``transaction_writes == 0``) and BEFORE the DML writes of ``frappe.delete_doc``
    avoids ``ImplicitCommitError`` without calling ``frappe.db.commit()``.
"""

from __future__ import annotations

import frappe


def execute():
	if frappe.db.exists("Number Card", "Total Research Events"):
		if frappe.db.exists("Workspace Number Card", {"number_card_name": "Total Research Events"}):
			frappe.db.delete("Workspace Number Card", {"number_card_name": "Total Research Events"})
		frappe.delete_doc(
			"Number Card", "Total Research Events", force=True, ignore_permissions=True
		)

	table_exists = frappe.db.table_exists("Research Event", cached=False)
	if table_exists:
		row_count = int(
			frappe.db.sql("SELECT COUNT(*) FROM `tabResearch Event`")[0][0] or 0
		)
		if row_count > 0:
			raise RuntimeError(
				f"Cannot delete Research Event: tabResearch Event contains {row_count} row(s). "
				"Migrate or clear those rows before running bench migrate."
			)

	if frappe.db.exists("DocType", "Research Event"):
		frappe.delete_doc(
			"DocType", "Research Event", force=True, ignore_permissions=True
		)

	# Verified in Frappe 15.128.0 + live MariaDB test: delete_doc("DocType", ...)
	# leaves `tabResearch Event` on disk. Reset transaction_writes before the
	# explicit Decision E DROP TABLE exception (never calling frappe.db.commit()).
	if frappe.db.table_exists("Research Event", cached=False):
		frappe.db.transaction_writes = 0
		frappe.db.sql("DROP TABLE IF EXISTS `tabResearch Event`")
