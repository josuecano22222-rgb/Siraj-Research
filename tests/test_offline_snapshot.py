"""Stub-only permission/integrity tests. Not a real Frappe security test."""
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / 'siraj_research/setup/offline_snapshot.py'


class FakeFrappe(types.ModuleType):
    def __init__(self):
        super().__init__('frappe'); self.session = types.SimpleNamespace(user='reader'); self.local = types.SimpleNamespace(site='site')
        self.denied = set(); self.hide = set(); self.rows = {
            'Person':[{'name':'public'}, {'name':'private'}, {'name':'list-hidden'}],
            'Place':[{'name':'place'}], 'Institution':[], 'Source':[],
            'Relationship':[{'name':'r1','subject_type':'Person','subject':'public','object_type':'Place','object':'place'},
                            {'name':'r2','subject_type':'Person','subject':'private','object_type':'Place','object':'place'},
                            {'name':'r3','subject_type':'Person','subject':'list-hidden','object_type':'Place','object':'place'}]}
        self.excluded = {('Person', 'list-hidden')}; self.denied.add(('Person','read','private'))
        self.calls = []
    def has_permission(self, dt, op, doc=None, throw=False):
        return (dt, op, doc) not in self.denied
    def get_list(self, dt, fields, order_by, limit_start, limit_page_length):
        self.calls.append((dt, fields))
        data = [r for r in self.rows.get(dt, []) if (dt, r['name']) not in self.excluded]
        data = sorted(data, key=lambda r:r['name'])[limit_start:limit_start+limit_page_length]
        return [{f:r.get(f) for f in fields if (dt, f) not in self.hide} for r in data]


def load(f):
    spec = importlib.util.spec_from_file_location('snapshot_test_module', PATH)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'frappe': f}): spec.loader.exec_module(module)
    return module


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.f = FakeFrappe(); self.m = load(self.f); self.key = b'x'*32
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    def issue(self): return self.m.issue_current_user(secret=self.key, now=self.now, lifetime=timedelta(hours=1))
    def test_only_authorized_list_and_document_visible_endpoints(self):
        envelope = self.issue(); payload = envelope['body']['payload']
        self.assertEqual(payload['nodes'], [{'doctype':'Person','name':'public'}, {'doctype':'Place','name':'place'}])
        self.assertEqual(len(payload['edges']),1)
        self.assertNotIn('private', str(payload)); self.assertNotIn('list-hidden', str(payload))
        self.assertTrue(self.m.verify(envelope, site='site', user='reader', secret=self.key, now=self.now))
        self.assertTrue(all(dt not in ('Event','SIRAJ Research Event') for dt, _ in self.f.calls))
        self.assertEqual(payload['edges'][0]['type'],'')
    def test_doctype_export_denial_and_relationship_denial(self):
        self.f.denied.update({('Place','export',None), ('Relationship','export',None)})
        p = self.issue()['body']['payload']
        self.assertIn('Place',p['scope']['omitted_types']); self.assertEqual(p['scope']['relationships'],'not_authorized')
        self.assertEqual(p['edges'],[]); self.assertNotIn('place', str(p['nodes']))
    def test_document_export_denial_excludes_node_and_relationship(self):
        self.f.denied.add(('Person','export','public'))
        p = self.issue()['body']['payload']
        self.assertNotIn('public', str(p))
        self.assertEqual(p['edges'], [])

    def test_missing_fields_denied_user_and_limits_fail_closed(self):
        self.f.hide.add(('Relationship','subject'))
        with self.assertRaises(self.m.SnapshotError): self.issue()
        self.f.hide.clear(); self.f.session.user='Guest'
        with self.assertRaises(self.m.SnapshotError): self.issue()
        self.f.session.user='reader'; self.m.MAX_NODES=1
        with self.assertRaises(self.m.SnapshotError): self.issue()
    def test_mac_tampering_context_expiry_and_wrong_secret(self):
        env = self.issue()
        self.assertFalse(self.m.verify(env,site='site',user='other',secret=self.key,now=self.now))
        self.assertFalse(self.m.verify(env,site='other',user='reader',secret=self.key,now=self.now))
        self.assertFalse(self.m.verify(env,site='site',user='reader',secret=b'y'*32,now=self.now))
        self.assertFalse(self.m.verify(env,site='site',user='reader',secret=self.key,now=self.now+timedelta(hours=1)))
        self.assertFalse(self.m.verify(env,site='site',user='reader',secret=self.key,now=self.now-timedelta(seconds=1)))
        for change in [lambda e:e['body']['payload']['nodes'].append({'doctype':'Person','name':'fake'}),
                       lambda e:e['body'].__setitem__('subject','other'), lambda e:e.__setitem__('mac','0'*64)]:
            altered = copy.deepcopy(env); change(altered)
            self.assertFalse(self.m.verify(altered,site='site',user='reader',secret=self.key,now=self.now))
    def test_invalid_key_time_and_malformed_tokens(self):
        with self.assertRaises(self.m.SnapshotError): self.m.issue_current_user(secret=b'bad',now=self.now,lifetime=timedelta(hours=1))
        with self.assertRaises(self.m.SnapshotError): self.m.issue_current_user(secret=self.key,now=self.now,lifetime=timedelta(days=8))
        with self.assertRaises(self.m.SnapshotError): self.m.issue_current_user(secret=self.key,now=self.now.replace(tzinfo=None),lifetime=timedelta(hours=1))
        for token in (None, {}, {'body':{},'mac':'x'}, {'body':[], 'mac':'0'*64}):
            self.assertFalse(self.m.verify(token,site='site',user='reader',secret=self.key,now=self.now))
    def test_pagination_and_relationship_document_permission(self):
        self.f.rows['Person'] = [{'name':f'p{i:03}'} for i in range(205)]
        self.f.excluded = set()
        self.f.rows['Relationship'] = [
            {'name':'allowed','subject_type':'Person','subject':'p000','object_type':'Place','object':'place'},
            {'name':'denied','subject_type':'Person','subject':'p001','object_type':'Place','object':'place'}]
        self.f.denied.add(('Relationship','export','denied'))
        p = self.issue()['body']['payload']
        self.assertEqual(len(p['nodes']), 206)
        self.assertEqual(len(p['edges']), 1)
        self.assertEqual(p['edges'][0]['source']['name'], 'p000')

    def test_session_change_fails_closed(self):
        original = self.f.get_list
        def altered(*args, **kwargs):
            result = original(*args, **kwargs)
            self.f.session.user = 'other'
            return result
        self.f.get_list = altered
        with self.assertRaises(self.m.SnapshotError): self.issue()

    def test_no_whitelist_endpoint(self):
        self.assertFalse(hasattr(self.m.collect_current_user, 'is_whitelisted'))
        self.assertNotIn('@frappe.whitelist', PATH.read_text())

if __name__ == '__main__': unittest.main()
