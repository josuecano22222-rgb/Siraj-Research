"""Read-only Event direct/dynamic/child reference review on supplied fixtures.

No database or files. All output, including record identifiers, is sensitive.
Completeness and ownership claims must be established independently.
"""

from siraj_research.setup.event_snapshot_projection import _index
from siraj_research.setup.event_transition_plan import PlanError


def inspect(metadata, rows, events, decisions):
	"""Inventory supplied direct and polymorphic Event references.

	`metadata` is effective DocType-shaped JSON, not a site lookup. `rows` use
	the projection model's {doctype,name,values}. `events` classify all supplied
	Event targets. `decisions` explicitly classify each reference and cite
	evidence. No source values, rows or decisions are changed. Direct Links
	require a separate metadata transition, which this model never performs.
	"""
	if not isinstance(metadata, list) or not isinstance(events, list) or not isinstance(decisions, list):
		raise PlanError("Invalid inventory containers")
	indexed = _index(rows)
	metas = {}
	issues = []
	events_by_name = {}
	decisions_by_key = {}
	for meta in metadata:
		if (
			not isinstance(meta, dict)
			or not isinstance(meta.get("name"), str)
			or not meta["name"]
			or not isinstance(meta.get("fields"), list)
			or meta["name"] in metas
		):
			raise PlanError("Invalid or duplicate metadata")
		fields = {}
		for field in meta["fields"]:
			if (
				not isinstance(field, dict)
				or not isinstance(field.get("fieldname"), str)
				or not field["fieldname"]
				or field["fieldname"] in fields
			):
				raise PlanError("Invalid or duplicate metadata field")
			fields[field["fieldname"]] = field
		metas[meta["name"]] = (meta, fields)
	for event in events:
		if (
			not isinstance(event, dict)
			or set(event) != {"name", "classification"}
			or not isinstance(event["name"], str)
			or not event["name"]
			or event["name"] in events_by_name
		):
			raise PlanError("Invalid or duplicate Event identity")
		events_by_name[event["name"]] = event["classification"]
	actual_events = {name for doctype, name in indexed if doctype == "Event"}
	for name in sorted(set(events_by_name) - actual_events):
		issues.append({"kind": "classified_event_missing", "name": name})
	for name in sorted(actual_events - set(events_by_name)):
		issues.append({"kind": "event_unclassified", "name": name})
	for name, classification in events_by_name.items():
		if classification not in ("research", "calendar"):
			issues.append({"kind": "event_classification_ambiguous", "name": name})
	for item in decisions:
		if (
			not isinstance(item, dict)
			or set(item) != {"doctype", "name", "field", "classification", "evidence"}
			or any(not isinstance(item[x], str) or not item[x].strip() for x in item)
		):
			raise PlanError("Invalid reference decision")
		key = (item["doctype"], item["name"], item["field"])
		if key in decisions_by_key:
			raise PlanError("Duplicate reference decision")
		decisions_by_key[key] = item
	findings = []
	seen = set()
	descriptors_by_doctype = {}
	direct_definitions = []
	for doctype, (meta, fields) in metas.items():
		descriptors = []
		for fieldname, field in fields.items():
			kind, options = field.get("fieldtype"), field.get("options")
			if kind == "Link" and options == "Event":
				descriptors.append((fieldname, None, "direct"))
				direct_definitions.append({"doctype": doctype, "field": fieldname})
			elif kind == "Dynamic Link":
				if not isinstance(options, str) or options not in fields:
					issues.append(
						{"kind": "dynamic_selector_missing", "doctype": doctype, "field": fieldname}
					)
					continue
				descriptors.append((fieldname, options, "dynamic"))
		if meta.get("istable") in (1, True):
			descriptors.append(("parent", "parenttype", "child"))
		descriptors_by_doctype[doctype] = descriptors
	for (doctype, name), row in sorted(indexed.items()):
		if doctype not in metas:
			issues.append({"kind": "metadata_missing", "doctype": doctype, "name": name})
			continue
		descriptors = descriptors_by_doctype[doctype]
		for fieldname, selector, kind in descriptors:
			values = row["values"]
			if fieldname not in values or (selector and selector not in values):
				issues.append(
					{"kind": "reference_field_missing", "doctype": doctype, "name": name, "field": fieldname}
				)
				continue
			value = values[fieldname]
			if selector:
				selected = values[selector]
				if selected != "Event":
					if selected in (None, "") and value not in (None, ""):
						issues.append(
							{"kind": "untyped_target", "doctype": doctype, "name": name, "field": fieldname}
						)
						continue
					if selected is None or isinstance(selected, str):
						continue
					issues.append(
						{"kind": "invalid_selector", "doctype": doctype, "name": name, "field": fieldname}
					)
					continue
			if value is None or value == "":
				if selector:
					issues.append(
						{"kind": "empty_event_target", "doctype": doctype, "name": name, "field": fieldname}
					)
				continue
			if not isinstance(value, str) or not value.strip() or value != value.strip():
				issues.append(
					{"kind": "invalid_target", "doctype": doctype, "name": name, "field": fieldname}
				)
				continue
			key = (doctype, name, fieldname)
			seen.add(key)
			finding = {
				"doctype": doctype,
				"name": name,
				"field": fieldname,
				"kind": kind,
				"selector": selector,
				"target": value,
			}
			findings.append(finding)
			classification = events_by_name.get(value)
			if value not in events_by_name:
				issues.append({**finding, "reference_kind": kind, "kind": "orphan_target"})
				continue
			if classification not in ("research", "calendar"):
				issues.append({**finding, "reference_kind": kind, "kind": "ambiguous_target"})
				continue
			decision = decisions_by_key.get(key)
			if not decision:
				issues.append({**finding, "reference_kind": kind, "kind": "unreviewed_reference"})
			elif decision["classification"] != classification:
				issues.append(
					{**finding, "reference_kind": kind, "kind": "reference_classification_conflict"}
				)
	for key in sorted(set(decisions_by_key) - seen):
		issues.append(
			{"kind": "unused_reference_decision", "doctype": key[0], "name": key[1], "field": key[2]}
		)
	return {
		"execution_ready": False,
		"findings": findings,
		"direct_definitions": direct_definitions,
		"issues": issues,
		"warning": "Supplied snapshots and classifications only. Site, other code, metadata and external consumers were not inventoried.",
	}
