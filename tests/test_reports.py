"""Report schema and permission tests against a Frappe-v15-shaped stub."""
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(path, name, injected):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, injected):
        spec.loader.exec_module(module)
    return module


class FrappeStub(types.SimpleNamespace):
    def __init__(self):
        self._ = lambda s: s
        self.rows = {}
        self.denied = set()
        self.db = types.SimpleNamespace(exists=lambda dt, name: any(r['name'] == name for r in self.rows.get(dt, [])))
        self.meta = {}
        for p in (ROOT / 'siraj_research/siraj_research/doctype').glob('*/*.json'):
            d = json.loads(p.read_text(encoding='utf-8'))
            self.meta[d['name']] = {f['fieldname'] for f in d.get('fields', [])} | {'name'}

    def has_permission(self, doctype=None, ptype='read', doc=None, user=None, throw=False, *, parent_doctype=None, debug=False, ignore_share_permissions=False):
        return doctype not in self.denied and (doctype, doc) not in self.denied

    def get_list(self, doctype, fields, filters, order_by, limit_start, limit_page_length):
        assert set(fields) <= self.meta[doctype], (doctype, fields)
        assert set(filters) <= self.meta[doctype], (doctype, filters)
        rows = [r for r in self.rows.get(doctype, []) if all(r.get(k) == v for k, v in filters.items())]
        return [{f: r.get(f) for f in fields} for r in rows[limit_start:limit_start + limit_page_length]]


class ReportTest(unittest.TestCase):
    def setUp(self):
        self.frappe = FrappeStub()
        self.access = load('siraj_research/report_access.py', 'test_report_access', {'frappe': self.frappe})
        self.injected = {'frappe': self.frappe, 'siraj_research.report_access': self.access}

    def report(self, folder):
        return load(f'siraj_research/siraj_research/report/{folder}/{folder}.py', 'test_report_' + folder, self.injected)

    def test_relationship_report_checks_both_endpoints_and_filters(self):
        self.frappe.rows = {
            'Person': [{'name': 'p1'}, {'name': 'p2'}],
            'Institution': [{'name': 'i1'}],
            'Relationship': [
                {'name': 'r1', 'subject_type': 'Person', 'subject': 'p1', 'object_type': 'Institution', 'object': 'i1'},
                {'name': 'r2', 'subject_type': 'Person', 'subject': 'p2', 'object_type': 'Institution', 'object': 'i1'},
                {'name': 'r3', 'subject_type': 'Person', 'subject': 'p1', 'object_type': 'Institution', 'object': 'i1'},
            ],
        }
        self.frappe.denied = {('Person', 'p2'), ('Relationship', 'r3')}
        columns, rows = self.report('entity_relationship_graph').execute({'subject_type': 'Person'})
        self.assertEqual([r['name'] for r in rows], ['r1'])
        self.assertEqual([c['fieldname'] for c in columns][1:3], ['subject_type', 'subject'])

    def test_military_report_uses_existing_fields_and_hides_parent(self):
        self.frappe.rows['Military Unit'] = [
            {'name': 'u1', 'unit_name': 'One', 'parent_unit': 'secret'},
            {'name': 'secret', 'unit_name': 'Secret'},
        ]
        self.frappe.denied.add(('Military Unit', 'secret'))
        _, rows = self.report('military_force_structure').execute({'unit': 'u1'})
        self.assertEqual(rows[0]['unit_name'], 'One')
        self.assertIsNone(rows[0]['parent_unit'])

    def test_quality_report_counts_only_visible_records(self):
        self.frappe.rows['Person'] = [
            {'name': 'p1', 'workflow_state': 'Draft'},
            {'name': 'p2', 'workflow_state': 'Verified'},
            {'name': 'p3', 'workflow_state': 'In Review'},
        ]
        self.frappe.denied = {('Person', 'p2'), 'Event'}
        _, rows = self.report('data_quality_&_verification_summary').execute()
        person = next(row for row in rows if row['doctype_name'] == 'Person')
        self.assertEqual((person['total_records'], person['draft_count'], person['in_review_count'], person['verified_count']), (2, 1, 1, 0))
        self.assertNotIn('Event', [row['doctype_name'] for row in rows])

    def test_batches_do_not_drop_visible_rows(self):
        self.frappe.rows['Person'] = [{'name': 'p' + str(i)} for i in range(5)]
        self.frappe.denied = {('Person', 'p1')}
        self.assertEqual(len(list(self.access.readable_rows('Person', [], page_size=2))), 4)


if __name__ == '__main__':
    unittest.main()
