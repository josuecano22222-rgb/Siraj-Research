"""Canonical form layout for SIRAJ location fields.

The coordinate, map and administrative-hierarchy fields must be edited as one
unit.  This module is deliberately pure (no Frappe imports) so the same rules
can be used by repository tooling, migrations and tests.

The shipped DocType JSON files are normalised in the repository, but keeping
the rules here makes the layout reproducible: a new DocType only has to expose
the fieldnames and ``normalize()`` produces the same section everywhere.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

LOCATION_SECTION_LABEL = "Location"

# Canonical order. ``location`` is the legacy alias used by Operational
# Deployment and Training Exercise for locality/place name.
FIELD_ORDER: tuple[str, ...] = (
	"latitude",
	"longitude",
	"geo_point",
	"country",
	"governorate",
	"district",
	"municipality",
	"village",
	"community",
	"place_name",
	"location",
)

CANONICAL_LABELS: dict[str, str] = {
	"latitude": "Latitude",
	"longitude": "Longitude",
	"geo_point": "Geolocation",
	"country": "Country",
	"governorate": "Governorate",
	"district": "District",
	"municipality": "Municipality",
	"village": "Village / locality",
	"community": "Community / cluster",
	"place_name": "Locality / place name",
}

LAYOUT_TYPES = {"Section Break", "Column Break", "Tab Break"}


def _is_layout(field: dict[str, Any]) -> bool:
	return field.get("fieldtype") in LAYOUT_TYPES


def _unique_fieldname(fields: Iterable[dict[str, Any]], base: str) -> str:
	used = {field.get("fieldname") for field in fields}
	if base not in used:
		return base
	index = 2
	while f"{base}_{index}" in used:
		index += 1
	return f"{base}_{index}"


def _prune_empty_sections(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
	"""Remove Section Breaks that no longer contain any editable field."""
	kept: list[dict[str, Any]] = []
	group: list[dict[str, Any]] = []

	def flush() -> None:
		if not group:
			return
		section = group[0]
		if section.get("fieldtype") == "Section Break" and not any(
			not _is_layout(field) for field in group[1:]
		):
			return
		kept.extend(group)
		group.clear()

	for field in fields:
		if field.get("fieldtype") in {"Section Break", "Tab Break"}:
			flush()
		group.append(field)
	flush()
	return kept


def normalize(meta: dict[str, Any]) -> dict[str, Any]:
	"""Return ``meta`` with every location field in one Location section.

	The function is idempotent. Fields that do not exist on a DocType are
	simply skipped; an empty ``Location`` section is never created.
	"""
	result = deepcopy(meta)
	fields = list(result.get("fields") or [])
	by_name = {field.get("fieldname"): field for field in fields}
	present = [name for name in FIELD_ORDER if name in by_name]
	if not present:
		return result

	# Anchor on the coordinate/map block when available. Otherwise use the
	# first hierarchy field present, so a country-only DocType still gets its
	# field grouped in place.
	anchor_name = next((name for name in ("latitude", "geo_point", "longitude") if name in present), present[0])
	anchor_index = next(i for i, field in enumerate(fields) if field.get("fieldname") == anchor_name)

	# Reuse an existing Location section instead of stacking a second one on
	# top of it (Gazetteer Place already shipped with `sb_loc`).
	existing_sections = [
		i
		for i, field in enumerate(fields)
		if field.get("fieldtype") == "Section Break"
		and field.get("label") == LOCATION_SECTION_LABEL
	]
	existing_section_names: set[str] = set()
	if existing_sections:
		anchor_index = existing_sections[0]
		existing_section_names = {fields[i]["fieldname"] for i in existing_sections}

	location_fields = [
		field
		for field in fields
		if field.get("fieldname") in present or field.get("fieldname") in existing_section_names
	]
	remaining = [
		field
		for field in fields
		if field.get("fieldname") not in present
		and field.get("fieldname") not in existing_section_names
	]

	# Find the last field before the anchor that survives the move, then
	# insert the new section immediately after it.
	removed_names = {field.get("fieldname") for field in location_fields}
	preceding_name = None
	for field in reversed(fields[:anchor_index]):
		name = field.get("fieldname")
		if name not in removed_names:
			preceding_name = name
			break

	remaining = _prune_empty_sections(remaining)
	insert_at = 0
	if preceding_name is not None:
		for index, field in enumerate(remaining):
			if field.get("fieldname") == preceding_name:
				insert_at = index + 1
				break

	section = {
		"fieldname": _unique_fieldname(remaining, "sb_location"),
		"label": LOCATION_SECTION_LABEL,
		"fieldtype": "Section Break",
	}
	block: list[dict[str, Any]] = [section]
	for name in FIELD_ORDER:
		field = by_name.get(name)
		if not field:
			continue
		field = deepcopy(field)
		if name in CANONICAL_LABELS:
			field["label"] = CANONICAL_LABELS[name]
		field["insert_after"] = block[-1]["fieldname"]
		block.append(field)

	remaining[insert_at:insert_at] = block
	result["fields"] = remaining
	if "field_order" in result:
		result["field_order"] = [field["fieldname"] for field in remaining]
	return result


def is_normalized(meta: dict[str, Any]) -> bool:
	"""True when every location field sits in exactly one Location section."""
	fields = meta.get("fields") or []
	present = [field for field in fields if field.get("fieldname") in FIELD_ORDER]
	if not present:
		return True
	section_indexes = [
		index
		for index, field in enumerate(fields)
		if field.get("fieldtype") == "Section Break" and field.get("label") == LOCATION_SECTION_LABEL
	]
	if len(section_indexes) != 1:
		return False
	start = section_indexes[0]
	end = next(
		(
			index
			for index in range(start + 1, len(fields))
			if fields[index].get("fieldtype") in {"Section Break", "Tab Break"}
		),
		len(fields),
	)
	section_names = {field.get("fieldname") for field in fields[start + 1 : end]}
	return all(field.get("fieldname") in section_names for field in present)
