"""Pure WGS84 coordinate transition model; no Frappe, database or file access.

Records, decisions and journals can contain sensitive values and identifiers.
This is a rehearsal, not a migration executor or proof of physical rollback.
"""

from __future__ import annotations

import copy
import json
from collections import Counter

from siraj_research.utils.coordinates import parse_coordinate

TYPES = ("Person", "Institution", "Place", "Siraj Event", "Military Unit", "Operational Deployment")
MAX_LENGTH = 140


class PlanError(ValueError):
	"""An incomplete, ambiguous or conflicting candidate must not be planned."""


def _validate_value(value):
	if value is None or isinstance(value, str | bool | int):
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


def _parse(value):
	return parse_coordinate(value, max_length=MAX_LENGTH)


def _canonical(n):
	text = format(n, "f")
	if "." in text:
		text = text.rstrip("0").rstrip(".")
	if n == 0:
		return "0"
	return text


def audit(rows, decisions):
	"""Inspect caller-supplied snapshot; never fetch or modify actual records.

	       Decisions are a list of {doctype,name,orientation,zero}
	orientation is
	       explicitly 'lat_lon' or 'swap'. zero is 'preserve' or 'not_zero'. There is
	       no guessing, implicit null conversion or automatic swap. Both blank pairs
	       are retained as-is. A partial, malformed, excessive, or out-of-range pair
	       blocks projection. A zero pair needs explicit preserve. WGS84 is an assumed
	       CRS requiring source evidence, not inferred from numbers.
	"""
	index = _index(rows)
	if not isinstance(decisions, list):
		raise PlanError("Invalid decisions")
	selected = {}
	for d in decisions:
		if (
			not isinstance(d, dict)
			or set(d) != {"doctype", "name", "orientation", "zero"}
			or d["orientation"] not in ("lat_lon", "swap")
			or d["zero"] not in ("preserve", "not_zero")
		):
			raise PlanError("Invalid coordinate decision")
		key = (d["doctype"], d["name"])
		if (
			not all(isinstance(x, str) and x for x in key)
			or key in selected
			or key not in index
			or key[0] not in TYPES
		):
			raise PlanError("Duplicate or unknown coordinate decision")
		selected[key] = d
	issues = []
	proposals = []
	counts = Counter()
	for (dt, name), row in sorted(index.items()):
		if dt not in TYPES:
			continue
		values = row["values"]
		if "latitude" not in values or "longitude" not in values:
			issues.append({"doctype": dt, "name": name, "kind": "missing_coordinate_field"})
			continue
		la, lv = _parse(values["latitude"])
		lo, ov = _parse(values["longitude"])
		if la == lo == "blank":
			counts["both_blank"] += 1
			if (dt, name) in selected:
				issues.append({"doctype": dt, "name": name, "kind": "unexpected_decision_for_blank"})
			continue
		if "invalid" in (la, lo):
			issues.append({"doctype": dt, "name": name, "kind": "invalid_coordinate"})
			continue
		if "blank" in (la, lo):
			issues.append({"doctype": dt, "name": name, "kind": "partial_pair"})
			continue
		direct = lv.copy_abs() <= 90 and ov.copy_abs() <= 180
		swapped = ov.copy_abs() <= 90 and lv.copy_abs() <= 180
		if not direct and not swapped:
			issues.append({"doctype": dt, "name": name, "kind": "out_of_range"})
			continue
		decision = selected.get((dt, name))
		if not decision:
			issues.append(
				{
					"doctype": dt,
					"name": name,
					"kind": "orientation_unreviewed",
					"possible_swap": bool(swapped),
					"direct_valid": bool(direct),
					"zero_pair": lv == 0 and ov == 0,
				}
			)
			continue
		if decision["orientation"] == "swap":
			lv, ov = ov, lv
		if lv.copy_abs() > 90 or ov.copy_abs() > 180:
			issues.append({"doctype": dt, "name": name, "kind": "orientation_out_of_range"})
			continue
		zero = lv == 0 and ov == 0
		if (zero and decision["zero"] != "preserve") or (not zero and decision["zero"] != "not_zero"):
			issues.append({"doctype": dt, "name": name, "kind": "zero_decision_conflict"})
			continue
		lat, lon = _canonical(lv), _canonical(ov)
		if len(lat) > MAX_LENGTH or len(lon) > MAX_LENGTH:
			issues.append({"doctype": dt, "name": name, "kind": "canonical_value_too_long"})
			continue
		proposals.append({"doctype": dt, "name": name, "latitude": lat, "longitude": lon})
		counts["reviewed_pairs"] += 1
	return {
		"execution_ready": False,
		"counts": dict(counts),
		"issues": issues,
		"proposals": proposals,
		"warning": "Fixture-only; original values and CRS provenance need independent verification. No database or schema changes.",
	}


def prepare(rows, decisions):
	"""Create guarded in-memory before/after snapshots; stop on any issue."""
	report = audit(rows, decisions)
	if report["issues"]:
		raise PlanError("Coordinate review has unresolved issues")
	after = copy.deepcopy(rows)
	indexed = {(r["doctype"], r["name"]): r for r in after}
	for item in report["proposals"]:
		values = indexed[(item["doctype"], item["name"])]["values"]
		values["latitude"], values["longitude"] = item["latitude"], item["longitude"]
	return {
		"execution_ready": False,
		"report": report,
		"manifest": {
			"version": 1,
			"before": copy.deepcopy(rows),
			"decisions": copy.deepcopy(decisions),
			"after": after,
		},
	}


def _same_rows(a, b):
	a, b = _index(a), _index(b)
	return set(a) == set(b) and all(_same(a[key], b[key]) for key in a)


def transition(rows, manifest, *, reverse=False):
	"""Rehearse idempotent guarded conversion/reversal of supplied snapshots."""
	if (
		type(reverse) is not bool
		or not isinstance(manifest, dict)
		or set(manifest) != {"version", "before", "decisions", "after"}
		or type(manifest["version"]) is not int
		or manifest["version"] != 1
	):
		raise PlanError("Invalid coordinate journal")
	expected = prepare(manifest["before"], manifest["decisions"])["manifest"]["after"]
	if not _same_rows(expected, manifest["after"]):
		raise PlanError("Coordinate journal mismatch")
	start, end = (
		(manifest["after"], manifest["before"]) if reverse else (manifest["before"], manifest["after"])
	)
	if _same_rows(rows, end):
		state = "already_reversed" if reverse else "already_projected"
	elif _same_rows(rows, start):
		state = "reversed" if reverse else "projected"
	else:
		raise PlanError("Coordinate snapshot conflict")
	return {
		"execution_ready": False,
		"state": state,
		"rows": copy.deepcopy(end),
		"warning": "In-memory only; not a database migration or rollback.",
	}
