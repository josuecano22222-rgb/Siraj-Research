"""Experimental, non-whitelisted offline snapshot components.

No endpoint, persistence or key provisioning is registered. Collection uses the
current Frappe session and may invoke site permission hooks. Do not run on real
records before security review and separate authorization. Signatures are MACs:
anyone possessing the shared key can forge snapshots; they do not encrypt data.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json

import frappe

TYPES = ("Person", "Institution", "Place", "Source")  # Event collision is unresolved.
MAX_NODES = 2000
MAX_RELATIONSHIPS_SCANNED = 4000
MAX_TOKEN_BYTES = 2 * 1024 * 1024
PAGE_SIZE = 200
MAX_AGE = timedelta(days=7)
FIELDS = ("subject_type", "subject", "object_type", "object")


class SnapshotError(ValueError):
    pass


def _valid_id(value):
    return isinstance(value, str) and 0 < len(value) <= 256 and value == value.strip()


def _visible_rows(doctype, fields, budget):
    """Yield list-visible and document-readable rows; cap raw rows examined."""
    start = scanned = 0
    while True:
        # Ask for one beyond budget, so overflow rejects rather than truncates.
        page_length = min(PAGE_SIZE, budget - scanned + 1)
        rows = frappe.get_list(doctype, fields=["name", *fields], order_by="name asc",
                               limit_start=start, limit_page_length=page_length)
        scanned += len(rows)
        if scanned > budget:
            raise SnapshotError("Snapshot scope exceeds scan limit")
        for row in rows:
            if any(field not in row for field in ("name", *fields)):
                raise SnapshotError("Required field is not readable")
            if not _valid_id(row['name']):
                raise SnapshotError("Invalid record identifier")
            if (frappe.has_permission(doctype, "read", doc=row['name'], throw=False) and
                    frappe.has_permission(doctype, "export", doc=row['name'], throw=False)):
                yield row
        if len(rows) < page_length:
            break
        start += len(rows)


def collect_current_user():
    """Produce a minimal candidate payload using current-session permissions.

    This function is NOT an HTTP endpoint or a finished export workflow. It
    scans four non-Event types and Relationship, requiring both read and export
    for each type, plus list and per-document read/export checks. No labels, linked details,
    evidence or attachments are exported. It does not sign or persist data.
    Skipped types are explicit. Concurrent edits may make the scan inconsistent.
    """
    user = frappe.session.user
    if not _valid_id(user) or user == 'Guest':
        raise SnapshotError("An authenticated session is required")
    nodes, visible, included, omitted = [], set(), [], []
    # Bound total list-visible candidate rows across types, not just results.
    # A fixed per-type cap is used and the final aggregate is also checked.
    for doctype in TYPES:
        if not (frappe.has_permission(doctype, 'read') and frappe.has_permission(doctype, 'export')):
            omitted.append(doctype)
            continue
        included.append(doctype)
        for row in _visible_rows(doctype, (), MAX_NODES):
            node = {'doctype': doctype, 'name': row['name']}
            if (doctype, row['name']) in visible:
                raise SnapshotError("Duplicate record in scan")
            nodes.append(node); visible.add((doctype, row['name']))
            if len(nodes) > MAX_NODES:
                raise SnapshotError("Snapshot scope exceeds node limit")
    edges = []
    relationship_access = bool(frappe.has_permission('Relationship', 'read') and frappe.has_permission('Relationship', 'export'))
    if relationship_access:
        for row in _visible_rows('Relationship', FIELDS, MAX_RELATIONSHIPS_SCANNED):
            a, b = (row['subject_type'], row['subject']), (row['object_type'], row['object'])
            # Check value types before hashing, including malformed custom data.
            if all(isinstance(v, str) for v in (*a, *b)) and a in visible and b in visible:
                # Avoid linked Relationship Type or description values: their
                # independent confidentiality policy has not been reviewed.
                edges.append({'source': {'doctype': a[0], 'name': a[1]},
                              'target': {'doctype': b[0], 'name': b[1]}, 'type': ''})
    if frappe.session.user != user:
        raise SnapshotError('Session changed during scan')
    return {'scope': {'included_types': included, 'omitted_types': omitted,
                      'relationships': 'filtered' if relationship_access else 'not_authorized',
                      'excluded_types': ['Event', 'SIRAJ Research Event'],
                      'consistency': 'non_atomic'},
            'nodes': nodes, 'edges': edges}


def _canonical(value):
    try:
        raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, RecursionError):
        raise SnapshotError('Invalid snapshot data') from None
    if len(raw) > MAX_TOKEN_BYTES:
        raise SnapshotError('Snapshot too large')
    return raw


def _key(key):
    if not isinstance(key, bytes) or len(key) < 32:
        raise SnapshotError('A secret key of at least 32 bytes is required')


def _now(now):
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise SnapshotError('An explicit UTC time is required')
    return now.astimezone(timezone.utc).replace(microsecond=0)


def seal(payload, *, site, user, secret, now, lifetime):
    """MAC a candidate payload, bound to explicit issuer context and expiry.

    Caller must supply trusted site/user and a securely provisioned secret; no
    key management is provided. This proves only possession of the shared key,
    not current permissions, confidentiality or offline identity. Not connected
    to the viewer and not suitable as a production issuance workflow yet.
    """
    _key(secret); issued = _now(now)
    if not _valid_id(site) or not _valid_id(user) or user == 'Guest':
        raise SnapshotError('Invalid authorization context')
    if not isinstance(lifetime, timedelta) or not timedelta(seconds=1) <= lifetime <= MAX_AGE:
        raise SnapshotError('Invalid expiry')
    body = {'version': 2, 'site': site, 'subject': user,
            'created_at': issued.isoformat(), 'expires_at': (issued + lifetime).isoformat(), 'payload': payload}
    signature = hmac.new(secret, _canonical(body), hashlib.sha256).hexdigest()
    envelope = {'body': body, 'mac': signature}
    _canonical(envelope)
    return envelope


def verify(envelope, *, site, user, secret, now):
    """Check MAC, expected context and validity; False for malformed input.

    This does not re-evaluate Frappe permissions or authenticate the caller.
    A server must obtain site/user from its own authenticated session, never
    from untrusted snapshot fields. Revocation and key rotation are external.
    """
    try:
        _key(secret); checked = _now(now)
        if not _valid_id(site) or not _valid_id(user) or user == 'Guest':
            return False
        if not isinstance(envelope, dict) or set(envelope) != {'body', 'mac'}:
            return False
        body, mac = envelope['body'], envelope['mac']
        if not isinstance(body, dict) or set(body) != {'version', 'site', 'subject', 'created_at', 'expires_at', 'payload'}:
            return False
        if type(body['version']) is not int or body['version'] != 2 or body['site'] != site or body['subject'] != user:
            return False
        if not isinstance(mac, str) or len(mac) != 64 or not all(c in '0123456789abcdef' for c in mac):
            return False
        _canonical(envelope)
        expected = hmac.new(secret, _canonical(body), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(mac, expected):
            return False
        issued = _now(datetime.fromisoformat(body['created_at']))
        expiry = _now(datetime.fromisoformat(body['expires_at']))
        return issued <= checked < expiry and timedelta(seconds=1) <= expiry - issued <= MAX_AGE
    except (SnapshotError, TypeError, ValueError, OverflowError):
        return False


def issue_current_user(*, secret, now, lifetime):
    """Collect and MAC for the current Frappe session; not whitelisted.

    A MAC is not a substitute for trustworthy key distribution or per-device
    authorization. This is an integration seam for isolated tests, not an
    authorized production download endpoint.
    """
    site = getattr(frappe.local, 'site', None)
    user = frappe.session.user
    if not _valid_id(site) or not _valid_id(user) or user == 'Guest':
        raise SnapshotError('Invalid current session')
    _key(secret); _now(now)
    if not isinstance(lifetime, timedelta) or not timedelta(seconds=1) <= lifetime <= MAX_AGE:
        raise SnapshotError('Invalid expiry')
    payload = collect_current_user()
    if frappe.session.user != user or getattr(frappe.local, 'site', None) != site:
        raise SnapshotError('Session changed during scan')
    return seal(payload, site=site, user=user, secret=secret, now=now, lifetime=lifetime)
