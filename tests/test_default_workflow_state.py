"""Checks for the default Workflow State setup without a running bench."""
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]


def load_install(frappe):
    spec = importlib.util.spec_from_file_location(
        "siraj_install_test", ROOT / "siraj_research/setup/install.py"
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"frappe": frappe}):
        spec.loader.exec_module(module)
    return module


class DefaultWorkflowStateTest(unittest.TestCase):
    def test_creates_draft_when_missing(self):
        frappe = types.SimpleNamespace(db=MagicMock(), get_doc=MagicMock())
        frappe.db.exists.return_value = False
        install = load_install(frappe)
        install.ensure_default_workflow_state()
        frappe.db.exists.assert_called_once_with("Workflow State", "Draft")
        frappe.get_doc.assert_called_once_with(
            {"doctype": "Workflow State", "workflow_state_name": "Draft"}
        )
        frappe.get_doc.return_value.insert.assert_called_once_with(ignore_permissions=True)

    def test_preserves_existing_draft(self):
        frappe = types.SimpleNamespace(db=MagicMock(), get_doc=MagicMock())
        frappe.db.exists.return_value = True
        install = load_install(frappe)
        install.ensure_default_workflow_state()
        frappe.get_doc.assert_not_called()

    def test_install_also_seeds_reference_data(self):
        frappe = types.SimpleNamespace(db=MagicMock(), get_doc=MagicMock())
        frappe.db.exists.return_value = True
        install = load_install(frappe)
        master = types.ModuleType('siraj_research.setup.master_data')
        master.seed_master_data = MagicMock(return_value={'created': {}})
        with patch.dict(sys.modules, {'siraj_research.setup.master_data': master}), patch('builtins.print'):
            install.after_install()
        master.seed_master_data.assert_called_once_with()

    def test_doctype_defaults_match_installed_state(self):
        fields = []
        for path in (ROOT / "siraj_research/siraj_research/doctype").glob("*/*.json"):
            document = json.loads(path.read_text(encoding="utf-8"))
            fields.extend(
                (document["name"], field)
                for field in document.get("fields", [])
                if field.get("fieldtype") == "Link" and field.get("options") == "Workflow State"
            )
        self.assertTrue(fields)
        for name, field in fields:
            with self.subTest(doctype=name):
                self.assertEqual(field.get("default"), "Draft")


if __name__ == "__main__":
    unittest.main()
