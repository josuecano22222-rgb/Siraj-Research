"""Python issuer to Node verifier, using synthetic Frappe and ephemeral keys."""
import base64
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import test_offline_snapshot

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
except ImportError:
    ec = None

PATH = Path(__file__).resolve().parents[1] / 'siraj_research/setup/offline_signed_snapshot.py'
ROOT = PATH.parents[2]


@unittest.skipIf(ec is None, 'cryptography package is not installed; signature integration not tested')
class SignedSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.f = test_offline_snapshot.FakeFrappe(); self.f.local.site='site'; self.f.session.user='account'
        core = test_offline_snapshot.load(self.f)
        spec = importlib.util.spec_from_file_location('signed_snapshot_test', PATH)
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'frappe':self.f, 'siraj_research.setup.offline_snapshot':core}):
            spec.loader.exec_module(self.module)
        self.core = self.module.core
        self.private = ec.generate_private_key(ec.SECP256R1())
        self.pem = self.private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    def test_current_session_issuer_and_browser_crypto_interoperate(self):
        self.f.rows['Person'] = [{'name':'example'}]; self.f.rows['Place'] = []; self.f.rows['Relationship'] = []
        env = self.module.issue_current_user(private_key_pem=self.pem, key_id='key', now=self.now, lifetime=timedelta(days=1))
        body = json.loads(base64.urlsafe_b64decode(env['body'] + '=' * (-len(env['body']) % 4)))
        self.assertEqual((body['site'],body['subject']),('site','account'))
        self.assertEqual(body['payload']['nodes'],[{'doctype':'Person','name':'example'}])
        numbers = self.private.public_key().public_numbers()
        encode = lambda n: base64.urlsafe_b64encode(n.to_bytes(32,'big')).decode().rstrip('=')
        trust = {'site':'site','subject':'account','key_id':'key',
                 'public_key':{'kty':'EC','crv':'P-256','x':encode(numbers.x),'y':encode(numbers.y)},
                 'revoked_snapshot_ids':[],'revoked_key_ids':[],'revocation_valid_until':'2026-01-03T00:00:00Z'}
        result = subprocess.run(['node','tests/test_signed_snapshot_crypto.js','--python-fixture'],cwd=ROOT,
                                input=json.dumps({'envelope':env,'trust':trust}),text=True,capture_output=True,check=True)
        self.assertIn('passed',result.stdout)
    def test_rejects_bad_keys_guest_and_bad_expiry_before_collecting(self):
        for key, duration in [(b'bad',timedelta(hours=1)),(self.pem,timedelta(days=8)),(self.pem,timedelta(seconds=1,microseconds=1))]:
            with self.subTest(key=key[:4],duration=duration), self.assertRaises(self.core.SnapshotError):
                self.module.issue_current_user(private_key_pem=key,key_id='key',now=self.now,lifetime=duration)
        self.f.session.user='Guest'
        with self.assertRaises(self.core.SnapshotError):
            self.module.issue_current_user(private_key_pem=self.pem,key_id='key',now=self.now,lifetime=timedelta(hours=1))
        self.assertEqual(self.f.calls, [])
    def test_doc_and_list_denials_apply_before_signing(self):
        env = self.module.issue_current_user(private_key_pem=self.pem,key_id='key',now=self.now,lifetime=timedelta(hours=1))
        raw = base64.urlsafe_b64decode(env['body'] + '=' * (-len(env['body']) % 4))
        self.assertNotIn(b'private',raw); self.assertNotIn(b'list-hidden',raw)
        self.assertNotIn('@frappe.whitelist',PATH.read_text())

if __name__ == '__main__': unittest.main()
