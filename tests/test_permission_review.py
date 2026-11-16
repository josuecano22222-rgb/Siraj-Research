"""Bench-only permission probe tests with a Frappe stub, not real permissions."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def make_probe():
    fake = types.SimpleNamespace()
    fake.session = types.SimpleNamespace(user='Administrator')
    fake.PermissionError = PermissionError
    fake.log = []
    fake.db = types.SimpleNamespace(exists=lambda dt, name: (dt, name) in {('User', 'limited'), ('DocType', 'Person'), ('Person', 'private-id')})
    fake.set_user = lambda name: (fake.log.append(('set_user', name)), setattr(fake.session, 'user', name))
    fake.get_roles = lambda user: ['SIRAJ Viewer']
    fake.get_meta = lambda dt: types.SimpleNamespace(module='Siraj Research', is_submittable=0)
    fake.get_doc = lambda dt, name: types.SimpleNamespace(doctype=dt, name=name)
    def has_permission(dt, ptype, user, throw, doc=None):
        assert fake.session.user == user == 'limited'
        fake.log.append(('check', dt, ptype, bool(doc)))
        return ptype == 'read' and doc is None
    fake.has_permission = has_permission
    fake.get_list = lambda *a, **k: []
    spec = importlib.util.spec_from_file_location('permission_review_test', ROOT / 'siraj_research/setup/permission_review.py')
    probe = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'frappe':fake}): spec.loader.exec_module(probe)
    return fake, probe


class PermissionReviewTest(unittest.TestCase):
    def test_fixed_scope_and_document_results_do_not_return_record_or_user(self):
        f, m = make_probe()
        result = m.inspect_permissions('limited', 'Person', 'private-id')
        entry = result['doctypes']['Person']
        self.assertTrue(entry['doctype_permissions']['read'])
        self.assertFalse(entry['document_permissions']['read'])
        self.assertFalse(entry['list_contains_record'])
        self.assertNotIn('create', entry['document_permissions'])
        self.assertNotIn('private-id', str(result)); self.assertNotIn('limited', str(result))
        self.assertEqual(f.session.user, 'Administrator')
        self.assertEqual(f.log[-1], ('set_user', 'Administrator'))
        self.assertFalse(hasattr(m.inspect_permissions, 'is_whitelisted'))

    def test_invalid_input_and_missing_doctypes(self):
        f, m = make_probe()
        for args in [('bad',), ('limited','User'), ('limited',None,'private-id'), ('limited','Person','missing')]:
            with self.subTest(args=args), self.assertRaises(ValueError): m.inspect_permissions(*args)
        data = m.inspect_permissions('limited')
        self.assertEqual(data['doctypes']['Event']['status'], 'doctype_missing')
        self.assertEqual(f.session.user,'Administrator')

    def test_restores_user_on_hook_error(self):
        f, m = make_probe()
        def failed(*a, **k): raise RuntimeError('hook error')
        f.has_permission = failed
        with self.assertRaises(RuntimeError): m.inspect_permissions('limited', 'Person')
        self.assertEqual(f.session.user,'Administrator')

    def test_permission_denied_list_is_safely_counted(self):
        f, m = make_probe()
        f.get_list = lambda *a, **k: (_ for _ in ()).throw(PermissionError())
        result = m.inspect_permissions('limited', 'Person', 'private-id')
        self.assertFalse(result['doctypes']['Person']['list_contains_record'])

if __name__ == '__main__': unittest.main()
