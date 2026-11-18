"""Synthetic non-Administrator list/document privacy cases, not live HTTP tests."""

import types
import unittest

from test_visualization import FakeFrappe, load_visualization


class VisualizationPermissionPathsTest(unittest.TestCase):
	def test_list_hidden_document_cannot_be_read_directly_or_via_relationship(self):
		f = FakeFrappe(
			{
				"Person": [
					{"name": "public", "display_name": "Public"},
					{"name": "hidden", "display_name": "Hidden"},
				],
				"Relationship": [
					{
						"name": "link",
						"subject_type": "Person",
						"subject": "public",
						"object_type": "Person",
						"object": "hidden",
					}
				],
			}
		)
		f.session = types.SimpleNamespace(user="researcher")
		original = f.get_list

		def filtered(dt, fields, **kwargs):
			rows = original(dt, fields, **kwargs)
			return [row for row in rows if not (dt == "Person" and row["name"] == "hidden")]

		f.get_list = filtered
		viz = load_visualization(f)
		with self.assertRaises(PermissionError):
			viz.record_detail("Person", "hidden")
		graph = viz.relationship_data()
		self.assertEqual(graph["edges"], [])
		self.assertNotIn("hidden", str(graph))
		self.assertEqual(viz.record_detail("Person", "public")["name"], "public")

	def test_document_denial_removes_list_visible_relationship(self):
		f = FakeFrappe(
			{
				"Person": [{"name": "p", "display_name": "P"}],
				"Relationship": [
					{
						"name": "secret-link",
						"subject_type": "Person",
						"subject": "p",
						"object_type": "Person",
						"object": "p",
					}
				],
			},
			denied={("Relationship", "secret-link")},
		)
		f.session = types.SimpleNamespace(user="researcher")
		graph = load_visualization(f).relationship_data()
		self.assertEqual(graph["edges"], [])
		self.assertNotIn("secret-link", str(graph))


if __name__ == "__main__":
	unittest.main()
