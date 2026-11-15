"""Schema and isolation tests for synthetic fixture (not a live Frappe test)."""
import ast
import copy
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = {}
for path in (ROOT / 'siraj_research/siraj_research/doctype').glob('*/*.json'):
    data = json.loads(path.read_text(encoding='utf8'))
    SCHEMAS[data['name']] = data


class FakeDoc:
    def __init__(self, api, values):
        self.api = api
        self.values = dict(values)
        self.doctype = values['doctype']
        fields = SCHEMAS[self.doctype]['fields']
        self.meta = types.SimpleNamespace(get_table_fields=lambda: [types.SimpleNamespace(fieldname=f['fieldname']) for f in fields if f['fieldtype'] in ('Table', 'Table MultiSelect')])

    def insert(self, ignore_permissions=False):
        assert ignore_permissions
        if self.api.fail_on == self.doctype:
            raise ValueError('simulated insert failure')
        schema = SCHEMAS[self.doctype]
        fields = {f.get('fieldname'): f for f in schema['fields']}
        unknown = set(self.values) - set(fields) - {'doctype'}
        if unknown:
            raise AssertionError(f'{self.doctype}: unknown fields {unknown}')
        for name, field in fields.items():
            if not name:
                continue
            val = self.values.get(name, field.get('default'))
            if field.get('reqd') and (val is None or val == ''):
                raise AssertionError(f'{self.doctype}: missing {name}')
            if val and field['fieldtype'] == 'Select' and val not in field.get('options', '').splitlines():
                raise AssertionError(f'{self.doctype}: invalid {name}={val}')
            if val and field['fieldtype'] == 'Link' and not self.api.exists(field['options'], val):
                raise AssertionError(f'{self.doctype}: missing link {name}={val}')
            if val and field['fieldtype'] == 'Dynamic Link':
                if not self.api.exists(self.values[field['options']], val):
                    raise AssertionError(f'{self.doctype}: missing dynamic link {name}={val}')
            if val and field['fieldtype'] in ('Table', 'Table MultiSelect'):
                self.values[name] = [FakeChild(self.api, field['options'], row) for row in val]
        auto = schema.get('autoname', '')
        self.name = self.values[auto.split(':', 1)[1]] if auto.startswith('field:') else self.doctype + '-' + str(len(self.api.records.get(self.doctype, {})) + 1)
        if self.api.exists(self.doctype, self.name):
            raise ValueError('duplicate')
        self.api.records.setdefault(self.doctype, {})[self.name] = self
        return self

    def get(self, field):
        return self.values.get(field)


class FakeChild:
    def __init__(self, api, doctype, values):
        self.doctype = doctype
        fields = {f.get('fieldname'): f for f in SCHEMAS[doctype]['fields']}
        assert not (set(values) - set(fields)), (doctype, values)
        for key, field in fields.items():
            if field.get('reqd') and values.get(key, field.get('default')) in (None, ''):
                raise AssertionError(f'{doctype}: missing {key}')
            if values.get(key) and field['fieldtype'] == 'Link' and not api.exists(field['options'], values[key]):
                raise AssertionError(f'{doctype}: missing link {key}')


class FakeFrappe(types.ModuleType):
    def __init__(self):
        super().__init__('frappe')
        self.local = types.SimpleNamespace(site='siraj.test.localhost')
        self.conf = {'siraj_test_fixture_site': self.local.site}
        self.records = {'Country': {'Iraq': object()}, 'Person Category': {'Military': object()}, 'Workflow State': {'Draft': object()}, 'DocType': {'SIRAJ Settings': object()}}
        self.initial = copy.deepcopy(self.records)
        self.fail_on = None
        self.rolled_back = False
        self.db = types.SimpleNamespace(exists=self.exists, rollback=self.rollback)
    def exists(self, doctype, name):
        records = self.records.get(doctype, {})
        if isinstance(name, dict):
            for record_name, record in records.items():
                values = record.values if isinstance(record, FakeDoc) else record if isinstance(record, dict) else {}
                if all(values.get(key) == value for key, value in name.items()):
                    return record_name
            return None
        return name if name in records else None
    def get_doc(self, values):
        return FakeDoc(self, values)
    def rollback(self):
        self.records = self.initial
        self.rolled_back = True


