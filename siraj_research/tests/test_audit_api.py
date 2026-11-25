# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
"""Bench smoke tests for the audit history API (Phase 4).

Run with:
    bench --site frappe.com run-tests --module siraj_research.tests.test_audit_api
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from siraj_research.api.audit import collect_history, document_history

PROBE_TAG = "Audit Probe"


class TestAuditApi(FrappeTestCase):
    def tearDown(self):
        for name in frappe.get_all(
            "Person",
            filters={"name_en": ["like", f"%{PROBE_TAG}%"]},
            pluck="name",
            limit_page_length=0,
        ):
            try:
                frappe.delete_doc("Person", name, force=True, ignore_permissions=True)
            except Exception:
                pass
        frappe.db.commit()

    def _probe(self) -> str:
        if not frappe.db.exists("Data Group", "GD"):
            frappe.get_doc({"doctype": "Data Group", "group_name": "GD"}).insert(
                ignore_permissions=True
            )
        doc = frappe.get_doc(
            {
                "doctype": "Person",
                "display_name": f"{PROBE_TAG}",
                "name_en": f"{PROBE_TAG}",
                "name_ar": f"{PROBE_TAG}",
                "data_group": "GD",
            }
        )
        doc.insert(ignore_permissions=True)
        return doc.name

    def test_history_formats_updates_and_drops_noise(self):
        name = self._probe()
        person = frappe.get_doc("Person", name)
        # ignore_version=False: frappe sets ignore_version=flags.in_test by
        # default, so plain saves during tests never write Version rows.
        person.name_variants = "audit probe first edit"
        person.save(ignore_permissions=True, ignore_version=False)
        person.name_variants = "audit probe second edit"
        person.save(ignore_permissions=True, ignore_version=False)

        result = collect_history("Person", name, limit=10)
        history = result["history"]
        self.assertTrue(history, "saving a change must produce a Version entry")
        entry = history[0]
        self.assertEqual(entry["action"], "updated")
        self.assertTrue(entry["by"])
        self.assertTrue(entry["when"])
        fields = [c["field"] for c in entry["changes"]]
        self.assertIn("name_variants", fields)
        # Labels come from the DocType meta, not raw fieldnames.
        labels = [c.get("label") for c in entry["changes"]]
        self.assertIn("Other recorded forms of the name", labels)
        # Framework noise never reaches the caller.
        noise = {"modified", "modified_by", "idx", "docstatus", "owner", "creation"}
        self.assertFalse(noise & set(fields))
        # The rendered diff shows the second edit as current.
        change = next(c for c in entry["changes"] if c["field"] == "name_variants")
        self.assertEqual(change["new"], "audit probe second edit")

    def test_unknown_doctype_and_record_are_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            document_history("Not A Doctype", "whatever")
        with self.assertRaises(frappe.ValidationError):
            document_history("Person", "")

    def test_whitelisted_entry_point_is_registered(self):
        # frappe.whitelist() registers into the frappe.whitelisted list.
        self.assertIn(document_history, frappe.whitelisted)
