"""Guard against stale DocType actions and browser-trusted relationship direction."""

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class FormIntegrityTest(unittest.TestCase):
	def test_no_stale_siraj_api_actions(self):
		for path in (ROOT / "siraj_research/siraj_research/doctype").glob("*/*.json"):
			data = json.loads(path.read_text(encoding="utf-8"))
			for action in data.get("actions", []):
				with self.subTest(doctype=data["name"], action=action.get("label")):
					self.assertFalse(action.get("action", "").startswith("siraj.api."))
					if action.get("action_type") == "Route" and action.get("action") == "siraj-explorer":
						self.assertTrue(
							(
								ROOT / "siraj_research/siraj_research/page/siraj_explorer/siraj_explorer.json"
							).exists()
						)

	def test_relationship_direction_is_server_derived(self):
		document_module = types.ModuleType("frappe.model.document")
		document_module.Document = type("Document", (), {})
		frappe = types.ModuleType("frappe")
		frappe.db = types.SimpleNamespace(get_value=lambda *args: 1)
		path = ROOT / "siraj_research/siraj_research/doctype/relationship/relationship.py"
		spec = importlib.util.spec_from_file_location("relationship_controller_test", path)
		module = importlib.util.module_from_spec(spec)
		with patch.dict(
			sys.modules,
			{
				"frappe": frappe,
				"frappe.model": types.ModuleType("frappe.model"),
				"frappe.model.document": document_module,
			},
		):
			spec.loader.exec_module(module)
		record = module.Relationship()
		record.relationship_type = "Colleague"
		record.direction = "Directed"  # A client-supplied value must not win.
		record.validate()
		self.assertEqual(record.direction, "Symmetric")
		frappe.db.get_value = lambda *args: 0
		record.validate()
		self.assertEqual(record.direction, "Directed")


if __name__ == "__main__":
	unittest.main()
