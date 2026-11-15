"""Schema and isolation tests for synthetic fixture (not a live Frappe test)."""
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
        return next(iter(records), None) if name == {} else name if name in records else None
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
        with self.assertRaisesRegex(RuntimeError, 'empty operational registry'):
            self.module.seed_test_data()

    def test_refuses_wrong_site_or_config_before_any_writes(self):
        for site, config in [('frappe.com', 'frappe.com'), ('siraj.test.localhost', None), ('siraj.test.localhost', 'other.test.localhost')]:
            with self.subTest(site=site, config=config):
                self.frappe.local.site = site
                self.frappe.conf['siraj_test_fixture_site'] = config
                with self.assertRaisesRegex(RuntimeError, 'separate'):
                    self.module.seed_test_data()
                self.assertEqual(set(self.frappe.records), {'Country', 'Person Category', 'Workflow State', 'DocType'})

    def test_failure_rolls_back(self):
        self.frappe.fail_on = 'Mission'
        with self.assertRaisesRegex(ValueError, 'simulated'):
            self.module.seed_test_data()
        self.assertTrue(self.frappe.rolled_back)
        self.assertEqual(set(self.frappe.records), {'Country', 'Person Category', 'Workflow State', 'DocType'})


if __name__ == '__main__':
    unittest.main()