def load(fake):
    spec = importlib.util.spec_from_file_location('siraj_test_fixture', ROOT / 'siraj_research/setup/test_data.py')
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'frappe': fake}):
        spec.loader.exec_module(module)
    return module


class FixtureTest(unittest.TestCase):
    def setUp(self):
        self.frappe = FakeFrappe()
        self.module = load(self.frappe)

    def test_coverage_links_and_repeat_guard(self):
        result = self.module.seed_test_data()
        self.assertEqual(set(result['created']) | {result['existing_singleton']}, set(SCHEMAS))
        self.assertEqual(result['created']['Relationship'], 5)
        self.assertEqual(result['created']['Military Unit'], 2)
        self.assertTrue(all(result['created'][name] for name in self.module.CHILD_TYPES))
        with self.assertRaisesRegex(RuntimeError, 'Sample identifier already exists'):
            self.module.seed_test_data()

    def test_existing_operational_data_is_preserved_and_samples_are_marked(self):
        self.frappe.local.site = 'frappe.com'
        original = {'name_en': 'A real record'}
        self.frappe.records['Person'] = {'PER-REAL': original}
        result = self.module.seed_test_data()
        self.assertIs(self.frappe.records['Person']['PER-REAL'], original)
        self.assertEqual(original, {'name_en': 'A real record'})
        for doctype in self.module.OPERATIONAL_TYPES:
            for name in result['created_names'][doctype]:
                doc = self.frappe.records[doctype][name]
                self.assertIn('TEST SAMPLE', doc.values['researcher_notes'])
        self.assertEqual(result['site'], 'frappe.com')
        self.assertNotIn('PER-REAL', result['created_names']['Person'])

    def test_collision_or_missing_prerequisite_rejected_before_writes(self):
        self.frappe.records['Person Status'] = {'custom': {'code': 'TEST_PERSON_STATUS'}}
        before = set(self.frappe.records)
        with self.assertRaisesRegex(RuntimeError, 'Sample identifier already exists in Person Status'):
            self.module.seed_test_data()
        self.assertEqual(set(self.frappe.records), before)
        del self.frappe.records['Person Status']
        del self.frappe.records['Country']['Iraq']
        with self.assertRaisesRegex(RuntimeError, 'Missing fixture prerequisite'):
            self.module.seed_test_data()
        self.assertEqual(set(self.frappe.records), before - {'Person Status'})

    def test_late_name_collision_is_checked_before_any_insertion(self):
        self.frappe.records['Unit Classification'] = {'TEST Unit Classification': {'classification_name': 'TEST Unit Classification'}}
        before = copy.deepcopy(self.frappe.records)
        with self.assertRaisesRegex(RuntimeError, 'Unit Classification'):
            self.module.seed_test_data()
        self.assertEqual(self.frappe.records['Unit Classification'], before['Unit Classification'])
        self.assertFalse(self.frappe.rolled_back)
        self.assertNotIn('Authentication Level', self.frappe.records)

    def test_missing_app_is_rejected(self):
        self.frappe.records['DocType'].clear()
        with self.assertRaisesRegex(RuntimeError, 'Install siraj_research'):
            self.module.seed_test_data()

    def test_fixture_is_not_a_hook_or_whitelisted_endpoint(self):
        root = ROOT / 'siraj_research'
        for path in (root / 'hooks.py', root / 'setup/install.py', root / 'setup/master_data.py'):
            with self.subTest(path=str(path)):
                self.assertNotIn('seed_test_data', path.read_text(encoding='utf8'))
        tree = ast.parse((root / 'setup/test_data.py').read_text(encoding='utf8'))
        target = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'seed_test_data')
        self.assertEqual(target.decorator_list, [])

    def test_failure_rolls_back(self):
        self.frappe.records['Person'] = {'PER-REAL': {'name_en': 'A real record'}}
        self.frappe.initial = copy.deepcopy(self.frappe.records)
        self.frappe.fail_on = 'Mission'
        with self.assertRaisesRegex(ValueError, 'simulated'):
            self.module.seed_test_data()
        self.assertTrue(self.frappe.rolled_back)
        self.assertEqual(set(self.frappe.records), {'Country', 'Person Category', 'Workflow State', 'DocType', 'Person'})
        self.assertEqual(self.frappe.records['Person']['PER-REAL']['name_en'], 'A real record')


if __name__ == '__main__':
    unittest.main()
