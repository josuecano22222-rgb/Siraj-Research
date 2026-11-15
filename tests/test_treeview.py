"""Tree root, actual parent fields and access checks, without a bench."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(path, name, modules):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module


class FrappeStub(types.SimpleNamespace):
    def __init__(self):
        super().__init__()
        self._ = lambda value: value
        self.PermissionError = PermissionError
        self.ValidationError = ValueError
        self.rows = {}
        self.denied = set()
        self.db = types.SimpleNamespace(exists=lambda dt, name: any(row['name'] == name for row in self.rows.get(dt, [])))

    def whitelist(self):
        return lambda fn: fn

    def has_permission(self, doctype=None, ptype='read', doc=None, user=None, throw=False, *, parent_doctype=None, debug=False, ignore_share_permissions=False):
        return doctype not in self.denied and (doctype, doc) not in self.denied

    def throw(self, msg, error):
        raise error(msg)

    def get_list(self, doctype, fields, filters, order_by, limit_start, limit_page_length):
        def matches(row):
            for field, val in filters.items():
                actual = row.get(field)
                if val == ['is', 'not set']:
                    if actual not in ('', None): return False
                elif val == ['<', 2]:
                    if (actual or 0) >= 2: return False
                elif actual != val: return False
            return True
        rows = sorted(filter(matches, self.rows.get(doctype, [])), key=lambda row: row['name'])
        return [{f: row.get(f) for f in fields} for row in rows[limit_start:limit_start + limit_page_length]]


class TreeTest(unittest.TestCase):
    def setUp(self):
        self.frappe = FrappeStub()
        access = load('siraj_research/report_access.py', 'tree_test_access', {'frappe': self.frappe})
        self.tree = load('siraj_research/treeview.py', 'tree_test', {'frappe': self.frappe, 'siraj_research.report_access': access})

    def test_empty_root_and_multiple_roots(self):
        self.assertEqual(self.tree.get_children('Military Unit'), [])
        self.frappe.rows['Military Unit'] = [
            {'name': 'A', 'unit_name': 'Alpha', 'parent_unit': None, 'is_group': 1},
            {'name': 'B', 'unit_name': 'Beta', 'parent_unit': '', 'is_group': 0},
            {'name': 'C', 'unit_name': 'Child', 'parent_unit': 'A', 'is_group': 0},
        ]
        self.assertEqual([r['value'] for r in self.tree.get_children('Military Unit')], ['A', 'B'])
        self.assertEqual([r['value'] for r in self.tree.get_children('Military Unit', 'A')], ['C'])

    def test_denied_and_other_doctypes_are_not_exposed(self):
        self.frappe.rows['Place'] = [{'name': 'P', 'is_group': 1}, {'name': 'C', 'parent_place': 'P'}]
        self.frappe.denied.add(('Place', 'P'))
        self.assertEqual(self.tree.get_children('Place'), [])
        with self.assertRaises(PermissionError): self.tree.get_children('Place', 'P')
        with self.assertRaises(ValueError): self.tree.get_children('User')
        self.frappe.denied.add('Command Region')
        with self.assertRaises(PermissionError): self.tree.get_children('Command Region')

    def test_pagination_is_not_limited_to_twenty(self):
        self.frappe.rows['Command Region'] = [{'name': str(i).zfill(3), 'region_name': str(i)} for i in range(230)]
        self.assertEqual(len(self.tree.get_children('Command Region')), 230)


if __name__ == '__main__':
    unittest.main()
