import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class InventoryTest(unittest.TestCase):
    def test_counts_effective_fields_and_surfaces_gaps_without_returning_records(self):
        f = types.ModuleType('frappe')
        rows = [{'name': n, 'issingle': n == 'Single', 'is_virtual': n == 'Virtual'}
                for n in ('A', 'Single', 'Virtual', 'Missing', 'Broken')]
        f.get_all = lambda doctype, **kw: rows
        def meta(name):
            if name == 'Broken':
                raise ValueError('secret: metadata failure')
            return types.SimpleNamespace(fields=[
                {'fieldname': 'event', 'fieldtype': 'Link', 'options': 'Event'},
                {'fieldname': 'reference_type', 'fieldtype': 'Link', 'options': 'DocType'},
                {'fieldname': 'reference', 'fieldtype': 'Dynamic Link', 'options': 'reference_type'},
                {'fieldname': 'subject_type', 'fieldtype': 'Select', 'options': 'Person\nEvent\nPlace'},
                {'fieldname': 'hidden_type', 'fieldtype': 'Dynamic Link', 'options': 'no_column'},
            ])
        f.get_meta = meta
        queries = []
        def count(doctype, filters):
            queries.append((doctype, filters))
            return 3 if 'reference_type' in filters else 0
        f.db = types.SimpleNamespace(table_exists=lambda name: name != 'Missing',
                                     has_column=lambda name, field: field != 'no_column', count=count)
        path = ROOT / 'siraj_research/setup/event_reference_inventory.py'
        spec = importlib.util.spec_from_file_location('event_reference_inventory_test', path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'frappe': f}):
            spec.loader.exec_module(module)
        result = module.inspect_metadata_event_references()
        self.assertEqual(result['nonzero_counts'], [{'doctype': 'A', 'field': 'reference_type', 'kind': 'selector', 'count': 3}])
        self.assertEqual(len(queries), 3)
        self.assertEqual(result['checked_fields'], 3)
        self.assertIn(('A', {'event': ['is', 'set']}), queries)
        self.assertIn(('A', {'subject_type': 'Event'}), queries)
        self.assertEqual({x['doctype'] for x in result['skipped']}, {'A', 'Single', 'Virtual', 'Missing', 'Broken'})
        self.assertNotIn('secret', str(result))
        self.assertIn('not proof', result['note'])

    def test_count_failure_is_reported_not_zero(self):
        f = types.ModuleType('frappe')
        f.get_all = lambda *a, **kw: [{'name': 'A'}]
        f.get_meta = lambda name: types.SimpleNamespace(fields=[{'fieldname': 'ref', 'fieldtype': 'Link', 'options': 'Event'}])
        def fail(*args): raise RuntimeError('secret value')
        f.db = types.SimpleNamespace(table_exists=lambda name: True, has_column=lambda *args: True, count=fail)
        path = ROOT / 'siraj_research/setup/event_reference_inventory.py'
        spec = importlib.util.spec_from_file_location('event_reference_inventory_failure_test', path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'frappe': f}): spec.loader.exec_module(module)
        result = module.inspect_metadata_event_references()
        self.assertEqual(result['nonzero_counts'], [])
        self.assertEqual(result['checked_fields'], 0)
        self.assertEqual(result['skipped'][0]['reason'], 'count unavailable')
        self.assertNotIn('secret', str(result))


if __name__ == '__main__': unittest.main()
