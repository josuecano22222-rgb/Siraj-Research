"""In-memory preservation and rollback prototype. Never connects to Frappe.

This models proposed copies and polymorphic reference changes on caller-supplied
JSON-shaped snapshots
 it is NOT an executable database migration. Snapshots
and journals contain sensitive data and require protected storage if retained.
"""

import copy
import json

from siraj_research.setup.event_transition_plan import OLD_TYPE, PlanError, prepare_transition


def _validate_value(value):
	if value is None or isinstance(value, (str, bool, int)):
		return
	if isinstance(value, float):
		json.dumps(value, allow_nan=False)
		return
	if isinstance(value, list):
		for item in value:
			_validate_value(item)
		return
	if isinstance(value, dict) and all(isinstance(key, str) for key in value):
		for item in value.values():
			_validate_value(item)
		return
	raise ValueError("Snapshot contains a non-JSON value")


def _same(a, b):
	return json.dumps(
		a, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":")
	) == json.dumps(b, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":"))


def _index(rows):
	if not isinstance(rows, list):
		raise PlanError("Snapshot must be a list")
	result = {}
	for row in rows:
		if not isinstance(row, dict) or set(row) != {"doctype", "name", "values"}:
			raise PlanError("Invalid snapshot row")
		if not all(
			isinstance(row[k], str) and row[k] and row[k] == row[k].strip() for k in ("doctype", "name")
		) or not isinstance(row["values"], dict):
			raise PlanError("Invalid snapshot identity or values")
		try:
			_validate_value(row["values"])
		except (ValueError, RecursionError):
			raise PlanError("Unsupported snapshot value") from None
		key = (row["doctype"], row["name"])
		if key in result:
			raise PlanError("Duplicate snapshot identity")
		result[key] = copy.deepcopy(row)
	return result


def project(events, references, rows):
	"""Copy research rows and project supplied type-field changes in memory.

	       Every supplied Event row must be classified. Referencing rows must be present
	       and match both expected type and target. Event-owned reference fields are
	       unsupported: copying/rewriting them requires additional schema policy. The
	       original Event rows are deliberately retained. Returns a projected snapshot
	       and private undo journal
	neither proves real-site completeness or safety.
	"""
	original = _index(rows)
	target_names = [name for doctype, name in original if doctype == "Research Event"]
	plan = prepare_transition(events, references, target_names)
	event_names = {name for doctype, name in original if doctype == OLD_TYPE}
	if event_names != {event["name"] for event in events}:
		raise PlanError("Event snapshot and classifications differ")
	projected = copy.deepcopy(original)
	before = {}
	created = []
	for item in plan["candidate_copies"]:
		source = (item["source_type"], item["source_name"])
		target = (item["target_type"], item["target_name"])
		row = copy.deepcopy(projected[source])
		row["doctype"], row["name"] = target
		projected[target] = row
		created.append(target)
	# Verify *all* references, including calendar references, before projection.
	for ref in references:
		key = (ref["doctype"], ref["name"])
		if ref["doctype"] in (OLD_TYPE, "Research Event"):
			raise PlanError("Event-owned references require separate review")
		if key not in projected:
			raise PlanError("Referenced snapshot row missing")
		values = projected[key]["values"]
		if values.get(ref["type_field"]) != OLD_TYPE or values.get(ref["name_field"]) != ref["target"]:
			raise PlanError("Reference snapshot does not match inventory")
	for change in plan["candidate_reference_changes"]:
		key = (change["doctype"], change["name"])
		before.setdefault(key, copy.deepcopy(original[key]))
		projected[key]["values"][change["type_field"]] = change["new_type"]
	journal = {
		"created": [copy.deepcopy(projected[key]) for key in created],
		"changed": [
			{"before": before[key], "after": copy.deepcopy(projected[key])} for key in sorted(before)
		],
	}
	return {
		"execution_ready": False,
		"rows": [projected[key] for key in sorted(projected)],
		"journal": journal,
		"counts": plan["counts"],
		"warning": "In-memory projection only; original Event rows remain and no site, schema, permissions or hooks were changed.",
	}


def rollback_projection(rows, journal):
	"""Reverse the in-memory projection only if affected rows still match.

	       This is not a database rollback. Rejects edits to a projected row rather
	       than overwriting them
	preserves unrelated rows. Journal must be trusted.
	"""
	current = _index(rows)
	if (
		not isinstance(journal, dict)
		or set(journal) != {"created", "changed"}
		or not all(isinstance(journal[k], list) for k in journal)
	):
		raise PlanError("Invalid journal")
	touched = set()
	for row in journal["created"]:
		checked = _index([row])
		key = next(iter(checked))
		if key in touched or key not in current or not _same(current[key], row):
			raise PlanError("Created row changed or missing")
		touched.add(key)
	for pair in journal["changed"]:
		if not isinstance(pair, dict) or set(pair) != {"before", "after"}:
			raise PlanError("Invalid journal change")
		old, new = _index([pair["before"]]), _index([pair["after"]])
		key = next(iter(old))
		if (
			set(old) != set(new)
			or key in touched
			or key not in current
			or not _same(current[key], pair["after"])
		):
			raise PlanError("Changed row no longer matches")
		touched.add(key)
	for row in journal["created"]:
		del current[(row["doctype"], row["name"])]
	for pair in journal["changed"]:
		row = copy.deepcopy(pair["before"])
		current[(row["doctype"], row["name"])] = row
	return [current[key] for key in sorted(current)]


def inspect_projection(events, references, before, after):
	"""Compare supplied projected JSON rows with an independently recomputed plan.

	This is not a site inventory or database integrity audit. The expected state
	intentionally retains legacy Event rows. Output contains row identifiers and
	must be treated as sensitive. A matching result proves only that supplied
	snapshots match the prototype's narrow model, not that a migration is safe.
	"""
	result = project(events, references, before)
	expected = _index(result["rows"])
	observed = _index(after)
	expected_keys, observed_keys = set(expected), set(observed)
	missing = sorted(expected_keys - observed_keys)
	unexpected = sorted(observed_keys - expected_keys)
	changed = sorted(key for key in expected_keys & observed_keys if not _same(expected[key], observed[key]))

	def identities(keys):
		return [{"doctype": dt, "name": name} for dt, name in keys]

	return {
		"execution_ready": False,
		"pre": result["counts"],
		"post": {
			"expected_rows": len(expected),
			"observed_rows": len(observed),
			"missing": identities(missing),
			"unexpected": identities(unexpected),
			"changed": identities(changed),
		},
		"model_matches": not (missing or unexpected or changed),
		"warning": "Only the supplied JSON snapshots were compared; this is not a real-site integrity report or migration approval.",
	}
