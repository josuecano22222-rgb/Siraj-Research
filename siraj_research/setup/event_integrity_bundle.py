"""Integrated, stale-state-aware Event fixture rehearsal. Never connects to a site.

All supplied evidence and outputs may be sensitive. Fingerprints detect changes
only if stored independently in a trusted location
 they are not signatures.
No operation in this module executes or authorizes a database migration.
"""

import copy
import hashlib
import hmac
import json
import re

from siraj_research.setup.event_reference_review import classify, discover, rehearsal
from siraj_research.setup.event_rehearsal_journal import prepare, transition
from siraj_research.setup.event_transition_plan import PlanError


def _bytes(value):
	try:
		return json.dumps(
			value, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":")
		).encode("utf-8")
	except (TypeError, ValueError, RecursionError):
		raise PlanError("Evidence is not valid JSON") from None


def fingerprint(bundle):
	"""Return a reproducible checksum of supplied data, not authentication."""
	return hashlib.sha256(b"SIRAJ-EVENT-FIXTURE-BUNDLE-1\0" + _bytes(bundle)).hexdigest()


def prepare_bundle(files, decisions, events, references, rows, coverage, source_meta, target_meta):
	"""Combine source candidate discovery, schema, projection and model gates.

	This operates exclusively on supplied values. Review and coverage claims
	are unverified, and no set of inputs can make execution_ready true.
	"""
	if not isinstance(files, list) or not files:
		raise PlanError("At least one supplied source file required")
	discovery = classify(discover(files), decisions)
	prepared = prepare(events, references, rows)
	report = rehearsal(
		events,
		references,
		rows,
		coverage,
		discovery,
		after=prepared["manifest"]["after"],
		source_meta=source_meta,
		target_meta=target_meta,
	)
	if not all(report["gates"].values()) or report["blockers"]:
		return {
			"execution_ready": False,
			"status": "blocked",
			"gates": report["gates"],
			"blockers": report["blockers"],
			"bundle": None,
			"fingerprint": None,
		}
	bundle = {
		"version": 1,
		"files": copy.deepcopy(files),
		"decisions": copy.deepcopy(decisions),
		"coverage": copy.deepcopy(coverage),
		"source_meta": copy.deepcopy(source_meta),
		"target_meta": copy.deepcopy(target_meta),
		"journal": prepared["manifest"],
	}
	return {
		"execution_ready": False,
		"status": "fixture_ready",
		"gates": report["gates"],
		"blockers": [],
		"bundle": bundle,
		"fingerprint": fingerprint(bundle),
		"warning": "Review assertions are unverified; this checksum is not authentication or migration approval.",
	}


def verify_transition(
	bundle, expected_fingerprint, *, files, events, references, source_meta, target_meta, rows, reverse=False
):
	"""Verify separately retained checksum and fresh inputs before model transition.

	       All supplied metadata, source texts, classifications/references and the
	       complete row state must match. Reordering a list counts as a change. The
	       checksum must be protected independently
	an attacker able to replace both
	       it and the bundle can forge this check. No schema or database is changed.
	"""
	if (
		not isinstance(bundle, dict)
		or set(bundle)
		!= {"version", "files", "decisions", "coverage", "source_meta", "target_meta", "journal"}
		or type(bundle["version"]) is not int
		or bundle["version"] != 1
	):
		raise PlanError("Invalid evidence bundle")
	if (
		not isinstance(expected_fingerprint, str)
		or not re.fullmatch("[0-9a-f]{64}", expected_fingerprint)
		or not hmac.compare_digest(fingerprint(bundle), expected_fingerprint)
	):
		raise PlanError("Bundle fingerprint mismatch")
	journal = bundle["journal"]
	if not isinstance(journal, dict):
		raise PlanError("Invalid rehearsal journal")
	for old, fresh in (
		(bundle["files"], files),
		(bundle["source_meta"], source_meta),
		(bundle["target_meta"], target_meta),
		(journal.get("events"), events),
		(journal.get("references"), references),
	):
		if not hmac.compare_digest(_bytes(old), _bytes(fresh)):
			raise PlanError("Stale evidence or classifications")
	# Recompute all gates from the protected bundle, not a stored Boolean.
	verified = prepare_bundle(
		bundle["files"],
		bundle["decisions"],
		journal["events"],
		journal["references"],
		journal["before"],
		bundle["coverage"],
		bundle["source_meta"],
		bundle["target_meta"],
	)
	if verified["status"] != "fixture_ready" or not hmac.compare_digest(
		_bytes(verified["bundle"]), _bytes(bundle)
	):
		raise PlanError("Bundle no longer passes fixture preflight")
	result = transition(rows, journal, reverse=reverse)
	return {
		"execution_ready": False,
		"state": result["state"],
		"rows": result["rows"],
		"warning": "Fixture-only; source completeness and the independently supplied checksum are not authenticated.",
	}
