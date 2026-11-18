"""
In-site DocType validation (runs via bench --site X run-tests or console).

Loads meta for every SIRAJ DocType and calls DocType.validate() — which runs
check_link_table_options (the validator behind WrongOptionsDoctypeLinkError) —
inside a savepoint that is rolled back.

Run:
    bench --site frappe.com run-tests --module siraj_research.tests.test_meta_loads
Or ad-hoc:
    bench --site frappe.com console < siraj_research/tests/test_meta_loads.py
"""
import frappe
from frappe.core.doctype.doctype.doctype import DocType
import unittest

SIRAJ_DOCTYPES = None  # filled by setUp


def _all_siraj_doctypes():
    return frappe.get_all("DocType", filters={"module": "Siraj Research"}, pluck="name")


class TestMetaLoads(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doctypes = _all_siraj_doctypes()
        assert cls.doctypes, "No SIRAJ Research DocTypes found — is the app installed?"

    def test_meta_loads_for_every_doctype(self):
        """frappe.get_meta must succeed for every SIRAJ DocType (not 404)."""
        for dt in self.doctypes:
            with self.subTest(doctype=dt):
                meta = frappe.get_meta(dt)
                self.assertIsNotNone(meta, f"frappe.get_meta({dt!r}) returned None")
                self.assertEqual(meta.name, dt)

    def test_doctype_validate_passes(self):
        """DocType.validate() — including check_link_table_options — must not raise."""
        for dt in self.doctypes:
            with self.subTest(doctype=dt):
                doc = frappe.get_doc("DocType", dt)
                frappe.flags.in_install = True  # avoid side effects
                try:
                    doc.validate()
                finally:
                    frappe.flags.in_install = False


if __name__ == "__main__":
    unittest.main(verbosity=2)
