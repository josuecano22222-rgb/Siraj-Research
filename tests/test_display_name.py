"""Test server-derived titles and the six controller hooks without a Frappe bench."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class Document:
	def get(self, key):
		return getattr(self, key, None)


class DisplayNameTest(unittest.TestCase):
	def test_controller_hooks_derive_titles_and_handle_sparse_input(self):
		document = types.ModuleType("frappe.model.document")
		document.Document = Document
		frappe = types.ModuleType("frappe")
		frappe._ = lambda x: x
		frappe.utils = types.ModuleType("frappe.utils")
		frappe.utils.getdate = lambda *args: None
		modules = {
			"frappe": frappe,
			"frappe.model": types.ModuleType("frappe.model"),
			"frappe.model.document": document,
			"frappe.utils": frappe.utils,
		}
		cases = [
			("person", "Person", "name_en", "name_ar"),
			("institution", "Institution", "name_en", "name_ar"),
			("place", "Place", "name_en", "name_ar"),
			("research_event", "ResearchEvent", "title_en", "title_ar"),
			("source", "Source", "title", "title_ar"),
		]
		with patch.dict(sys.modules, modules):
			for slug, cls, first, second in cases:
				with self.subTest(doctype=cls):
					path = ROOT / f"siraj_research/siraj_research/doctype/{slug}/{slug}.py"
					spec = importlib.util.spec_from_file_location("test_" + slug + "_display", path)
					module = importlib.util.module_from_spec(spec)
					spec.loader.exec_module(module)
					doc = getattr(module, cls)()
					doc.display_name = "client supplied"
					setattr(doc, second, "  اسم اختبار  ")
					doc.before_validate()
					self.assertEqual(doc.display_name, "اسم اختبار")
					setattr(doc, first, "  " + "A" * 200 + "  ")
					doc.before_validate()
					self.assertEqual(doc.display_name, "A" * 140)
					setattr(doc, first, " ")
					setattr(doc, second, None)
					doc.before_validate()
					self.assertIsNone(doc.display_name)

	def test_relationship_uses_stored_ids_without_loading_hidden_records(self):
		from siraj_research.utils.display_name import set_relationship_display_name

		doc = Document()
		doc.subject, doc.relationship_type, doc.object = "PER-1", "Member", "INS-1"
		set_relationship_display_name(doc)
		self.assertEqual(doc.display_name, "PER-1 → Member → INS-1")
		doc.subject = "x" * 200
		set_relationship_display_name(doc)
		self.assertEqual(len(doc.display_name), 140)
		doc.subject = doc.relationship_type = doc.object = None
		set_relationship_display_name(doc)
		self.assertIsNone(doc.display_name)


if __name__ == "__main__":
	unittest.main()
