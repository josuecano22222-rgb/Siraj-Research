import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class EventDiagnosticsTest(unittest.TestCase):
    def test_aggregates_only_and_handles_absent_columns(self):
        queries = []
        def has_column(doctype, field):
            return field in {'title_ar', 'event_type', 'researcher_notes'} and doctype != 'Source'
        def count(doctype, filters=None):
            queries.append((doctype, filters))
            return 3 if doctype == 'Event' and filters is None else 0
        frappe = types.ModuleType('frappe')
        frappe.db = types.SimpleNamespace(has_column=has_column, count=count, table_exists=lambda doctype: True)
        frappe.get_meta = lambda doctype: types.SimpleNamespace(module='Siraj Research', get_field=lambda field: field if field in {'title_ar', 'researcher_notes'} else None)
        test_data = types.ModuleType('siraj_research.setup.test_data')
        test_data.OPERATIONAL_TYPES = ('Event', 'Source')
        spec = importlib.util.spec_from_file_location('event_diag_test', ROOT / 'siraj_research/setup/event_diagnostics.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'frappe': frappe, 'siraj_research.setup.test_data': test_data}):
            spec.loader.exec_module(module)
        output = module.inspect_event_collision()
        self.assertEqual(output['event_module'], 'Siraj Research')
        self.assertEqual(output['event_total'], 3)
        self.assertEqual(output['test_sample_marker_counts'], {'Event': 0})
        self.assertEqual(output['event_fields']['title_ar'], {'metadata': True, 'column': True})
        self.assertEqual(output['event_fields']['sync_with_google_calendar'], {'metadata': False, 'column': False})
        self.assertEqual(queries, [('Event', {'researcher_notes': ['like', 'TEST SAMPLE%']}), ('Event', None)])
        self.assertIn('not proof', output['note'])


if __name__ == '__main__':
    unittest.main()
