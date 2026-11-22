"""Presentation layer shared by the Explorer's read-only profile endpoints.

The Explorer used to render whatever order the DocType happened to store, with
raw DocField labels and raw values. That produced three recurring problems:

* a Tab Break was skipped but did not start a new group, so trailing fields
  leaked into the preceding section (``Completeness (%)`` appeared under
  ``External identifiers``);
* Table fields were formatted as values, so child tables rendered as the
  literal ``[object Object]``;
* labels were English while enum values had already been translated by the
  server, so one panel was effectively bilingual by accident.

This module is deliberately *pure Python* — no Frappe import at module import
time — so the ordering, typing and i18n metadata can be unit-tested without a
bench. Both :func:`siraj_research.api.entity_profile.get_entity_profile` and
:func:`siraj_research.api.relationship_profile.get_relationship_profile` pass
their raw payload through :func:`organise_profile` before returning it.

Strings emitted here are *source* strings (usually English). The client is the
single place that translates them with ``__()``; every source value is kept
alongside its display value so the panel can switch between the translated
text and the text actually recorded in the archive.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from siraj_research.setup.demo_content import CONFIDENCE_CODES

#: Bump when the shape of a profile payload changes incompatibly.
PRESENTATION_VERSION = 2

#: Deterministic quality-score weights (stable presentation contract).
QUALITY_WEIGHTS: dict[str, float] = {
    "completeness": 0.6,
    "evidence": 0.25,
    "source": 0.15,
}

#: Evidence rows required for the evidence component to saturate.
EVIDENCE_SATURATION_ROWS = 5

#: UI help text for the Quality section — documents the scoring weights and
#: the derived-vs-recorded confidence rule. Kept as one source string; the
#: renderer translates it client-side like every other label (ar.csv row).
QUALITY_HELP = (
	"Quality score = 60% completeness + 25% evidence rows (saturates at 5) "
	"+ 15% primary source, rounded and clamped to 0-100; the quality fields "
	"themselves are excluded from completeness. Confidence is marked "
	"(derived) when the record stores no authentication level — it is then "
	"computed from evidence rows (2+ → corroborated, 1 → single source, "
	"0 → unverified); otherwise it is the recorded value."
)

# The semantic order of the Fields tab. ``fields`` and ``headings`` are exact
# matches; ``keywords`` is a last-resort match on fieldnames/labels. Keeping
# the blueprint here (instead of in the DOM) means the same order is used by
# every surface that consumes a profile, including exports and future viewers.
SECTION_BLUEPRINTS: tuple[dict[str, Any], ...] = (
	{
		"id": "identity",
		"heading": "Identity",
		"order": 10,
		"headings": ("Identity", "sb_identity", "tab_identity"),
		"fields": (
			"naming_series",
			"display_name",
			"name_ar",
			"name_en",
			"name_original",
			"name_original_lang",
			"name_transliteration",
			"name_variants",
			"image",
			"image_url",
			"image_alt",
			"abbreviation",
			"title",
			"acronym",
		),
		"keywords": ("name", "series", "transliter", "alias", "portrait"),
	},
	{
		"id": "life",
		"heading": "Life & dates",
		"order": 20,
		"headings": ("Life & dates", "Birth", "Death"),
		"fields": (
			"birth_date_as_stated",
			"birth_date",
			"birth_date_precision",
			"death_date_as_stated",
			"death_date",
			"death_date_precision",
			"date_of_birth",
			"date_of_death",
			"birth_year",
			"death_year",
		),
		"keywords": ("birth", "death", "born", "died"),
	},
	{
		"id": "origin",
		"heading": "Origin",
		"order": 30,
		"headings": ("Origin",),
		"fields": (
			"nationality",
			"birthplace",
			"birthplace_as_stated",
			"country",
			"governorate",
			"district",
			"municipality",
			"village",
			"community",
			"place_name",
			"ethnicity",
			"religion",
			"language",
		),
		"keywords": ("national", "birthplace", "origin"),
	},
	{
		"id": "classification",
		"heading": "Classification",
		"order": 40,
		"headings": ("Classification",),
		"fields": (
			"person_category",
			"person_status",
			"category",
			"classification",
			"current_position_as_stated",
			"declared_affiliation",
			"specializations",
		),
		"keywords": ("classification", "category", "status", "position", "affiliation"),
	},
	{
		"id": "family",
		"heading": "Family",
		"order": 45,
		"headings": (
			"Family",
			"tab_family",
			"Marital status",
			"sb_marital",
			"Spouse",
			"sb_spouse",
			"Children",
			"sb_children",
			"Grandchildren",
			"sb_grandchildren",
			"Siblings",
			"sb_siblings",
			"Family of origin & next of kin",
			"sb_family_origin",
		),
		"fields": (
			"marital_status",
			"family_summary",
			"spouse_name",
			"spouse_birth_date",
			"spouse_nationality",
			"spouse_occupation",
			"marriage_date",
			"marriage_date_as_stated",
			"marriage_place",
			"spouse_notes",
			"children",
			"grandchildren",
			"siblings",
			"father_name",
			"father_person",
			"mother_name",
			"family_name",
			"next_of_kin",
			"family_notes",
		),
		"keywords": ("family", "spouse", "married", "children", "kin", "sibling"),
	},
	{
		"id": "service",
		"heading": "Military service",
		"order": 50,
		"headings": ("Military service", "Service", "Command"),
		"fields": (
			"rank_title",
			"rank",
			"branch",
			"commission_date",
			"service_status",
			"military_biography",
			"leadership_assessments",
			"unit_armament_holding",
			"retirement_date",
			"command_role",
		),
		"keywords": ("rank", "branch", "service", "commission", "military", "unit"),
	},
	{
		"id": "public",
		"heading": "Public activity",
		"order": 70,
		"headings": ("Public activity", "Public", "Media"),
		"fields": (
			"public_activity",
			"website",
			"image_url",
			"social_accounts",
			"email",
			"phone",
		),
		"keywords": ("website", "social", "public", "account"),
	},
	{
		"id": "relationship",
		"heading": "Relationship details",
		"order": 75,
		"headings": ("Relationship", "Relationship details", "The link"),
		"fields": (
			"relationship_type",
			"direction",
			"is_current",
			"role_as_stated",
			"relationship_description",
			"subject_type",
			"object_type",
		),
		"keywords": ("relationship", "direction", "ongoing"),
	},
	{
		"id": "endpoints",
		"heading": "Endpoints",
		"order": 78,
		"headings": ("Endpoints", "From (subject)", "To (object)"),
		"fields": ("subject", "object"),
		"keywords": ("subject", "object"),
	},
	{
		"id": "location",
		"heading": "Location",
		"order": 80,
		"headings": ("Location", "Position (this record's own)", "Coordinates"),
		"fields": (
			"latitude",
			"longitude",
			"geo_precision",
			"geocoding_method",
			"geo_uncertainty_m",
			"geometry_source",
			"location_source",
			"admin_boundary_geom",
		),
		"keywords": ("latitude", "longitude", "coordinate", "geo", "location"),
	},
	{
		"id": "timing",
		"heading": "Timing",
		"order": 85,
		"headings": ("Timing", "Validity", "Dates"),
		"fields": (
			"start_date_as_stated",
			"start_date",
			"start_date_precision",
			"end_date_as_stated",
			"end_date",
			"end_date_precision",
			"last_review_date",
			"access_date",
			"event_date",
		),
		"keywords": ("start", "end", "validity", "date"),
	},
	{
		"id": "provenance",
		"heading": "Provenance & state",
		"order": 90,
		"headings": ("Source & verification", "Provenance & State", "Provenance"),
		"fields": (
			"primary_source",
			"documentation_level",
			"authentication_level",
			"workflow_state",
			"researcher_notes",
			"record_status",
			"status",
		),
		"keywords": ("source", "documentation", "authentication", "workflow", "notes"),
	},
	{
		"id": "evidence",
		"heading": "Evidence",
		"order": 100,
		"headings": ("Evidence", "Evidence (claims this record makes)"),
		"fields": ("evidence", "evidence_count"),
		"keywords": ("evidence", "claim"),
	},
	{
		"id": "identifiers",
		"heading": "External identifiers",
		"order": 110,
		"headings": ("External identifiers", "Identifiers"),
		"fields": ("external_identifiers", "external_id", "wikidata_id"),
		"keywords": ("identifier", "external"),
	},
	{
		"id": "quality",
		"heading": "Quality",
		"order": 130,
		"headings": ("Quality",),
		"fields": ("completeness_score", "quality_score", "confidence"),
		"keywords": ("completeness", "quality", "confidence"),
		"help": QUALITY_HELP,
	},
)

OTHER_GROUP = {
	"id": "other",
	"heading": "Other fields",
	"order": 900,
	"headings": (),
	"fields": (),
	"keywords": (),
}

#: Fieldnames that differ by parent DocType. ``Relationship.display_name`` is
#: the label of the edge, not the identity of a biographical subject.
DOCTYPE_FIELD_OVERRIDES: dict[str, dict[str, str]] = {
	"Relationship": {
		"display_name": "relationship",
		"naming_series": "relationship",
		"description": "relationship",
	},
}

#: Where a child table belongs. Child tables are rendered *between* field
#: groups instead of being dumped at the end of the tab.
CHILD_SECTION: dict[str, str] = {
	"social_accounts": "public",
	"leadership_assessments": "service",
	"specializations": "classification",
	"admin_boundary_geom": "location",
	"evidence": "evidence",
	"external_identifiers": "identifiers",
	"unit_armament_holding": "service",
}

NON_VALUE_FIELDTYPES = {
	"Section Break",
	"Column Break",
	"Tab Break",
	"HTML",
	"Button",
	"Table",
	"Table MultiSelect",
}

BOOLEAN_FIELDTYPES = {"Check"}
DATE_FIELDTYPES = {"Date", "Datetime", "Time"}
NUMBER_FIELDTYPES = {"Int", "Float", "Currency", "Percent", "Rating", "Duration"}

ARABIC_SCRIPT = re.compile(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff]")
URL_RE = re.compile(r"^(https?://|mailto:|tel:)", re.IGNORECASE)
DEMO_TAG_RE = re.compile(r"\s*\\?\[DEMO\\?\]", re.IGNORECASE)


def _normalised(text: Any) -> str:
	return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())


def _blueprints_by_field() -> dict[str, str]:
	out: dict[str, str] = {}
	for spec in SECTION_BLUEPRINTS:
		for fieldname in spec["fields"]:
			out.setdefault(fieldname, spec["id"])
	return out


FIELD_SECTION = _blueprints_by_field()


def humanize(fieldname: str) -> str:
	"""Turn ``field_key`` into a readable fallback label without losing data."""
	return str(fieldname or "").replace("_", " ").strip().capitalize()


def section_spec(group_id: str) -> dict[str, Any]:
	for spec in (*SECTION_BLUEPRINTS, OTHER_GROUP):
		if spec["id"] == group_id:
			return spec
	return OTHER_GROUP


def group_for_section(heading: Any, fieldnames: Any = ()) -> str:
	"""Resolve the semantic group for a source section heading + its fields."""
	label = _normalised(heading)
	for spec in SECTION_BLUEPRINTS:
		if label and any(_normalised(alias) == label for alias in spec["headings"]):
			return spec["id"]
	votes: dict[str, int] = {}
	for fieldname in fieldnames:
		group = FIELD_SECTION.get(fieldname)
		if group:
			votes[group] = votes.get(group, 0) + 2
		low = _normalised(fieldname)
		if low:
			for spec in SECTION_BLUEPRINTS:
				if any(word in low for word in map(_normalised, spec["keywords"])):
					votes[spec["id"]] = votes.get(spec["id"], 0) + 1
	if votes:
		return max(sorted(votes), key=lambda key: votes[key])
	return OTHER_GROUP["id"]


def group_for_field(fieldname: str, doctype: str | None = None) -> str:
	overrides = DOCTYPE_FIELD_OVERRIDES.get(doctype or "", {})
	if fieldname in overrides:
		return overrides[fieldname]
	return FIELD_SECTION.get(fieldname, OTHER_GROUP["id"])


def strip_demo_tag(value: Any) -> tuple[str, bool]:
	"""Separate a trailing ``[DEMO]`` marker from the underlying value.

	Demo records carry the marker in their data on purpose. Keeping it as a
	bilingual badge (instead of baking it into every label) makes the panel
	readable while preserving the marker in ``title``/source mode.
	"""
	text = "" if value is None else str(value)
	cleaned = DEMO_TAG_RE.sub("", text).strip()
	return cleaned, cleaned != text


def value_kind(field: dict[str, Any]) -> str:
	fieldtype = str(field.get("fieldtype") or "")
	value = field.get("value")
	options = str(field.get("options") or "")
	if isinstance(value, dict) and value.get("type") in ("link", "attach"):
		return str(value["type"])
	if fieldtype == "Link" or fieldtype == "Dynamic Link":
		return "link"
	if fieldtype in ("Attach", "Attach Image", "Image"):
		return "attach"
	if fieldtype in BOOLEAN_FIELDTYPES:
		return "boolean"
	if fieldtype in DATE_FIELDTYPES:
		return "date"
	if fieldtype in NUMBER_FIELDTYPES:
		return "number"
	if options == "URL" or (isinstance(value, str) and URL_RE.match(value.strip())):
		return "url"
	if fieldtype in ("Select",):
		return "enum"
	if fieldtype in ("Email",):
		return "email"
	if fieldtype in ("Phone",):
		return "phone"
	if isinstance(value, dict | list):
		return "json"
	return "text"


def display_value(value: Any) -> str:
	"""A never-``[object Object]`` textual representation of a raw value."""
	if value is None:
		return ""
	if isinstance(value, bool):
		return "Yes" if value else "No"
	if isinstance(value, str):
		return value
	if isinstance(value, dict | list):
		return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(", ", ": "))
	return str(value)


def normalise_field(field: dict[str, Any], doctype: str | None = None) -> dict[str, Any]:
	"""Add stable ids, source strings and a value type to a profile field."""
	out = dict(field)
	raw = out.get("value")
	label_source = str(out.get("label") or humanize(out.get("fieldname", "")))
	out["label"] = label_source
	out["label_source"] = label_source
	out["i18n_key"] = label_source
	out["source_heading"] = out.get("source_heading") or ""
	kind = value_kind(out)
	out["value_kind"] = kind

	if isinstance(raw, dict) and raw.get("type") == "link":
		out["value"] = {
			"type": "link",
			"doctype": raw.get("doctype", ""),
			"name": raw.get("name", ""),
			"title": raw.get("title", raw.get("name", "")),
		}
		out["value_source"] = str(raw.get("title") or raw.get("name") or "")
		out["translatable_value"] = False
	elif isinstance(raw, dict) and raw.get("type") == "attach":
		out["value"] = {"type": "attach", "url": raw.get("url", "")}
		out["value_source"] = str(raw.get("url") or "")
		out["translatable_value"] = False
	else:
		out["value"] = raw
		out["value_source"] = display_value(raw)
		# Only controlled vocabulary is safe to feed through __(); names, notes
		# and URLs are archive data and must never be autocorrected by i18n.
		out["translatable_value"] = kind == "enum" and bool(raw)

	clean_label, label_is_demo = strip_demo_tag(label_source)
	out["label_demo"] = label_is_demo
	clean_value, value_is_demo = strip_demo_tag(out["value_source"])
	out["value_demo"] = value_is_demo
	if label_is_demo:
		out["label"] = clean_label
	out["group"] = group_for_field(str(out.get("fieldname") or ""), doctype)
	if ARABIC_SCRIPT.search(out["value_source"]):
		out["value_rtl"] = True
	return out


def normalise_sections(
	sections: Any,
	doctype: str | None = None,
	translate: Callable[[str], str] | None = None,
) -> list[dict[str, Any]]:
	"""Flatten, re-group and deterministically order the scalar field sections."""
	buckets: dict[str, list[dict[str, Any]]] = {}
	seen_headings: dict[str, list[str]] = {}
	for source in sections or []:
		if not isinstance(source, dict):
			continue
		heading = str(source.get("heading") or source.get("label") or "")
		fields = source.get("fields") or []
		fieldnames = [str(f.get("fieldname") or "") for f in fields if isinstance(f, dict)]
		group = group_for_section(heading, fieldnames)
		seen_headings.setdefault(group, [])
		if heading and heading not in seen_headings[group]:
			seen_headings[group].append(heading)
		for field in fields:
			if not isinstance(field, dict):
				continue
			fieldtype = str(field.get("fieldtype") or "")
			if fieldtype in NON_VALUE_FIELDTYPES:
				continue
			item = dict(field)
			item["source_heading"] = heading
			normalised = normalise_field(item, doctype)
			target = normalised["group"]
			if target not in buckets:
				buckets[target] = []
			if not any(
				existing.get("fieldname") == normalised.get("fieldname") for existing in buckets[target]
			):
				buckets[target].append(normalised)
			if target != group and heading and heading not in seen_headings.setdefault(target, []):
				seen_headings[target].append(heading)

	specs = sorted(
		(*SECTION_BLUEPRINTS, OTHER_GROUP),
		key=lambda spec: (spec["order"], spec["heading"]),
	)
	out = []
	for spec in specs:
		fields = buckets.get(spec["id"]) or []
		if not fields:
			continue
		heading = spec["heading"]
		section_out: dict[str, Any] = {
			"id": spec["id"],
			"heading": translate(heading) if translate else heading,
			"heading_source": heading,
			"i18n_key": heading,
			"order": spec["order"],
			"source_headings": seen_headings.get(spec["id"], []),
			"fields": fields,
		}
		if spec.get("help"):
			# Source text only — the client translates it (labelNode pattern).
			section_out["help"] = spec["help"]
		out.append(section_out)
	return out


def _column_order(table: dict[str, Any], rows: list[dict[str, Any]]) -> list[str]:
	preferred = [str(key) for key in table.get("column_order") or []]
	seen: set[str] = set()
	ordered: list[str] = []
	excluded = {"name", "idx", "parent", "parenttype", "parentfield"}

	def add(key: str) -> None:
		if key not in seen and key not in excluded:
			seen.add(key)
			ordered.append(key)

	for key in preferred:
		add(key)
	for row in rows:
		for key in row:
			add(key)
	return ordered


def normalise_children(
	children: Any,
	translate: Callable[[str], str] | None = None,
) -> dict[str, dict[str, Any]]:
	"""Turn child-table payloads into stable, typed, column-ordered tables."""
	out: dict[str, dict[str, Any]] = {}
	for fieldname, table in (children or {}).items():
		if not isinstance(table, dict):
			continue
		rows = [row for row in (table.get("rows") or []) if isinstance(row, dict)]
		columns: list[dict[str, Any]] = []
		for key in _column_order(table, rows):
			first = next((row[key] for row in rows if key in row), None)
			label = (
				str((first or {}).get("label") or humanize(key)) if isinstance(first, dict) else humanize(key)
			)
			columns.append(
				{
					"fieldname": key,
					"label": translate(label) if translate else label,
					"label_source": label,
					"i18n_key": label,
					"value_kind": (first or {}).get("value_kind", "text")
					if isinstance(first, dict)
					else "text",
				}
			)
		normalised_rows = []
		for row in rows:
			cells = {}
			for key, cell in row.items():
				if not isinstance(cell, dict):
					cell = {"label": humanize(key), "value": cell}
				cells[key] = normalise_field(
					{
						"fieldname": key,
						"label": cell.get("label") or humanize(key),
						"fieldtype": cell.get("fieldtype") or "Data",
						"options": cell.get("options") or "",
						"value": cell.get("value"),
					}
				)
			normalised_rows.append(cells)
		label_source = str(table.get("label") or humanize(str(fieldname)))
		out[str(fieldname)] = {
			"id": str(fieldname),
			"fieldname": str(fieldname),
			"label": translate(label_source) if translate else label_source,
			"label_source": label_source,
			"i18n_key": label_source,
			"options": table.get("options") or "",
			"section": CHILD_SECTION.get(str(fieldname), group_for_section(label_source)),
			"total": table.get("total", len(normalised_rows)),
			"truncated": bool(table.get("truncated")),
			"columns": columns,
			"rows": normalised_rows,
		}
	return out


def collect_strings(profile: dict[str, Any]) -> list[str]:
	"""Collect every source string a translation catalogue must contain."""
	found: set[str] = set()
	for section in profile.get("sections") or []:
		for key in ("heading", "heading_source", "i18n_key"):
			if section.get(key):
				found.add(str(section[key]))
		for heading in section.get("source_headings") or []:
			found.add(str(heading))
		for field in section.get("fields") or []:
			for key in ("label", "label_source", "i18n_key", "value_source"):
				if field.get(key) and (key != "value_source" or field.get("translatable_value")):
					found.add(str(field[key]))
	for table in (profile.get("children") or {}).values():
		for key in ("label", "label_source", "i18n_key"):
			if table.get(key):
				found.add(str(table[key]))
		for column in table.get("columns") or []:
			if column.get("label_source"):
				found.add(str(column["label_source"]))
		for row in table.get("rows") or []:
			for cell in row.values():
				if isinstance(cell, dict) and cell.get("translatable_value") and cell.get("value_source"):
					found.add(str(cell["value_source"]))
	return sorted(found)


def _entry_present(value: Any) -> bool:
	"""True when a field value counts as filled (0 and False are filled)."""
	if value is None:
		return False
	if isinstance(value, str):
		return value.strip() != ""
	if isinstance(value, list | tuple | dict):
		return len(value) > 0
	return True


def compute_quality_scores(profile: dict[str, Any]) -> dict[str, Any]:
	"""Deterministic quality scoring for a SIRAJ profile payload.

	Extends the existing ``completeness_score`` / ``quality_score`` /
	``confidence`` presentation contract — no parallel system:

	* ``completeness_score`` (0-100): share of non-empty data fields. The
	  three quality fields themselves are excluded from the denominator so
	  the scores never grade each other.
	* ``quality_score`` (0-100): ``60% completeness + 25% evidence`` (rows
	  saturating at :data:`EVIDENCE_SATURATION_ROWS`) ``+ 15% primary
	  source presence`` — weights in :data:`QUALITY_WEIGHTS`.
	* ``confidence``: the record's ``authentication_level`` when it is one
	  of the six ordered :data:`CONFIDENCE_CODES` (low → high), otherwise
	  derived from evidence rows (≥2 → ``corroborated``, 1 →
	  ``single_source``, 0 → ``unverified``).

	Pure and deterministic: identical input yields identical output.
	Accepts both the raw entity-profile payload and an already-normalised
	one (sections of field entries + children with ``rows``/``total``).
	"""
	sections = profile.get("sections") or []
	entries = [
		field
		for section in sections
		if isinstance(section, dict)
		for field in (section.get("fields") or [])
		if isinstance(field, dict)
	]
	quality_names = {"completeness_score", "quality_score", "confidence"}
	scored = [f for f in entries if f.get("fieldname") not in quality_names]
	present = sum(1 for f in scored if _entry_present(f.get("value")))
	completeness = int(present * 100 / len(scored) + 0.5) if scored else 0

	children = profile.get("children") or {}
	evidence = children.get("evidence") or {}
	if not isinstance(evidence, dict):
		evidence = {}
	evidence_rows = int(
		evidence.get("total") or len(evidence.get("rows") or []) or 0
	)

	source_value = next(
		(
			f.get("value")
			for f in entries
			if f.get("fieldname") == "primary_source"
		),
		None,
	)
	source_present = _entry_present(source_value)

	evidence_points = (
		100.0 * min(evidence_rows, EVIDENCE_SATURATION_ROWS)
		/ EVIDENCE_SATURATION_ROWS
	)
	quality = int(
		QUALITY_WEIGHTS["completeness"] * completeness
		+ QUALITY_WEIGHTS["evidence"] * evidence_points
		+ QUALITY_WEIGHTS["source"] * (100.0 if source_present else 0.0)
		+ 0.5
	)

	auth = next(
		(
			f.get("value")
			for f in entries
			if f.get("fieldname") == "authentication_level"
		),
		None,
	)
	if isinstance(auth, str) and auth in CONFIDENCE_CODES:
		confidence = auth
		confidence_derived = False
	elif evidence_rows >= 2:
		confidence = "corroborated"
		confidence_derived = True
	elif evidence_rows == 1:
		confidence = "single_source"
		confidence_derived = True
	else:
		confidence = "unverified"
		confidence_derived = True

	return {
		"completeness_score": max(0, min(100, completeness)),
		"quality_score": max(0, min(100, quality)),
		"confidence": confidence,
		# True when confidence came from evidence rows instead of the
		# record's recorded authentication_level — the UI marks those
		# values "(derived)" so recorded and derived are distinguishable.
		"confidence_derived": confidence_derived,
		"evidence_rows": evidence_rows,
		"confidence_scale": list(CONFIDENCE_CODES),
	}


def organise_profile(
	profile: dict[str, Any],
	*,
	doctype: str | None = None,
	lang: str | None = None,
	translate: Callable[[str], str] | None = None,
) -> dict[str, Any]:
	"""Return a copy of ``profile`` with presentation/i18n metadata attached.

	Existing keys are kept so older clients continue to work; new clients read
	``sections``, ``children`` and ``presentation`` from the same payload.
	"""
	out = dict(profile or {})
	sections = normalise_sections(out.get("sections"), doctype, translate)
	children = normalise_children(out.get("children"), translate)
	# A table can be the only content of a semantic group (e.g. a record whose
	# only provenance content is its Evidence table). Give it a section so the
	# client can interleave it at the right place instead of appending it last.
	present = {section["id"] for section in sections}
	for table in children.values():
		group_id = table["section"]
		if group_id in present:
			continue
		spec = section_spec(group_id)
		sections.append(
			{
				"id": spec["id"],
				"heading": translate(spec["heading"]) if translate else spec["heading"],
				"heading_source": spec["heading"],
				"i18n_key": spec["heading"],
				"order": spec["order"],
				"source_headings": [],
				"fields": [],
			}
		)
		present.add(group_id)
	sections.sort(key=lambda section: (section["order"], section["heading"]))
	out["sections"] = sections
	out["children"] = children
	language = lang or "en"
	out["presentation"] = {
		"version": PRESENTATION_VERSION,
		"language": language,
		"rtl": str(language).split("-")[0].lower() in {"ar", "fa", "he", "ur"},
		"group_order": [spec["id"] for spec in SECTION_BLUEPRINTS] + [OTHER_GROUP["id"]],
		"strings": collect_strings(out),
	}
	return out
