"""Fixture-only, read-only Event reference discovery and integrity rehearsal.

Callers supply text and synthetic snapshots
 this module never reads a site,
executes supplied code, accesses a database, or applies changes. Reports can
contain source lines and record identifiers and must be protected.
"""

import json
import re

from siraj_research.setup.event_schema_compare import compare_metadata
from siraj_research.setup.event_snapshot_projection import (
	_index,
	_same,
	inspect_projection,
	project,
	rollback_projection,
)
from siraj_research.setup.event_transition_plan import PlanError

# These are categories of evidence required, not declarations a scanner can prove.
REQUIRED_AREAS = (
	"committed_app",
	"installed_apps_hooks",
	"effective_metadata",
	"physical_schema",
	"custom_fields_property_setters",
	"direct_and_dynamic_records",
	"files_comments_children",
	"permissions_workflows_scripts",
	"reports_integrations_jobs",
	"external_consumers",
	"backup_restore",
	"concurrent_writes",
)
TOKEN = re.compile(
	r"(?i)(?<![a-z0-9])(?:siraj[ _-]+research[ _-]+event|event(?:s|_type|_participants)?)(?![a-z0-9])"
)


def _category(path):
	lower = path.lower()
	if lower.endswith("hooks.py"):
		return "hook"
	if "/report/" in lower or "/dashboard_chart/" in lower or "/number_card/" in lower:
		return "report_dashboard"
	if "integration" in lower or "webhook" in lower:
		return "integration"
	if "/doctype/" in lower and lower.endswith(".json"):
		return "doctype_metadata"
	if lower.endswith((".py", ".js", ".ts", ".sql")):
		return "application_code"
	return "other"


def discover(files):
	"""Discover review candidates in an explicitly supplied text corpus.

	Every matching line is an *unclassified candidate*, never an automatic
	rewrite. Structured metadata also reports ALL Dynamic Links, since selector
	values can name Event without that token appearing in the DocField itself.
	Input completeness, dynamic code, compiled/binary content, external systems,
	runtime values and site customizations are impossible to prove here.
	"""
	if not isinstance(files, list):
		raise PlanError("Files must be a list")
	findings, issues, paths = [], [], set()
	for entry in files:
		if not isinstance(entry, dict) or set(entry) != {"path", "text"}:
			raise PlanError("Invalid file entry")
		path, text = entry["path"], entry["text"]
		if not isinstance(path, str) or not path or not isinstance(text, str) or path in paths:
			raise PlanError("Invalid or duplicate file path")
		paths.add(path)
		category = _category(path)
		for number, line in enumerate(text.splitlines(), 1):
			if TOKEN.search(line):
				findings.append(
					{
						"path": path,
						"category": category,
						"kind": "text_candidate",
						"line": number,
						"text": line,
						"classification": "unreviewed",
					}
				)
		if category == "doctype_metadata":
			try:
				metadata = json.loads(text)
				if not isinstance(metadata, dict) or not isinstance(metadata.get("fields", []), list):
					raise ValueError()
				fields = metadata.get("fields", [])
				if any(not isinstance(f, dict) for f in fields):
					raise ValueError()
			except (ValueError, RecursionError):
				issues.append({"path": path, "kind": "invalid_metadata"})
				continue
			for field in fields:
				name, kind, options = field.get("fieldname"), field.get("fieldtype"), field.get("options")
				if not isinstance(name, str) or not name or not isinstance(kind, str):
					issues.append({"path": path, "kind": "invalid_docfield"})
					continue
				if kind == "Dynamic Link":
					findings.append(
						{
							"path": path,
							"category": category,
							"kind": "dynamic_link",
							"field": name,
							"selector": options,
							"classification": "unreviewed",
						}
					)
					if (
						not isinstance(options, str)
						or not options
						or not any(f.get("fieldname") == options for f in fields)
					):
						issues.append({"path": path, "field": name, "kind": "missing_dynamic_selector"})
				elif kind == "Link" and options == "Event":
					findings.append(
						{
							"path": path,
							"category": category,
							"kind": "direct_link",
							"field": name,
							"classification": "unreviewed",
						}
					)
				elif kind == "Select" and isinstance(options, str) and "Event" in options.splitlines():
					findings.append(
						{
							"path": path,
							"category": category,
							"kind": "event_selector",
							"field": name,
							"classification": "unreviewed",
						}
					)
	return {
		"findings": findings,
		"issues": issues,
		"files_scanned": len(paths),
		"execution_ready": False,
		"warning": "Supplied corpus only; candidates and completeness are unverified. No site, binary files or external systems were scanned.",
	}


