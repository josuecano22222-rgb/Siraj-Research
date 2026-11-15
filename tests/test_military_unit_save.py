"""Military Unit save hooks and parent-linked calculations without Frappe."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeFrappe(types.ModuleType):
    def __init__(self):
        super().__init__('frappe')
        self._ = lambda x: x
        self.ValidationError = ValueError
        self.rows = {}
        self.denied = set()
        self.db = types.SimpleNamespace(get_value=self.get_value, set_value=self.set_value)

    def whitelist(self):
        return lambda fn: fn

    def throw(self, message, exception=None, **kwargs):
        raise (exception or ValueError)(message)

    def get_value(self, doctype, name, field):
        assert doctype == 'Military Unit'
        return self.rows.get(name, {}).get(field)

    def set_value(self, doctype, name, field, value, update_modified=True):
        assert doctype == 'Military Unit'
        self.rows[name][field] = value

    def get_all(self, doctype, filters, pluck=None, fields=None, **kwargs):
        assert doctype == 'Military Unit'
        field, (_, values) = next(iter(filters.items()))
        rows = [dict(name=name, **data) for name, data in sorted(self.rows.items()) if (name if field == 'name' else data.get(field)) in values]
        if pluck:
            return [row[pluck] for row in rows]
        return [types.SimpleNamespace(total=sum(row.get('direct_personnel', 0) or 0 for row in rows))]


class Document:
    doctype = 'Military Unit'
    def get(self, field):
        return getattr(self, field, None)
    def is_new(self):
        return self.new
    def get_doc_before_save(self):
        return self.before
    def check_permission(self, permission):
        if self.denied:
            raise PermissionError()


class MilitaryUnitTest(unittest.TestCase):
    def setUp(self):
        self.f = FakeFrappe()
        self.f.rows = {
            'A': {'parent_unit': None, 'direct_personnel': 1},
            'B': {'parent_unit': 'A', 'direct_personnel': 2},
            'C': {'parent_unit': 'B', 'direct_personnel': 3},
            'D': {'parent_unit': None, 'direct_personnel': 4},
        }
        modules = {'frappe': self.f, 'frappe.model': types.ModuleType('frappe.model'),
                   'frappe.model.document': types.SimpleNamespace(Document=Document)}
        with patch.dict(sys.modules, modules):
            self.helpers = load('test_military_helpers', 'siraj_research/utils/military.py')
            modules['siraj_research.utils.military'] = self.helpers
            modules['siraj_research.report_access'] = types.SimpleNamespace(
                readable_rows=lambda dt, fields, filters: ({'name': n} for n in filters['name'][1] if n not in self.f.denied))
            with patch.dict(sys.modules, modules):
                self.controller = load('test_military_controller', 'siraj_research/siraj_research/doctype/military_unit/military_unit.py')

    def unit(self, name, parent, personnel, new=False, before=None):
        unit = self.controller.MilitaryUnit()
        unit.name, unit.parent_unit, unit.direct_personnel = name, parent, personnel
        unit.new, unit.before, unit.denied = new, before, False
        unit.commander, unit.armaments = None, []
        return unit

    def test_new_save_hook_does_not_access_nested_set_columns(self):
        unit = self.unit('N', 'A', 5, new=True)
        unit.validate()
        self.assertEqual(unit.subtree_personnel, 5)
        self.f.rows['N'] = {'parent_unit': 'A', 'direct_personnel': 5}
        unit.on_update()
        self.assertEqual(self.f.rows['A']['subtree_personnel'], 11)

    def test_edit_and_reparent_recalculate_both_chains(self):
        unit = self.unit('B', 'D', 8, before=types.SimpleNamespace(parent_unit='A'))
        unit.validate()
        self.assertEqual(unit.subtree_personnel, 11)
        self.f.rows['B'].update(parent_unit='D', direct_personnel=8)
        unit.on_update()
        self.assertEqual(self.f.rows['A']['subtree_personnel'], 1)
        self.assertEqual(self.f.rows['D']['subtree_personnel'], 15)
        self.assertTrue(self.helpers.is_ancestor('Military Unit', 'D', 'C'))
        self.assertFalse(self.helpers.is_ancestor('Military Unit', 'A', 'C'))

    def test_delete_updates_ancestors(self):
        del self.f.rows['C']
        self.unit('C', 'B', 3).after_delete()
        self.assertEqual(self.f.rows['B']['subtree_personnel'], 2)
        self.assertEqual(self.f.rows['A']['subtree_personnel'], 3)

    def test_rejects_cycle_and_checks_all_children(self):
        with self.assertRaises(ValueError):
            self.unit('A', 'C', 1).validate_parent()
        self.f.rows['A']['parent_unit'] = 'C'
        with self.assertRaises(ValueError): self.helpers.descendants('Military Unit', 'A')
        with self.assertRaises(ValueError): self.helpers.ancestors('Military Unit', 'A')
        self.f.rows['A']['parent_unit'] = None
        for i in range(230): self.f.rows[f'x{i}'] = {'parent_unit': 'D', 'direct_personnel': 1}
        self.assertEqual(len(self.helpers.descendants('Military Unit', 'D')), 230)
        self.assertEqual(self.helpers.subtree_personnel('Military Unit', 'D'), 234)

    def test_exposed_descendants_filter_permissions(self):
        self.f.denied.add('B')
        unit = self.unit('A', None, 1)
        self.assertEqual(unit.get_descendants(), ['C'])
        unit.denied = True
        with self.assertRaises(PermissionError): unit.get_descendants()


if __name__ == '__main__':
    unittest.main()
