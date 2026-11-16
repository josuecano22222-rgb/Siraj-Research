"""Synthetic probe tests, no real Frappe or database."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / 'siraj_research/setup/link_query_probe.py'


class ProbeTest(unittest.TestCase):
    def setUp(self):
        f = types.ModuleType('frappe'); f.session = types.SimpleNamespace(user='original')
        f.db = types.SimpleNamespace(exists=lambda dt, name: name == 'user', sql=lambda *a, **k: [])
        f.set_user = lambda user: setattr(f.session, 'user', user)
        f.has_permission = lambda dt, op: True
        self.f = f; self.original = f.db.sql
        def load(path):
            def report(): f.db.sql('secret SQL', ('secret value',)); return ([], [{'name':'private'}])
            def tree(dt, parent): f.db.sql('another query'); f.db.sql('more'); return [{'value':'private'}]
            return tree if path.endswith('get_children') else report
        f.get_attr = load
        spec = importlib.util.spec_from_file_location('probe_test', PATH); self.m = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'frappe':f}): spec.loader.exec_module(self.m)
    def test_counts_without_returning_sql_or_identifiers(self):
        report = self.m.measure('user','relationship_report',2, confirm='ISOLATED-TEST-APPROVED')
        self.assertEqual([s['sql_calls'] for s in report['samples']], [1,1])
        self.assertEqual(self.f.session.user,'original'); self.assertIs(self.f.db.sql,self.original)
        self.assertNotIn('secret',str(report)); self.assertNotIn('private',str(report)); self.assertNotIn('user',str(report))
        tree = self.m.measure('user','place_tree',1,'private parent', confirm='ISOLATED-TEST-APPROVED')
        self.assertEqual(tree['samples'][0]['sql_calls'],2)
        self.assertNotIn('private',str(tree))
    def test_limits_and_restoration_on_failure(self):
        for args in [('bad','place_tree',1,'p'), ('user','place_tree',4,'p'), ('user','place_tree',1,''), ('user','unknown',1,None)]:
            with self.subTest(args=args), self.assertRaises(ValueError): self.m.measure(*args, confirm='ISOLATED-TEST-APPROVED')
        self.f.get_attr = lambda path: lambda *args: (_ for _ in ()).throw(RuntimeError('failed'))
        with self.assertRaises(RuntimeError): self.m.measure('user','place_tree',1,'p', confirm='ISOLATED-TEST-APPROVED')
        self.assertEqual(self.f.session.user,'original'); self.assertIs(self.f.db.sql,self.original)
    def test_requires_explicit_isolation_confirmation(self):
        with self.assertRaises(ValueError): self.m.measure('user','relationship_report')
        self.assertIs(self.f.db.sql,self.original)

    def test_report_requires_permission(self):
        self.f.has_permission = lambda *args: False
        with self.assertRaises(PermissionError): self.m.measure('user','relationship_report', confirm='ISOLATED-TEST-APPROVED')
        self.assertEqual(self.f.session.user,'original'); self.assertIs(self.f.db.sql,self.original)

if __name__ == '__main__': unittest.main()
