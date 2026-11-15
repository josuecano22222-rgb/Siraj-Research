"""Unit and metadata tests for the permission-aware explorer (no bench required)."""
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_visualization(frappe):
    access_spec = importlib.util.spec_from_file_location("siraj_visualization_access_test", ROOT / "siraj_research/report_access.py")
    access = importlib.util.module_from_spec(access_spec)
    spec = importlib.util.spec_from_file_location("siraj_visualization_test", ROOT / "siraj_research/visualization.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"frappe": frappe}):
        access_spec.loader.exec_module(access)
        with patch.dict(sys.modules, {"siraj_research.report_access": access}):
            spec.loader.exec_module(module)
    return module


class FakeFrappe(types.SimpleNamespace):
    def __init__(self, rows=None, denied=()):
        super().__init__()
        self.rows = rows or {}
        self.denied = set(denied)
        self._ = lambda text: text
        self.ValidationError = ValueError
        self.PermissionError = PermissionError
        self.hidden_fields = set()

    def whitelist(self):
        return lambda fn: fn

    def has_permission(self, doctype=None, ptype='read', doc=None, user=None, throw=False, *, parent_doctype=None, debug=False, ignore_share_permissions=False):
        return doctype not in self.denied and (doctype, doc) not in self.denied

    def get_list(self, doctype, fields, **kwargs):
        start = kwargs.get('limit_start', 0)
        size = kwargs.get('page_length', kwargs.get('limit_page_length', 20))
        rows = sorted(self.rows.get(doctype, []), key=lambda row: row['name'])
        return [{field: row.get(field) for field in fields if field not in self.hidden_fields}
                for row in rows[start:start + size]]

    def get_meta(self, doctype):
        return types.SimpleNamespace(get_field=lambda field: types.SimpleNamespace(label=field))

    def throw(self, message, exception):
        raise exception(message)


class VisualizationTest(unittest.TestCase):
    def test_coordinates_are_record_owned_and_valid(self):
        f = FakeFrappe({'Person': [
            {'name': 'p1', 'display_name': 'One', 'latitude': 10, 'longitude': 20},
            {'name': 'p2', 'display_name': 'Missing', 'latitude': 0, 'longitude': 0},
            {'name': 'p3', 'display_name': 'Invalid', 'latitude': 95, 'longitude': 10},
            {'name': 'p4', 'display_name': 'Private', 'latitude': 5, 'longitude': 5},
        ]}, denied={('Person', 'p4')})
        v = load_visualization(f)
        result = v.geographic_data()
        self.assertEqual([p['name'] for p in result['points']], ['p1'])
        self.assertEqual(result['points'][0]['latitude'], 10)
        self.assertFalse(v._valid_point(float('nan'), 1))
        self.assertTrue(v._valid_point(0, 20))

    def test_edges_never_reveal_inaccessible_endpoints_or_relationships(self):
        f = FakeFrappe({
            'Person': [{'name': 'p1', 'display_name': 'Public'}, {'name': 'p2', 'display_name': 'Private'}],
            'Institution': [{'name': 'i1', 'display_name': 'Institute'}],
            'Relationship': [
                {'name': 'r1', 'subject_type': 'Person', 'subject': 'p1', 'object_type': 'Institution', 'object': 'i1'},
                {'name': 'r2', 'subject_type': 'Person', 'subject': 'p2', 'object_type': 'Institution', 'object': 'i1'},
                {'name': 'r3', 'subject_type': 'Person', 'subject': 'p1', 'object_type': 'Institution', 'object': 'i1'},
            ],
        }, denied={('Person', 'p2'), ('Relationship', 'r3')})
        result = load_visualization(f).relationship_data()
        self.assertEqual([edge['name'] for edge in result['edges']], ['r1'])
        self.assertEqual({node['name'] for node in result['nodes']}, {'p1', 'i1'})

    def test_structure_counts_sum_at_every_level(self):
        v = load_visualization(FakeFrappe())
        rows = [{'a': 'A', 'b': 'B'}, {'a': 'A', 'b': 'C'}, {'a': None, 'b': 'B'}]
        root = v._structure_counts(iter(rows), ('a', 'b'))
        groups = v._structure_children(root, ('a', 'b'))
        self.assertEqual(root['count'], len(rows))
        self.assertEqual(sum(x['count'] for x in groups), len(rows))
        for group in groups:
            self.assertEqual(sum(x['count'] for x in group['children']), group['count'])
        self.assertEqual(groups[0]['count'], 2)

    def test_structures_count_all_visible_records_and_fold_without_losing_totals(self):
        people = [{'name': str(i).zfill(5), 'nationality': f'Country-{i % 60:02}',
                   'classification': f'Class-{i % 17:02}', 'workflow_state': 'Draft'} for i in range(2600)]
        f = FakeFrappe({'Person': people}, denied={('Person', '00000'), ('Person', '02599')})
        v = load_visualization(f)
        result = v.structure_data('people')
        self.assertEqual(result['count'], 2598)
        self.assertFalse(result['truncated'])
        self.assertEqual(result['group_count'], 60)
        self.assertEqual(sum(child['count'] for child in result['children']), result['count'])
        self.assertEqual(len(result['children']), 49)
        folded = result['children'][-1]
        self.assertEqual(folded['folded_groups'], 12)
        self.assertEqual(folded['label'], '12 smaller groups')
        self.assertGreater(folded['count'], 0)
        for child in result['children'][:-1]:
            self.assertEqual(sum(item['count'] for item in child['children']), child['count'])

    def test_structure_deep_folding_counts_and_denied_source(self):
        f = FakeFrappe({'Person': [{'name': str(i).zfill(3), 'nationality': 'Iraq',
                                     'classification': f'Class-{i:02}', 'workflow_state': 'Draft'}
                                    for i in range(20)]})
        v = load_visualization(f)
        root = v.structure_data('people')
        branch = root['children'][0]
        self.assertEqual(branch['group_count'], 20)
        self.assertEqual(len(branch['children']), 13)
        self.assertEqual(branch['children'][-1]['folded_groups'], 8)
        self.assertEqual(sum(child['count'] for child in branch['children']), 20)
        f.denied.add('Person')
        with self.assertRaises(PermissionError): v.structure_data('people')
        with self.assertRaises(ValueError): v.structure_data('not-a-source')

    def test_structure_refuses_unreadable_dimension_instead_of_false_missing_data(self):
        f = FakeFrappe({'Person': [{'name': 'p1', 'nationality': 'Iraq'}]})
        f.hidden_fields.add('nationality')
        with self.assertRaises(PermissionError): load_visualization(f).structure_data('people')

    def test_cutoff_and_denied_doctype(self):
        f = FakeFrappe({'Person': [{'name': str(i)} for i in range(4)]}, denied={'Event'})
        v = load_visualization(f)
        v.MAX_RECORDS = 3
        self.assertEqual(len(v._records('Person', [])[0]), 3)
        self.assertTrue(v._records('Person', [])[1])
        self.assertEqual(v._records('Event', []), ([], False))
        with self.assertRaises(PermissionError):
            v.structure_data('events')
        with self.assertRaises(ValueError):
            v.structure_data('nonsense')

    def test_selected_fields_exist_and_are_public(self):
        v = load_visualization(FakeFrappe())
        specs = {}
        for path in (ROOT / 'siraj_research/siraj_research/doctype').glob('*/*.json'):
            d = json.loads(path.read_text(encoding='utf-8'))
            specs[d['name']] = {field.get('fieldname'): field for field in d.get('fields', [])}
        for dt, title in v.ENTITIES.items():
            fields = [title]
            if dt in v.GEO_TYPES:
                fields += ['latitude', 'longitude', 'geo_precision', 'geocoding_method', 'geo_uncertainty_m', 'geometry_source']
            for field in fields:
                with self.subTest(doctype=dt, field=field):
                    self.assertIn(field, specs[dt])
                    self.assertFalse(specs[dt][field].get('permlevel'))
        for field in ['relationship_type', 'subject_type', 'subject', 'object_type', 'object', 'direction', 'description', 'workflow_state']:
            with self.subTest(doctype='Relationship', field=field):
                self.assertIn(field, specs['Relationship'])
                self.assertFalse(specs['Relationship'][field].get('permlevel'))
        for dt, fields in v.STRUCTURES.values():
            for field in fields:
                with self.subTest(doctype=dt, field=field):
                    self.assertIn(field, specs[dt])
                    self.assertFalse(specs[dt][field].get('permlevel'))


if __name__ == '__main__':
    unittest.main()
