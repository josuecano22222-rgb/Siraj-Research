"""Whole-snapshot Event transition journal: pure fixture model, never site I/O.

Not an executor. The caller must protect manifests and must not use them to
modify a site. Completeness and physical database rollback remain unverified.
"""

import copy

from siraj_research.setup.event_snapshot_projection import _index, _same, project
from siraj_research.setup.event_transition_plan import PlanError


def _equal_rows(left, right):
	a, b = _index(left), _index(right)
	return set(a) == set(b) and all(_same(a[key], b[key]) for key in a)


def prepare(events, references, rows):
	"""Build reproducible before/after and a complete guarded fixture journal."""
	projected = project(events, references, rows)
	manifest = {
		"version": 1,
		"events": copy.deepcopy(events),
		"references": copy.deepcopy(references),
		"before": copy.deepcopy(rows),
		"after": copy.deepcopy(projected["rows"]),
	}
	return {
		"execution_ready": False,
		"manifest": manifest,
		"counts": projected["counts"],
		"warning": "Fixture model only; source Event rows remain. Not a database migration or approval.",
	}


def _checked(manifest):
	if (
		not isinstance(manifest, dict)
		or set(manifest) != {"version", "events", "references", "before", "after"}
		or type(manifest["version"]) is not int
		or manifest["version"] != 1
	):
		raise PlanError("Invalid rehearsal manifest")
	expected = project(manifest["events"], manifest["references"], manifest["before"])
	if not _equal_rows(expected["rows"], manifest["after"]):
		raise PlanError("Manifest post-state does not match recomputed model")
	return manifest["before"], manifest["after"]


def transition(rows, manifest, *, reverse=False):
	"""Idempotently project or reverse a complete JSON snapshot, with no writes.

	Reject changed, missing or additional rows, partial operations, malformed
	journals and mismatched post-state. Caller-provided manifest is not signed;
	authorization, independent inventory and real DB transactions are absent.
	"""
	if type(reverse) is not bool:
		raise PlanError("Invalid direction")
	before, after = _checked(manifest)
	start, end = (after, before) if reverse else (before, after)
	if _equal_rows(rows, end):
		state = "already_reversed" if reverse else "already_projected"
	elif _equal_rows(rows, start):
		state = "reversed" if reverse else "projected"
	else:
		raise PlanError("Snapshot conflict: modified, missing, added or partially transitioned row")
	return {
		"execution_ready": False,
		"state": state,
		"rows": copy.deepcopy(end),
		"warning": "In-memory model only; no actual records, schema, external effects or site were changed.",
	}
