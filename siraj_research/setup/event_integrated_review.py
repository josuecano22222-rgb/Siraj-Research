"""Integrated Event compatibility/reference/freshness rehearsal; fixture only.

All arguments are supplied by the caller. This code reads/writes no site, never
runs hooks, and never authorizes a migration. Inputs may contain sensitive data.
"""

import copy
import hashlib
import hmac
import re

from siraj_research.setup.event_compatibility import inspect as inspect_compatibility
from siraj_research.setup.event_integrity_bundle import _bytes, prepare_bundle, verify_transition
from siraj_research.setup.event_reference_matrix import inspect as inspect_references
from siraj_research.setup.event_transition_plan import PlanError


def checksum(bundle):
	return hashlib.sha256(b"SIRAJ-EVENT-INTEGRATED-REVIEW-1\0" + _bytes(bundle)).hexdigest()


def _reference_gap(matrix, references, events):
	"""Require each discovered polymorphic pair in the projection, exactly once."""
	if not isinstance(references, list):
		raise PlanError("Invalid reference list")
	if matrix["direct_definitions"]:
		return "direct_link_transition_unsupported"
	classes = {item["name"]: item["classification"] for item in events}
	expected = {
		(f["doctype"], f["name"], f["selector"], f["field"], f["target"], classes.get(f["target"]))
		for f in matrix["findings"]
	}
	try:
		planned = {
			(r["doctype"], r["name"], r["type_field"], r["name_field"], r["target"], r["classification"])
			for r in references
		}
	except (TypeError, KeyError):
		raise PlanError("Invalid reference list") from None
	if len(expected) != len(matrix["findings"]) or len(planned) != len(references) or expected != planned:
		return "reference_projection_mismatch"
	return None


def review(
	*,
	files,
	code_decisions,
	events,
	references,
	rows,
	coverage,
	source_meta,
	target_meta,
	core_reference_meta,
	reference_metadata,
	reference_decisions,
	physical_schema,
	hook_inventory,
):
	"""Return blockers and a guarded fixture bundle only if supplied checks pass.

	       `core_reference_meta` is a supplied framework reference, not necessarily the
	       currently effective site metadata. Physical schema and hook inventories are
	       JSON-shaped claims
	this function cannot prove their completeness or truth.
	"""
	if (
		not isinstance(physical_schema, dict)
		or not physical_schema
		or not isinstance(hook_inventory, dict)
		or not hook_inventory
	):
		raise PlanError("Physical schema and hook inventory must be supplied")
	compatibility = inspect_compatibility(core_reference_meta, target_meta)
	matrix = inspect_references(reference_metadata, rows, events, reference_decisions)
	blockers = []
	if compatibility["issues"]:
		blockers.append("selected_compatibility_contract_failed")
	if matrix["issues"]:
		blockers.append("reference_review_incomplete")
	event_meta = [m for m in reference_metadata if m.get("name") == "Event"]
	if len(event_meta) != 1 or _bytes(event_meta[0]) != _bytes(source_meta):
		blockers.append("source_reference_metadata_mismatch")
	gap = _reference_gap(matrix, references, events)
	if gap:
		blockers.append(gap)
	try:
		projected = prepare_bundle(
			files, code_decisions, events, references, rows, coverage, source_meta, target_meta
		)
		if projected["status"] != "fixture_ready":
			blockers.append("projection_preflight_failed")
	except PlanError:
		projected = None
		blockers.append("projection_rejected")
	report = {
		"execution_ready": False,
		"status": "blocked" if blockers else "fixture_ready",
		"blockers": blockers,
		"compatibility": compatibility,
		"references": matrix,
		"projection_gates": projected["gates"] if projected else None,
		"bundle": None,
		"checksum": None,
		"warning": "Fixture-only: unverified claims and checksum cannot establish real-site completeness or authorization.",
	}
	if blockers:
		return report
	bundle = {
		"version": 1,
		"inner_bundle": projected["bundle"],
		"inner_checksum": projected["fingerprint"],
		"core_reference_meta": copy.deepcopy(core_reference_meta),
		"reference_metadata": copy.deepcopy(reference_metadata),
		"reference_decisions": copy.deepcopy(reference_decisions),
		"physical_schema": copy.deepcopy(physical_schema),
		"hook_inventory": copy.deepcopy(hook_inventory),
	}
	report["bundle"] = bundle
	report["checksum"] = checksum(bundle)
	return report


def transition(
	bundle,
	expected_checksum,
	*,
	files,
	events,
	references,
	rows,
	source_meta,
	target_meta,
	core_reference_meta,
	reference_metadata,
	physical_schema,
	hook_inventory,
	reverse=False,
):
	"""Re-check a separately protected checksum and fresh inputs before modeling.

	On either direction, any changed metadata, schema, hooks, reference list,
	code or snapshot is a conflict. The trusted checksum is not a signature.
	"""
	if (
		not isinstance(bundle, dict)
		or set(bundle)
		!= {
			"version",
			"inner_bundle",
			"inner_checksum",
			"core_reference_meta",
			"reference_metadata",
			"reference_decisions",
			"physical_schema",
			"hook_inventory",
		}
		or type(bundle["version"]) is not int
		or bundle["version"] != 1
	):
		raise PlanError("Invalid integrated review bundle")
	if (
		not isinstance(expected_checksum, str)
		or not re.fullmatch("[0-9a-f]{64}", expected_checksum)
		or not hmac.compare_digest(checksum(bundle), expected_checksum)
	):
		raise PlanError("Integrated review checksum mismatch")
	for name, current in (
		("core_reference_meta", core_reference_meta),
		("reference_metadata", reference_metadata),
		("physical_schema", physical_schema),
		("hook_inventory", hook_inventory),
	):
		if not hmac.compare_digest(_bytes(bundle[name]), _bytes(current)):
			raise PlanError("Stale physical schema, hooks or reference metadata")
	inner = bundle["inner_bundle"]
	journal = inner.get("journal", {}) if isinstance(inner, dict) else {}
	# Recompute reference findings against the protected pre-state. The inner
	# transition separately checks the current full pre/post rows and references.
	matrix = inspect_references(
		reference_metadata, journal.get("before"), events, bundle["reference_decisions"]
	)
	event_meta = [m for m in reference_metadata if m.get("name") == "Event"]
	if len(event_meta) != 1 or _bytes(event_meta[0]) != _bytes(source_meta):
		raise PlanError("Source reference metadata mismatch")
	if (
		matrix["issues"]
		or _reference_gap(matrix, references, events)
		or inspect_compatibility(core_reference_meta, target_meta)["issues"]
	):
		raise PlanError("Compatibility or reference review no longer passes")
	result = verify_transition(
		inner,
		bundle["inner_checksum"],
		files=files,
		events=events,
		references=references,
		source_meta=source_meta,
		target_meta=target_meta,
		rows=rows,
		reverse=reverse,
	)
	return {
		"execution_ready": False,
		"state": result["state"],
		"rows": result["rows"],
		"warning": "In-memory fixture model only; no database operation or actual rollback performed.",
	}
