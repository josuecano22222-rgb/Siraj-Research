"""Pure tests for the canonical Location section layout."""

from __future__ import annotations

import json
from pathlib import Path

from siraj_research.location_layout import (
	CANONICAL_LABELS,
	FIELD_ORDER,
	LOCATION_SECTION_LABEL,
	is_normalized,
	normalize,
)

ROOT = Path(__file__).resolve().parents[1]
DOCTYPE_DIR = ROOT / "siraj_research/siraj_research/doctype"


def _meta(*names):
	return {
		"name": "Synthetic",
		"field_order": list(names),
		"fields": [
			{"fieldname": "sb_identity", "fieldtype": "Section Break", "label": "Identity"},
			*[
				{"fieldname": name, "fieldtype": "Data", "label": name.title()}
				for name in names
			],
			{"fieldname": "sb_notes", "fieldtype": "Section Break", "label": "Notes"},
			{"fieldname": "notes", "fieldtype": "Text", "label": "Notes"},
		],
	}


def test_normalize_groups_fields_in_one_location_section():
	meta = _meta("latitude", "country", "geo_point")
	result = normalize(meta)
	assert is_normalized(result)

	fields = result["fields"]
	start = next(
		i for i, field in enumerate(fields)
		if field["fieldtype"] == "Section Break" and field["label"] == LOCATION_SECTION_LABEL
	)
	end = next(
		i for i in range(start + 1, len(fields))
		if fields[i]["fieldtype"] == "Section Break"
	)
	section_names = [field["fieldname"] for field in fields[start + 1 : end]]
	assert section_names == ["latitude", "geo_point", "country"]
	assert {field["label"] for field in fields[start + 1 : end]} == {
		CANONICAL_LABELS["latitude"], CANONICAL_LABELS["geo_point"], CANONICAL_LABELS["country"]
	}
	assert result["field_order"] == [field["fieldname"] for field in fields]


def test_normalize_is_idempotent_and_does_not_remove_other_fields():
	meta = _meta("latitude", "country", "geo_point")
	once = normalize(meta)
	twice = normalize(once)
	assert once == twice
	assert any(field.get("fieldname") == "notes" for field in twice["fields"])


def test_all_shipped_doctypes_with_location_fields_are_normalized():
	checked = 0
	for path in sorted(DOCTYPE_DIR.glob("*/*.json")):
		meta = json.loads(path.read_text())
		names = {field.get("fieldname") for field in meta.get("fields", [])}
		if not names.intersection(FIELD_ORDER):
			continue
		checked += 1
		assert is_normalized(meta), meta["name"]
		assert meta.get("field_order") == [field["fieldname"] for field in meta["fields"]], meta["name"]
		labels = {field["label"] for field in meta["fields"] if field.get("fieldname") == "geo_point"}
		assert labels in ({CANONICAL_LABELS["geo_point"]}, set()), meta["name"]
	assert checked >= 17


def test_bundle_loads_location_guard_before_map_modules():
	bundle = (ROOT / "siraj_research/public/js/siraj.bundle.js").read_text()
	guard = bundle.index("import './siraj-location-layout.js';")
	map_module = bundle.index("import './coordinate_map.js';")
	assert guard < map_module
