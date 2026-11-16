"""Reference data installer tests without a live Frappe bench."""
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
DT_ROOT = ROOT / 'siraj_research/siraj_research/doctype'
DATA = ROOT / 'siraj_research/setup/reference_data'


class FakeDocument:
    def __init__(self, api, values):
        self.api = api
        self.__dict__.update(values)

    def insert(self, ignore_permissions=False):
        assert ignore_permissions
        dt = self.doctype
        self.name = (self.workflow_state_name if dt == 'Workflow State' else
                     self.code if dt in ('Governorate', 'District', 'Municipality', 'Village', 'Community') else self.label_en)
        if self.name.casefold() in self.api.names[dt]:
            raise AssertionError(f'duplicate name {dt} {self.name}')
        if hasattr(self, 'code') and self.code.casefold() in self.api.codes[dt]:
            raise AssertionError(f'duplicate code {dt} {self.code}')
        self.api.add(self.__dict__)
        return self

    def save(self, ignore_permissions=False):
        assert ignore_permissions
        self.api.docs[self.doctype][self.name] = {k: v for k, v in self.__dict__.items() if k != 'api'}
        return self


class FakeFrappe(types.ModuleType):
    def __init__(self):
        super().__init__('frappe')
        from collections import defaultdict
        self.docs = defaultdict(dict)
        self.names = defaultdict(dict)
        self.codes = defaultdict(dict)
        self.db = types.SimpleNamespace(exists=self.exists)

    def add(self, values):
        record = {k: v for k, v in values.items() if k != 'api'}
        dt, name = record['doctype'], record['name']
        self.docs[dt][name] = record
        self.names[dt][name.casefold()] = name
        if record.get('code'):
            self.codes[dt][record['code'].casefold()] = name

    def exists(self, doctype, name_or_filters):
        if isinstance(name_or_filters, dict):
            return self.codes[doctype].get(str(name_or_filters['code']).casefold())
        return self.names[doctype].get(str(name_or_filters).casefold())

    def get_all(self, doctype, fields, limit_page_length):
        assert limit_page_length == 0
        return [{field: row.get(field) for field in fields} for row in self.docs[doctype].values()]

    def get_doc(self, values):
        return FakeDocument(self, values)


def load(frappe):
    spec = importlib.util.spec_from_file_location('master_data_test', ROOT / 'siraj_research/setup/master_data.py')
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'frappe': frappe}):
        spec.loader.exec_module(module)
    return module


class MasterDataTest(unittest.TestCase):
    def setUp(self):
        self.frappe = FakeFrappe()
        for row in json.loads((DATA / 'countries.json').read_text(encoding='utf8')):
            self.frappe.add({'doctype': 'Country', 'name': 'Syrian Arab Republic' if row['code'] == 'SY' else row['label_en'], 'code': row['code'].lower()})
        self.seed = load(self.frappe)

    def test_complete_fresh_install_and_repeat_preserve_existing(self):
        result = self.seed.seed_master_data()
        self.assertEqual(result['skipped'], {})
        self.assertEqual(result['created']['Governorate'], 4011)
        self.assertEqual(result['created']['District'], 1416)
        self.assertEqual(result['created']['Municipality'], 8)
        self.assertEqual(result['created']['Village'], 69)
        self.assertEqual(result['created']['Community'], 3)
        self.assertEqual(result['created']['Relationship Type'], 34)
        self.assertEqual(result['created']['Leadership Quality'], 12)
        self.assertEqual(len(self.frappe.docs['Workflow State']), 8)
        self.assertEqual(self.frappe.docs['Person Category']['Military']['code'], 'military')
        self.assertEqual(self.frappe.docs['Relationship Type']['Student of']['inverse_type'], 'Teacher of')
        self.assertEqual(self.frappe.docs['Relationship Type']['Colleague of']['is_symmetric'], 1)
        gov = self.frappe.docs['Governorate']['SY-DI']
        self.assertEqual(gov['country'], 'Syrian Arab Republic')
        district = self.frappe.docs['District']['SY-DI-DM']
        self.assertEqual(district['governorate'], 'SY-DI')
        self.assertEqual(district['country'], gov['country'])
        village = self.frappe.docs['Village']['SY-DI-DM-DM-MD']
        self.assertEqual((village['municipality'], village['district'], village['governorate'], village['country']), ('SY-DI-DM-DM', 'SY-DI-DM', 'SY-DI', gov['country']))
        self.frappe.docs['Person Category']['Military']['label_ar'] = 'custom label'
        self.frappe.docs['Relationship Type']['Student of']['inverse_type'] = None
        again = self.seed.seed_master_data()
        self.assertEqual(again['created'], {})
        self.assertEqual(again['skipped'], {})
        self.assertEqual(self.frappe.docs['Person Category']['Military']['label_ar'], 'custom label')
        self.assertIsNone(self.frappe.docs['Relationship Type']['Student of']['inverse_type'])
        self.assertEqual(len(self.frappe.docs['Person']), 0)
        self.assertEqual(len(self.frappe.docs['Military Unit']), 0)

    def test_missing_and_conflicting_parents_never_create_wrong_hierarchy(self):
        self.frappe.docs['Country'].pop('Syrian Arab Republic')
        self.frappe.add({'doctype': 'Governorate', 'name': 'IQ-BG', 'code': 'IQ-BG', 'country': 'wrong-country'})
        report = self.seed.SeedReport()
        self.seed._seed_geography(self.seed._load('lookups.json'), report)
        self.assertNotIn('SY-DI', self.frappe.docs['Governorate'])
        self.assertNotIn('SY-DI-DM', self.frappe.docs['District'])
        self.assertNotIn('IQ-BG-KR', self.frappe.docs['District'])
        self.assertGreater(report.skipped['Governorate'], 0)
        self.assertEqual(self.frappe.docs['Governorate']['IQ-BG']['country'], 'wrong-country')

    def test_existing_name_collision_is_not_overwritten(self):
        self.frappe.add({'doctype': 'Person Category', 'name': 'Military', 'code': 'custom', 'label_en': 'Military', 'label_ar': 'custom'})
        report = self.seed.SeedReport()
        self.seed._seed_lookups(self.seed._load('lookups.json'), report)
        self.assertEqual(self.frappe.docs['Person Category']['Military']['code'], 'custom')
        self.assertEqual(report.skipped['Person Category'], 1)

    def test_seed_metadata_maps_to_valid_doctypes(self):
        metadata = {}
        for path in DT_ROOT.glob('*/*.json'):
            doc = json.loads(path.read_text(encoding='utf8'))
            metadata[doc['name']] = doc
        data = self.seed._load('lookups.json')
        for domain, doctype in self.seed.DOMAIN_TYPES.items():
            self.assertIn(doctype, metadata)
            fields = {f['fieldname'] for f in metadata[doctype]['fields']}
            self.assertTrue({'code', 'label_en', 'label_ar', 'color', 'sort_order', 'disabled', 'is_system'} <= fields)
            for code, en, ar, order, meta, color in data['domains'][domain]:
                self.assertTrue(code and en and ar)
                self.assertIn(color, self.seed.COLORS)
                self.assertNotEqual(en, doctype)


if __name__ == '__main__':
    unittest.main()
