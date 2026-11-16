"""Regression against Frappe-shaped stubs; not a real role/permission test."""

import unittest

import test_reports
import test_treeview


class LinkQueryPrivacyTest(unittest.TestCase):
	def test_parent_hidden_by_list_query_cannot_be_expanded(self):
		case = test_treeview.TreeTest()
		case.setUp()
		f = case.frappe
		f.rows["Place"] = [
			{"name": "hidden-parent", "is_group": 1},
			{"name": "visible-child", "parent_place": "hidden-parent"},
		]
		original = f.get_list

		def filtered(doctype, **kwargs):
			return [row for row in original(doctype, **kwargs) if row["name"] != "hidden-parent"]

		f.get_list = filtered
		with self.assertRaises(PermissionError):
			case.tree.get_children("Place", "hidden-parent")

	def test_relationship_report_requires_list_visible_endpoint(self):
		case = test_reports.ReportTest()
		case.setUp()
		f = case.frappe
		f.rows = {
			"Person": [{"name": "p"}],
			"Institution": [{"name": "private-institute"}],
			"Relationship": [
				{
					"name": "r",
					"subject_type": "Person",
					"subject": "p",
					"object_type": "Institution",
					"object": "private-institute",
				}
			],
		}
		original = f.get_list

		def filtered(doctype, **kwargs):
			return [] if doctype == "Institution" else original(doctype, **kwargs)

		f.get_list = filtered
		_, rows = case.report("entity_relationship_graph").execute()
		self.assertEqual(rows, [])

	def test_visible_link_remains_available(self):
		case = test_treeview.TreeTest()
		case.setUp()
		f = case.frappe
		f.rows["Place"] = [{"name": "parent", "is_group": 1}, {"name": "child", "parent_place": "parent"}]
		self.assertEqual([row["value"] for row in case.tree.get_children("Place", "parent")], ["child"])


if __name__ == "__main__":
	unittest.main()
