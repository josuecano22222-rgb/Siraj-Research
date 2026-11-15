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
        filters = kwargs.get('filters') or {}
        rows = [row for row in rows if all(row.get(key) == value for key, value in filters.items())]
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

    def test_relationship_evidence_counts_require_readable_parent_field(self):
        f = FakeFrappe({'Person': [{'name': 'p1', 'display_name': 'Public'}],
                        'Relationship': [{'name': 'r1', 'subject_type': 'Person', 'subject': 'p1',
                                          'object_type': 'Person', 'object': 'p1'},
                                         {'name': 'r2', 'subject_type': 'Person', 'subject': 'p1',
                                          'object_type': 'Person', 'object': 'p1'},
                                         {'name': 'r3', 'subject_type': 'Person', 'subject': 'p1',
                                          'object_type': 'Person', 'object': 'p1'}]}, denied={('Relationship', 'r3')})
        f.session = types.SimpleNamespace(user='researcher')
        seen = []
        class Doc:
            def __init__(self, name): self.name = name; self.meta = types.SimpleNamespace(get_field=lambda name: types.SimpleNamespace(permlevel=1 if self.name == 'r2' else 0))
            def check_permission(self, permission): seen.append((self.name, permission))
            def has_permlevel_access_to(self, name, field, permission): return self.name != 'r2'
            def apply_fieldlevel_read_permissions(self): pass
            def get(self, field): return [1, 2]
        f.get_doc = lambda doctype, name: Doc(name)
        v = load_visualization(f)
        plain = v.relationship_data()
        self.assertNotIn('evidence_count', plain['edges'][0])
        result = v.relationship_data('1')
        self.assertEqual([edge['evidence_count'] for edge in result['edges']], [2, None])
        self.assertEqual(seen, [('r1', 'read'), ('r2', 'read')])

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

    def test_record_dossier_respects_record_permissions_and_field_restrictions(self):
        f = FakeFrappe({'Person': [{'name': 'p1', 'display_name': 'One', 'nationality': 'Iraq'},
                                   {'name': 'p2', 'display_name': 'Private'}]}, denied={('Person', 'p2')})
        f.hidden_fields.add('nationality')
        v = load_visualization(f)
        record = v.record_detail('Person', 'p1')
        self.assertEqual(record['label'], 'One')
        self.assertNotIn('nationality', record['details'])
        with self.assertRaises(PermissionError): v.record_detail('Person', 'p2')
        with self.assertRaises(ValueError): v.record_detail('User', 'Administrator')

    def test_missing_group_and_literal_label_remain_distinct(self):
        f = FakeFrappe({'Person': [{'name': '1', 'nationality': None},
                                   {'name': '2', 'nationality': 'Not recorded'}]})
        groups = load_visualization(f).structure_data('people')['children']
        self.assertEqual(len(groups), 2)
        self.assertEqual({group['key'] for group in groups}, {None, 'Not recorded'})

    def test_hierarchy_folds_count_subtrees_not_only_direct_children(self):
        rows = [{'name': f'root{i:02}', 'unit_name': f'Root {i}', 'parent_unit': None} for i in range(50)]
        rows += [{'name': 'child', 'unit_name': 'Child', 'parent_unit': 'root49'}]
        result = load_visualization(FakeFrappe({'Military Unit': rows})).structure_data('units')
        self.assertEqual(result['count'], 51)
        self.assertEqual(result['group_count'], 50)
        self.assertEqual(result['children'][-1]['folded_groups'], 2)
        self.assertEqual(sum(child['count'] for child in result['children']), 51)

    def test_unit_hierarchy_counts_orphans_cycles_and_permissions(self):
        rows = [{'name': 'a', 'unit_name': 'Alpha', 'parent_unit': None},
                {'name': 'b', 'unit_name': 'Bravo', 'parent_unit': 'a'},
                {'name': 'c', 'unit_name': 'Charlie', 'parent_unit': 'b'},
                {'name': 'x', 'unit_name': 'Cycle X', 'parent_unit': 'y'},
                {'name': 'y', 'unit_name': 'Cycle Y', 'parent_unit': 'x'},
                {'name': 'orphan', 'unit_name': 'Orphan', 'parent_unit': 'secret'},
                {'name': 'secret', 'unit_name': 'Secret', 'parent_unit': None}]
        result = load_visualization(FakeFrappe({'Military Unit': rows}, denied={('Military Unit', 'secret')})).structure_data('units')
        self.assertEqual(result['count'], 6)
        self.assertEqual(sum(child['count'] for child in result['children']), 6)
        nodes = {child['name']: child for child in result['children']}
        self.assertEqual(nodes['a']['count'], 3)
        self.assertEqual(nodes['x']['count'], 2)
        self.assertEqual(nodes['orphan']['count'], 1)
        self.assertNotIn('secret', nodes)
        self.assertTrue(nodes['a']['target'])

    def test_region_hierarchy_respects_parent_and_permissions(self):
        rows = [{'name': 'root', 'region_name': 'Region', 'parent_region': None},
                {'name': 'child', 'region_name': 'Area', 'parent_region': 'root'}]
        result = load_visualization(FakeFrappe({'Command Region': rows})).structure_data('regions')
        self.assertEqual(result['count'], 2)
        self.assertEqual(result['children'][0]['count'], 2)
        self.assertEqual(result['children'][0]['children'][0]['name'], 'child')

    def test_regions_units_composite_counts_and_does_not_expose_private_parents(self):
        f = FakeFrappe({
            'Command Region': [{'name': 'r1', 'region_name': 'Region One', 'parent_region': None},
                               {'name': 'secret-region', 'region_name': 'Private', 'parent_region': None}],
            'Military Unit': [{'name': 'u1', 'unit_name': 'Unit One', 'parent_unit': None, 'region': 'r1'},
                              {'name': 'u2', 'unit_name': 'Unit Two', 'parent_unit': 'u1', 'region': 'r1'},
                              {'name': 'u3', 'unit_name': 'Unit Three', 'parent_unit': None, 'region': 'secret-region'},
                              {'name': 'u4', 'unit_name': 'Unit Four', 'parent_unit': 'u1', 'region': None},
                              {'name': 'hidden-unit', 'unit_name': 'Hidden', 'parent_unit': None, 'region': 'r1'}]},
            denied={('Command Region', 'secret-region'), ('Military Unit', 'hidden-unit')})
        v = load_visualization(f)
        result = v.structure_data('regions-units')
        self.assertEqual(result['count'], 5)
        self.assertEqual(sum(node['count'] for node in result['children']), 5)
        region = next(node for node in result['children'] if node.get('name') == 'r1')
        self.assertEqual(region['count'], 3)
        self.assertEqual(region['children'][0]['target_doctype'], 'Military Unit')
        self.assertEqual(region['children'][0]['children'][0]['name'], 'u2')
        orphan = next(node for node in result['children'] if not node.get('target'))
        self.assertEqual(orphan['count'], 2)
        self.assertNotIn('secret-region', str(result))
        self.assertNotIn('hidden-unit', str(result))
        f.denied.add('Military Unit')
        result = v.structure_data('regions-units')
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['unavailable_types'], ['Military Unit'])

    def test_units_operations_composite_counts_and_field_permissions(self):
        f = FakeFrappe({
            'Military Unit': [{'name': 'unit', 'unit_name': 'Unit', 'parent_unit': None}],
            'Operational Deployment': [{'name': 'd1', 'deployment_name': 'Deployment', 'unit': 'unit'},
                                       {'name': 'd2', 'deployment_name': 'Unassigned', 'unit': None}],
            'Mission': [{'name': 'm1', 'mission_name': 'Mission', 'unit': 'unit'}],
            'Training Exercise': [{'name': 't1', 'exercise_name': 'Training', 'unit': 'unit'}],
        })
        v = load_visualization(f)
        result = v.structure_data('units-ops')
        self.assertEqual(result['count'], 5)
        unit = next(node for node in result['children'] if node.get('name') == 'unit')
        self.assertEqual(unit['count'], 4)
        self.assertEqual({node['target_doctype'] for node in unit['children']},
                         {'Operational Deployment', 'Mission', 'Training Exercise'})
        self.assertEqual(sum(node['count'] for node in result['children']), 5)
        f.hidden_fields.add('unit')
        with self.assertRaises(PermissionError): v.structure_data('units-ops')

    def test_maps_scan_beyond_old_cutoff(self):
        people = [{'name': str(i).zfill(5), 'display_name': f'Person {i}', 'latitude': 1, 'longitude': 2} for i in range(1601)]
        relationships = [{'name': str(i).zfill(5), 'subject_type': 'Person', 'subject': str(i).zfill(5),
                          'object_type': 'Person', 'object': '00000'} for i in range(1601)]
        result = load_visualization(FakeFrappe({'Person': people, 'Relationship': relationships}))
        self.assertEqual(len(result.relationship_data()['edges']), 1601)
        self.assertEqual(len(result.geographic_data()['points']), 1601)

    def test_structure_record_leaves_have_bounded_explicit_tail(self):
        f = FakeFrappe({'Person': [{'name': str(i).zfill(3), 'display_name': 'Person ' + str(i),
                                    'nationality': 'Iraq', 'classification': 'A', 'workflow_state': 'Draft'}
                                   for i in range(60)]}, denied={('Person', '000')})
        result = load_visualization(f).structure_data('people')
        group = result['children'][0]['children'][0]['children'][0]
        self.assertEqual(group['count'], 59)
        self.assertEqual(group['record_count'], 59)
        self.assertEqual(len(group['children']), 49)
        self.assertEqual(group['children'][0]['name'], '001')
        self.assertEqual(group['children'][-1]['folded_records'], 11)
        self.assertEqual(sum(child['count'] for child in group['children']), 59)

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

    def test_full_scan_and_denied_doctype(self):
        f = FakeFrappe({'Person': [{'name': str(i)} for i in range(1600)]}, denied={'Event'})
        v = load_visualization(f)
        self.assertEqual(len(v._records('Person', [])[0]), 1600)
        self.assertFalse(v._records('Person', [])[1])
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
        for field in ['relationship_type', 'subject_type', 'subject', 'object_type', 'object', 'direction', 'description', 'workflow_state', 'is_current', 'end_date', 'authentication_level', 'primary_source']:
            with self.subTest(doctype='Relationship', field=field):
                self.assertIn(field, specs['Relationship'])
                self.assertFalse(specs['Relationship'][field].get('permlevel'))
        for dt, fields in v.DETAIL_FIELDS.items():
            for field in fields:
                with self.subTest(doctype=dt, field=field):
                    self.assertIn(field, specs[dt])
                    self.assertFalse(specs[dt][field].get('permlevel'))
        for dt, fields in {'Military Unit': ('parent_unit', 'region'), 'Command Region': ('parent_region',),
                           'Operational Deployment': ('unit',), 'Mission': ('unit',), 'Training Exercise': ('unit',)}.items():
            for field in fields:
                with self.subTest(doctype=dt, field=field):
                    self.assertIn(field, specs[dt])
                    self.assertFalse(specs[dt][field].get('permlevel'))
        for dt, fields in v.STRUCTURES.values():
            for field in fields:
                with self.subTest(doctype=dt, field=field):
                    self.assertIn(field, specs[dt])
                    self.assertFalse(specs[dt][field].get('permlevel'))


if __name__ == '__main__':
    unittest.main()
