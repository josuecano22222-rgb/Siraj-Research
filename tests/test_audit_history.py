"""Pure contracts for the audit history formatter (Phase 4)."""
import json

from siraj_research.utils.audit_history import (
	NOISE_FIELDS,
	build_entries,
	filter_visible,
)


def _row(name, data, creation="2026-11-18 10:00:00", owner="Researcher"):
	if not isinstance(data, str):
		data = json.dumps(data)
	return {"name": name, "creation": creation, "owner": owner, "data": data}


def test_insert_marker_becomes_created_entry():
	entries = build_entries([_row("v1", {"creation": "2026-11-18 09:00:00", "created_by": "Admin"})])
	assert len(entries) == 1
	assert entries[0]["action"] == "created"
	assert entries[0]["by"] == "Admin"
	assert entries[0]["changes"] == []


def test_changed_fields_split_with_labels_by_caller():
	entries = build_entries(
		[_row("v2", {"changed": [["description", "old text", "new text"], ["country", "IQ", "PS"]]})]
	)
	assert entries[0]["action"] == "updated"
	assert entries[0]["changes"] == [
		{"field": "description", "old": "old text", "new": "new text"},
		{"field": "country", "old": "IQ", "new": "PS"},
	]


def test_framework_noise_is_always_dropped():
	noise = sorted(NOISE_FIELDS)
	entries = build_entries(
		[_row("v3", {"changed": [[f, "a", "b"] for f in noise] + [["title", "x", "y"]]})]
	)
	assert [c["field"] for c in entries[0]["changes"]] == ["title"]
	# A payload with ONLY noise changes disappears entirely.
	assert build_entries([_row("v4", {"changed": [[f, "a", "b"] for f in noise]})]) == []


def test_noop_changes_are_dropped():
	entries = build_entries([_row("v5", {"changed": [["title", "same", "same"]]})])
	assert entries == []


def test_child_table_counts_and_row_flattening():
	entries = build_entries(
		[
			_row(
				"v6",
				{
					"added": [["evidence", [{"name": "E1"}, {"name": "E2"}]]],
					"removed": [["social_accounts", [{"name": "S1"}]]],
					"row_changed": [
						["evidence", "E1", 0, [["source", "SRC-1", "SRC-2"]]]
					],
				},
			)
		]
	)
	fields = [(c["field"], c["old"], c["new"]) for c in entries[0]["changes"]]
	assert ("evidence", "", "2 rows") in fields
	assert ("social_accounts", "1 rows", "") in fields
	assert ("evidence[1].source", "SRC-1", "SRC-2") in fields


def test_malformed_payload_is_ignored():
	assert build_entries([_row("v7", "{not json")]) == []
	assert build_entries([{"name": "v8", "creation": "x", "owner": "y", "data": None}]) == []


def test_filter_visible_drops_fields_and_orphans_entries():
	entries = build_entries(
		[_row("v9", {"changed": [["researcher_notes", "a", "b"], ["title", "x", "y"]]})]
	)
	# Field-level gate removes the L1 notes but keeps the entry (title left).
	visible = filter_visible(entries, lambda field: field != "researcher_notes")
	assert [c["field"] for c in visible[0]["changes"]] == ["title"]
	# Gate that hides everything removes the whole entry.
	assert filter_visible(entries, lambda field: False) == []
	# Created entries carry no field data and survive the field gate.
	created = build_entries([_row("v10", {"creation": "t", "created_by": "A"})])
	assert len(filter_visible(created, lambda field: False)) == 1


def test_filter_visible_does_not_mutate_input():
	entries = build_entries([_row("v11", {"changed": [["title", "x", "y"]]})])
	filter_visible(entries, lambda field: True)
	assert entries[0]["changes"] == [{"field": "title", "old": "x", "new": "y"}]
