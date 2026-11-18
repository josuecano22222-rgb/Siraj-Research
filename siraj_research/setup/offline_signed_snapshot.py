"""Experimental asymmetric snapshot issuer; not a web endpoint.

Uses current-session permissions through offline_snapshot. No key provisioning,
site configuration, file storage, encryption or real-record export is enabled.
Private key material is accepted only from trusted in-process caller
 never put
it in bench arguments, logs, code, site exports, or client packages.
"""

import base64
import json
import secrets
from datetime import timedelta, timezone

import frappe

from siraj_research.setup import offline_snapshot as core

DOMAIN = b"SIRAJ-OFFLINE-SNAPSHOT-V3\x00"
MAX_SIZE = 2 * 1024 * 1024


def _b64(value):
	return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def issue_current_user(*, private_key_pem, key_id, now, lifetime):
	"""Produce a signed v3 envelope for the current session, without writing it.

	       Experimental, non-whitelisted, not a production export. Issuer and trust
	       provisioning must be independently reviewed
	no online revocation or
	       encryption is supplied. Signature doesn't prove the collector is correct.
	"""
	issued = core._now(now)
	if (
		not isinstance(lifetime, timedelta)
		or not timedelta(seconds=1) <= lifetime <= core.MAX_AGE
		or lifetime.microseconds
	):
		raise core.SnapshotError("Invalid expiry")
	if not core._valid_id(key_id) or not isinstance(private_key_pem, bytes):
		raise core.SnapshotError("Invalid signing key")
	try:
		from cryptography.hazmat.primitives import hashes, serialization
		from cryptography.hazmat.primitives.asymmetric import ec, utils

		key = serialization.load_pem_private_key(private_key_pem, password=None)
		if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
			raise ValueError("Expected P-256 key")
	except (ImportError, ValueError, TypeError):
		raise core.SnapshotError("Invalid or unavailable P-256 signing key") from None
	site = getattr(frappe.local, "site", None)
	subject = frappe.session.user
	if not core._valid_id(site) or not core._valid_id(subject) or subject == "Guest":
		raise core.SnapshotError("Invalid current session")
	payload = core.collect_current_user()
	if frappe.session.user != subject or getattr(frappe.local, "site", None) != site:
		raise core.SnapshotError("Session changed during scan")
	body = {
		"version": 3,
		"site": site,
		"subject": subject,
		"key_id": key_id,
		"snapshot_id": secrets.token_hex(16),
		"created_at": issued.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
		"expires_at": (issued + lifetime).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
		"payload": payload,
	}
	data = core._canonical(body)
	der = key.sign(DOMAIN + data, ec.ECDSA(hashes.SHA256()))
	r, s = utils.decode_dss_signature(der)
	envelope = {
		"version": 3,
		"body": _b64(data),
		"signature": _b64(r.to_bytes(32, "big") + s.to_bytes(32, "big")),
	}
	if len(json.dumps(envelope, separators=(",", ":")).encode("utf-8")) > MAX_SIZE:
		raise core.SnapshotError("Signed snapshot too large")
	return envelope
