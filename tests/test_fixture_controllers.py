"""Exercise fixture order against bundled controllers with a fake database.

This is not Frappe integration testing: framework lifecycle, SQL, hooks,
permissions and integrations are only represented by small stubs.
"""
import datetime
import importlib.util
import sys
import types
import unittest
from unittest.mock import patch

from test_test_data import FakeChild, FakeDoc, FakeFrappe, ROOT, SCHEMAS, load


class ControllerDocument:
    def __init__(self, doc):
        object.__setattr__(self, '_doc', doc)
        object.__setattr__(self, 'name', doc.name)
        object.__setattr__(self, 'doctype', doc.doctype)

    def __getattr__(self, name):
        value = self._doc.values.get(name)
        if value is None:
            field = next((f for f in SCHEMAS[self.doctype]['fields'] if f.get('fieldname') == name), {})
            value = field.get('default')
            if field.get('fieldtype') in ('Check', 'Int', 'Float') and value is not None:
                value = float(value) if field['fieldtype'] == 'Float' else int(value)
        return value

    def __setattr__(self, name, value):
        self._doc.values[name] = value

    def get(self, field):
        return getattr(self, field, None)

    def is_new(self):
        return True

    def get_doc_before_save(self):
        return None


def import_file(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ControllerFixtureTest(unittest.TestCase):
    def test_fixture_against_bundled_controller_validations(self):
        f = FakeFrappe()
        f._ = lambda text: text
        f.ValidationError = ValueError
        f.throw = lambda message, *args, **kwargs: (_ for _ in ()).throw(ValueError(message))
        f.msgprint = lambda *args, **kwargs: None
        f.whitelist = lambda: (lambda fn: fn)
        utils = types.ModuleType('frappe.utils')
        utils.getdate = lambda value=None: datetime.date.fromisoformat(str(value)) if value else datetime.date.today()
        utils.date_diff = lambda a, b: (datetime.date.fromisoformat(str(a)) - datetime.date.fromisoformat(str(b))).days
        f.utils = utils

        def get_value(doctype, name, field):
            if isinstance(name, dict):
                raise AssertionError('unexpected filter query: ' + repr((doctype, name)))
            row = f.records.get(doctype, {}).get(name)
            if isinstance(row, FakeDoc):
                value = row.values.get(field)
                if value is None:
                    definition = next((f for f in SCHEMAS[doctype]['fields'] if f.get('fieldname') == field), {})
                    value = definition.get('default')
                    if definition.get('fieldtype') in ('Check', 'Int') and value is not None:
                        value = int(value)
                return value
            return row.get(field) if isinstance(row, dict) else None

        def set_value(doctype, name, field, value, **kwargs):
            f.records[doctype][name].values[field] = value

        def get_all(doctype, filters, pluck=None, fields=None, **kwargs):
            rows = []
            for name, doc in f.records.get(doctype, {}).items():
                if not isinstance(doc, FakeDoc):
                    continue
                row = {'name': name, 'docstatus': 0, **doc.values}
                def matches(field, value):
                    if isinstance(value, (list, tuple)):
                        op, operand = value
                        if op == 'in': return row.get(field) in operand
                        if op == '!=': return row.get(field) != operand
                        if op == '<': return row.get(field) < operand
                        raise AssertionError(op)
                    return row.get(field) == value
                if all(matches(field, value) for field, value in filters.items()):
                    rows.append(row)
            if pluck:
                return [row[pluck] for row in rows]
            if fields == ['sum(direct_personnel) as total']:
                return [types.SimpleNamespace(total=sum(row.get('direct_personnel') or 0 for row in rows))]
            return [types.SimpleNamespace(**row) for row in rows]

        f.db.get_value = get_value
        f.db.set_value = set_value
        f.get_all = get_all
        modules = {'frappe': f, 'frappe.model': types.ModuleType('frappe.model'),
                   'frappe.model.document': types.SimpleNamespace(Document=ControllerDocument),
                   'frappe.utils': utils,
                   'siraj_research.report_access': types.SimpleNamespace(readable_rows=lambda *a, **k: [])}
        controllers = {}
        with patch.dict(sys.modules, modules):
            military = import_file('fixture_military_helpers', 'siraj_research/utils/military.py')
            modules['siraj_research.utils.military'] = military
            with patch.dict(sys.modules, modules):
                for slug, cls in [('person', 'Person'), ('institution', 'Institution'), ('place', 'Place'),
                                  ('source', 'Source'), ('event', 'Event'), ('relationship', 'Relationship'),
                                  ('military_unit', 'MilitaryUnit'), ('operational_deployment', 'OperationalDeployment'),
                                  ('mission', 'Mission'), ('training_exercise', 'TrainingExercise'),
                                  ('command_appointment', 'CommandAppointment')]:
                    module = import_file('fixture_controller_' + slug,
                                         f'siraj_research/siraj_research/doctype/{slug}/{slug}.py')
                    doctype = next(name for name in SCHEMAS if name.lower().replace(' ', '_') == slug)
                    controllers[doctype] = getattr(module, cls)
                fixture = load(f)

        # FakeChild supports the same attributes the controllers access.
        def child_attribute(child, name):
            return child.values.get(name)
        original_insert = FakeDoc.insert
        def insert_with_controllers(doc, ignore_permissions=False):
            # FakeDoc checks mandatory fields and requires linked records to
            # exist at this insertion point, including child and Dynamic Links.
            original_insert(doc, ignore_permissions=ignore_permissions)
            cls = controllers.get(doc.doctype)
            if cls:
                controller = cls(doc)
                for method in ('before_validate', 'validate', 'on_update'):
                    fn = getattr(controller, method, None)
                    if callable(fn):
                        fn()
            return doc

        with patch.object(FakeChild, '__getattr__', child_attribute, create=True), \
             patch.object(FakeDoc, 'insert', insert_with_controllers):
            fixture._assert_event_safe = lambda: None  # simulation only
            result = fixture.seed_test_data()
        units = [f.records['Military Unit'][name] for name in result['created_names']['Military Unit']]
        parent = next(unit for unit in units if unit.values['unit_name'] == 'TEST Parent Unit')
        self.assertEqual(parent.values['subtree_personnel'], 70)
        exercises = [f.records['Training Exercise'][name] for name in result['created_names']['Training Exercise']]
        self.assertEqual(sorted(doc.values['duration_days'] for doc in exercises), [1, 3])
        relationships = [f.records['Relationship'][name] for name in result['created_names']['Relationship']]
        self.assertEqual({doc.values['direction'] for doc in relationships}, {'Directed', 'Symmetric'})

    def test_link_checks_reject_a_missing_prerequisite(self):
        f = FakeFrappe()
        doc = f.get_doc({'doctype': 'Place', 'name_ar': 'اختبار مكان', 'place_type': 'MISSING'})
        with self.assertRaisesRegex(AssertionError, 'missing link place_type'):
            doc.insert(ignore_permissions=True)
        self.assertFalse(f.records.get('Place'))


if __name__ == '__main__':
    unittest.main()
