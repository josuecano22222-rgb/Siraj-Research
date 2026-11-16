"""Regression test against Frappe-shaped stubs, not an actual permission test."""
import unittest
from test_visualization import FakeFrappe, load_visualization


class RelationshipSourcePrivacyTest(unittest.TestCase):
    def test_edge_hides_unreadable_or_deleted_source(self):
        f = FakeFrappe({
            'Person': [{'name':'p', 'display_name':'Visible person'}],
            'Source': [{'name':'public', 'display_name':'Public source'},
                       {'name':'private-source', 'display_name':'Private source'}],
            'Relationship': [
                {'name':'a', 'subject_type':'Person', 'subject':'p', 'object_type':'Person', 'object':'p', 'primary_source':'public'},
                {'name':'b', 'subject_type':'Person', 'subject':'p', 'object_type':'Person', 'object':'p', 'primary_source':'private-source'},
                {'name':'c', 'subject_type':'Person', 'subject':'p', 'object_type':'Person', 'object':'p', 'primary_source':'missing-source'},
            ],
        }, denied={('Source','private-source')})
        result = load_visualization(f).relationship_data()
        edges = {edge['name']:edge for edge in result['edges']}
        self.assertEqual(edges['a']['primary_source'], 'public')
        self.assertEqual(edges['b']['primary_source'], '')
        self.assertEqual(edges['c']['primary_source'], '')
        self.assertNotIn('private-source', str(result))
        self.assertNotIn('missing-source', str(result))
        f.denied.add('Source')
        edges = load_visualization(f).relationship_data()['edges']
        self.assertTrue(all(edge['primary_source'] == '' for edge in edges))

if __name__ == '__main__': unittest.main()