def classify(discovery, decisions):
	"""Attach explicit per-finding human claims; never infer ownership from text.

	       Decisions use the zero-based finding index, classification and evidence. An
	       ambiguity, missing decision or invalid scanner result remains a blocker.
	       Evidence is unverified and may be sensitive
	even full classification never
	       authorizes execution. Indices apply only to this exact discovery result.
	"""
	if (
		not isinstance(discovery, dict)
		or discovery.get("execution_ready") is not False
		or not isinstance(discovery.get("findings"), list)
		or not isinstance(discovery.get("issues"), list)
		or not isinstance(decisions, list)
	):
		raise PlanError("Invalid discovery or decisions")
	reviewed = {}
	for item in decisions:
		if not isinstance(item, dict) or set(item) != {"index", "classification", "evidence"}:
			raise PlanError("Invalid classification")
		i = item["index"]
		if (
			type(i) is not int
			or i < 0
			or i >= len(discovery["findings"])
			or i in reviewed
			or item["classification"] not in ("research", "calendar", "shared", "unrelated", "ambiguous")
			or not isinstance(item["evidence"], str)
			or not item["evidence"].strip()
		):
			raise PlanError("Invalid or duplicate classification")
		reviewed[i] = item
	pending = [
		i
		for i in range(len(discovery["findings"]))
		if i not in reviewed or reviewed[i]["classification"] == "ambiguous"
	]
	return {
		"findings": discovery["findings"],
		"issues": discovery["issues"],
		"decisions": [dict(reviewed[i]) for i in sorted(reviewed)],
		"pending": pending,
		"execution_ready": False,
		"warning": "Classification is supplied, unverified and corpus-limited.",
	}


def rehearsal(
	events,
	references,
	before,
	coverage,
	discovery,
	after=None,
	rollback_rows=None,
	*,
	source_meta=None,
	target_meta=None,
):
	"""Evaluate preflight, projection and rollback guards on caller-supplied JSON.

	       Coverage claims and input rows are not independently verified. An optional
	       observed `after` tests the model postcondition
	optional `rollback_rows`
	       models intervening edits. Neither may represent a real migration. This wrapper
	       does not return or apply changed rows
	all work uses copies in memory.
	"""
	if not isinstance(coverage, dict) or set(coverage) - set(REQUIRED_AREAS):
		raise PlanError("Invalid coverage claims")
	if (
		not isinstance(discovery, dict)
		or discovery.get("execution_ready") is not False
		or not isinstance(discovery.get("findings"), list)
		or not isinstance(discovery.get("issues"), list)
	):
		raise PlanError("Invalid discovery result")
	gates = {
		"coverage": all(coverage.get(k) == "reviewed" for k in REQUIRED_AREAS),
		"discovery": not discovery["issues"]
		and not discovery.get("pending", list(range(len(discovery["findings"])))),
		"schema": False,
		"preflight": False,
		"postflight": False,
		"rollback": False,
	}
	blockers = []
	if not gates["coverage"]:
		blockers.append("coverage_incomplete_or_unverified")
	if not gates["discovery"]:
		blockers.append("discovery_findings_require_review")
	try:
		if source_meta is None or target_meta is None:
			blockers.append("schema_not_supplied")
		else:
			gates["schema"] = compare_metadata(source_meta, target_meta)["selected_attributes_match"]
			if not gates["schema"]:
				blockers.append("selected_schema_mismatch")
		projected = project(events, references, before)
		gates["preflight"] = gates["coverage"] and gates["discovery"] and gates["schema"]
		if after is None:
			blockers.append("postflight_not_supplied")
		else:
			comparison = inspect_projection(events, references, before, after)
			gates["postflight"] = comparison["model_matches"]
			if not gates["postflight"]:
				blockers.append("postflight_model_mismatch")
		restored = rollback_projection(
			projected["rows"] if rollback_rows is None else rollback_rows, projected["journal"]
		)
		a, b = _index(restored), _index(before)
		# Added unrelated rows are not overwritten, but require explicit review.
		gates["rollback"] = set(a) == set(b) and all(_same(a[k], b[k]) for k in a)
		if not gates["rollback"]:
			blockers.append("rollback_state_mismatch")
	except (PlanError, ValueError, TypeError, RecursionError) as exc:
		blockers.append("rehearsal_rejected: " + str(exc))
	return {
		"gates": gates,
		"blockers": blockers,
		"execution_ready": False,
		"warning": "Fixture model only; reviewed declarations are unverified and no database rollback or mutation is implemented.",
	}
