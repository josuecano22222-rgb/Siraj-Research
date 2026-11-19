"""Global administrative hierarchy: resolution, linking and safe upserts.

This module is the bridge between the spatial resolver
(:mod:`siraj_research.api.geo_resolve`) and the six searchable DocTypes that
make up SIRAJ's administrative backbone:

    Country → Governorate → District → Municipality → Village → Community

The resolver knows about *polygons* (``Admin Boundary``) and *gazetteer
points*; this module knows about the *records* shown in forms and lists. It
turns a resolved chain into real Frappe documents, creating only what is
missing and never overwriting values a researcher has edited by hand.

Design constraints
------------------

* Importable without Frappe so code generation / chain normalisation can be
  unit-tested in a plain Python process.
* Every level is optional. Countries without an administrative level simply
  leave a gap; we never invent a placeholder just to make a chain look deep.
* Codes are deterministic. Re-resolving the same coordinate must find the
  same row instead of creating duplicates.
* All writes go through the Frappe document API (no raw SQL).

See ``docs/global-admin-hierarchy.md`` for the architecture and seeding plan.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable
from typing import Any

try:  # pragma: no cover - exercised inside a bench
    import frappe
except Exception:  # pragma: no cover - pure-Python tests
    frappe = None  # type: ignore[assignment]


# Stable level contract. ``field`` is the Link field on the *next* level's
# DocType as well as the key used in resolver payloads.
LEVELS: tuple[dict[str, Any], ...] = (
	{"level": 0, "field": "country", "doctype": "Country", "parent": None, "prefix": "C"},
	{"level": 1, "field": "governorate", "doctype": "Governorate", "parent": "country", "prefix": "G"},
	{"level": 2, "field": "district", "doctype": "District", "parent": "governorate", "prefix": "D"},
	{"level": 3, "field": "municipality", "doctype": "Municipality", "parent": "district", "prefix": "M"},
	{"level": 4, "field": "village", "doctype": "Village", "parent": "municipality", "prefix": "V"},
	{"level": 5, "field": "community", "doctype": "Community", "parent": "village", "prefix": "Q"},
)

HIERARCHY_DOCTYPES = tuple(spec["doctype"] for spec in LEVELS[1:])
MAX_CODE_LENGTH = 120  # Frappe Data default is 140; leave room for suffixes.

_SLUG_RE = re.compile(r"[^A-Z0-9]+")
_CODE_ALLOWED_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,139}$")


def level_spec(level: int | str) -> dict[str, Any]:
	try:
		index = int(level)
	except (TypeError, ValueError):
		return LEVELS[-1]
	if 0 <= index < len(LEVELS):
		return LEVELS[index]
	return LEVELS[-1]


def field_to_level(fieldname: str) -> int:
	for spec in LEVELS:
		if spec["field"] == fieldname:
			return int(spec["level"])
	return -1


def slug(value: Any, fallback: str = "X") -> str:
	"""ASCII, upper-case slug suitable for a deterministic code fragment."""
	text = unicodedata.normalize("NFKD", "" if value is None else str(value))
	text = text.encode("ascii", "ignore").decode("ascii").upper()
	slug_text = _SLUG_RE.sub("-", text).strip("-")
	if slug_text:
		return slug_text
	digest = hashlib.sha1(str(value or fallback).encode("utf-8")).hexdigest()[:8].upper()
	return digest


def normalize_code(pcode: Any) -> str:
	"""Canonicalise source codes so ``IQ.BG`` and ``IQ-BG`` map to one row."""
	return re.sub(r"[.\s]+", "-", str(pcode or "").strip().upper()).strip("-")


def make_code(pcode: Any, name: Any, parent_code: str | None, level: int | str) -> str:
	"""Return a stable, Frappe-safe document name for an administrative row.

	Source P-Codes are preferred because different levels often share the same
	local name. When no P-Code exists we derive one from the parent code and
	the label; the hash keeps Arabic-only names deterministic and non-empty.
	"""
	spec = level_spec(level)
	candidate = normalize_code(pcode).replace(" ", "_")
	if candidate and _CODE_ALLOWED_RE.match(candidate):
		return candidate[:MAX_CODE_LENGTH]
	fragment = slug(name, fallback=spec["prefix"])
	parent = str(parent_code or "").strip().upper()
	base = "-".join(part for part in (spec["prefix"], parent, fragment) if part)
	base = re.sub(r"[^A-Z0-9._:-]", "-", base).strip("-") or spec["prefix"] + "-" + fragment
	if len(base) <= MAX_CODE_LENGTH:
		return base
	digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:10]
	return base[: MAX_CODE_LENGTH - 11] + "-" + digest


def _entry_value(entry: Any) -> tuple[str, str | None, str | None, str | None]:
	"""Normalise one resolver chain entry to (label, pcode, name_ar, source)."""
	if isinstance(entry, str):
		return entry, None, None, None
	if not isinstance(entry, dict):
		return "", None, None, None
	label = str(entry.get("name_en") or entry.get("label_en") or entry.get("name") or "").strip()
	return (
		label,
		entry.get("pcode") or entry.get("code") or None,
		entry.get("name_ar") or entry.get("label_ar") or None,
		entry.get("source") or None,
	)


def normalise_chain(raw_chain: Any, nearest_place: Any = None) -> tuple[dict[str, dict], list[dict]]:
	"""Map a resolver payload onto the six-level SIRAJ hierarchy.

	Returns ``(entries, gaps)`` where ``entries`` is keyed by level field and
	``gaps`` lists levels that could not be populated. Missing intermediate
	levels are *reported*, never fabricated. A gazetteer place is kept as a
	low-confidence village candidate only when no polygon-derived village or
	community exists.
	"""
	chain = dict(raw_chain or {})
	entries: dict[str, dict] = {}
	gaps: list[dict] = []

	# Historic resolver payloads used ``community`` for level 4. Move that
	# alias to village so the six DocTypes keep their documented order.
	if chain.get("community") and not chain.get("village"):
		chain["village"] = {**dict(chain["community"]), "level": 4}
		chain.pop("community")
	elif chain.get("community") and chain.get("village"):
		legacy = chain["community"]
		current = chain["village"]
		if isinstance(legacy, dict) and isinstance(current, dict):
			if (legacy.get("pcode") and legacy.get("pcode") == current.get("pcode")) \
					or legacy.get("name_en") == current.get("name_en"):
				chain.pop("community")

	for spec in LEVELS:
		field = str(spec["field"])
		entry = chain.get(field)
		if entry:
			label, pcode, name_ar, source = _entry_value(entry)
			entries[field] = {
				"level": spec["level"],
				"field": field,
				"doctype": spec["doctype"],
				"label_en": label,
				"label_ar": name_ar,
				"pcode": pcode,
				"source": source or "polygon_containment",
				"confidence": "high",
			}
			continue
		gaps.append({
			"level": spec["level"],
			"field": field,
			"doctype": spec["doctype"],
			"reason": "no_polygon_at_level",
		})

	if nearest_place and not entries.get("village") and not entries.get("community"):
		label, pcode, name_ar, source = _entry_value(nearest_place)
		if label:
			entries["village"] = {
				"level": 4,
				"field": "village",
				"doctype": "Village",
				"label_en": label,
				"label_ar": name_ar,
				"pcode": pcode or nearest_place.get("source_id"),
				"source": source or "gazetteer_nearest",
				"confidence": "low",
				"distance_m": nearest_place.get("distance_m"),
			}
			gaps = [gap for gap in gaps if gap["field"] != "village"]
	return entries, gaps


def chain_rows(entries: dict[str, dict]) -> list[dict]:
	"""Return entries in parent-first order with deterministic codes attached."""
	rows: list[dict] = []
	parent_code: str | None = None
	for spec in LEVELS[1:]:
		field = str(spec["field"])
		entry = entries.get(field)
		if not entry:
			continue
		code = make_code(entry.get("pcode"), entry.get("label_en"), parent_code, spec["level"])
		rows.append({
			**entry,
			"code": code,
			"parent_code": parent_code,
			"parent_field": spec["parent"],
			"ancestor_codes": {row["field"]: row["code"] for row in rows},
		})
		parent_code = code
	return rows


def _resolve_country(name_or_code: Any) -> str | None:
	"""Find a Frappe Country by ISO code or exact name; never create one here."""
	if frappe is None or not name_or_code:
		return None
	value = str(name_or_code).strip()
	candidates = (
		{"code": value.upper()},
		{"name": value},
		{"name": value.title()},
	)
	for filters in candidates:
		found = frappe.db.exists("Country", filters)
		if found:
			return found
	# Frappe ships the Country DocType; a fresh site may still be missing a
	# newer ISO code. Create only when the operator is allowed to.
	if value and frappe.has_permission("Country", "create"):
		code = value if re.fullmatch(r"[A-Za-z]{2,3}", value) else None
		try:
			doc = frappe.get_doc({
				"doctype": "Country",
				"country_name": value.title() if value.isupper() else value,
				**({"code": code.upper()} if code else {}),
			}).insert(ignore_permissions=True)
			return doc.name
		except Exception:
			return None
	return None


def _write_spatial_fields(doc, entry: dict, lat: float | None, lon: float | None, dataset: str | None) -> bool:
	"""Fill only blank spatial metadata. Return True when the doc was saved."""
	changed = False
	values = {
		"latitude": lat,
		"longitude": lon,
		"pcode": entry.get("pcode"),
		"bbox": entry.get("bbox"),
		"source_dataset": dataset,
		"boundary": entry.get("boundary"),
	}
	for field, value in values.items():
		if value in (None, ""):
			continue
		if hasattr(doc, field) and doc.get(field) in (None, "", 0):
			doc.set(field, value)
			changed = True
	return changed


def _link_boundary(boundary_name: str | None, doctype: str, docname: str) -> None:
	"""Keep the polygon record and the editable hierarchy row connected."""
	if not boundary_name or frappe is None:
		return
	if not frappe.db.exists("Admin Boundary", boundary_name):
		return
	boundary = frappe.get_doc("Admin Boundary", boundary_name)
	if getattr(boundary, "linked_hierarchy", None):
		return
	if hasattr(boundary, "linked_hierarchy_doctype"):
		boundary.linked_hierarchy_doctype = doctype
		boundary.linked_hierarchy = docname
		boundary.save(ignore_permissions=True)


def _find_existing_level(entry: dict, parent_name: str | None, doctype: str,
                         code: str) -> str | None:
	"""Find a row created by another importer before inserting a duplicate.

	Codes differ between datasets (GeoNames uses dots, GADM uses dashes, OSM
	uses numeric relations), so we try several safe matches: exact code,
	normalised P-Code, indexed ``pcode`` + parent, and bilingual label + parent.
	Only existing rows are returned; nothing is modified here.
	"""
	if frappe is None:
		return None
	pcode = normalize_code(entry.get("pcode"))
	candidates = [code]
	if pcode and pcode != code:
		candidates.append(pcode)
	for candidate in candidates:
		found = frappe.db.exists(doctype, candidate)
		if found:
			return found
	parent_field = entry.get("parent_field")
	for field, value in (("pcode", entry.get("pcode")), ("label_en", entry.get("label_en"))):
		if not value:
			continue
		filters = {field: value}
		if parent_field and parent_name:
			filters[parent_field] = parent_name
		found = frappe.db.exists(doctype, filters)
		if found:
			return found
	return None


def upsert_level(entry: dict, parent_name: str | None, *, lat=None, lon=None,
                 dataset: str | None = None, create_missing: bool = True) -> dict:
	"""Create or reuse one administrative DocType row.

	Existing rows are treated as researcher-owned: only empty spatial fields
	are back-filled. If creation is not permitted, the row is reported as
	``missing`` instead of raising so a Viewer can still see the hierarchy.
	"""
	doctype = entry["doctype"]
	code = entry.get("code") or make_code(entry.get("pcode"), entry.get("label_en"),
	                                       entry.get("parent_code"), entry.get("level"))
	if frappe is None:
		return {"code": code, "name": None, "status": "no_frappe"}
	existing = _find_existing_level(entry, parent_name, doctype, code)
	if existing:
		doc = frappe.get_doc(doctype, existing)
		if _write_spatial_fields(doc, entry, lat, lon, dataset):
			doc.save(ignore_permissions=True)
		_link_boundary(entry.get("boundary"), doctype, existing)
		return {"code": code, "name": existing, "status": "existing"}

	if not create_missing or not frappe.has_permission(doctype, "create"):
		return {"code": code, "name": None, "status": "missing", "reason": "no_create_permission"}

	label_en = entry.get("label_en") or code
	values: dict[str, Any] = {
		"doctype": doctype,
		"code": code,
		"label_en": label_en,
		# Every hierarchy DocType requires label_ar. Open datasets rarely ship
		# Arabic, so seed the English label as a visible placeholder; researchers
		# replace it through the normal form without any migration.
		"label_ar": entry.get("label_ar") or label_en,
		"sort_order": 100,
		"disabled": 0,
		"is_system": 0,
	}
	if entry.get("admin_level_type"):
		values["admin_level_type"] = entry["admin_level_type"]
	if entry.get("source_kind"):
		values["source_kind"] = entry["source_kind"]
	for ancestor_field, ancestor_code in (entry.get("ancestor_codes") or {}).items():
		if ancestor_field in {spec["field"] for spec in LEVELS}:
			values[ancestor_field] = ancestor_code
	parent_field = entry.get("parent_field")
	if parent_field and parent_name:
		values[parent_field] = parent_name
	if entry.get("pcode"):
		values["pcode"] = entry["pcode"]
	if lat is not None:
		values["latitude"] = lat
	if lon is not None:
		values["longitude"] = lon
	if dataset:
		values["source_dataset"] = dataset
	if entry.get("bbox"):
		values["bbox"] = entry["bbox"]
	if entry.get("boundary"):
		values["boundary"] = entry["boundary"]
	doc = frappe.get_doc(values)
	doc.insert(ignore_permissions=True)
	_link_boundary(entry.get("boundary"), doctype, doc.name)
	return {"code": code, "name": doc.name, "status": "created"}


def hierarchy_settings() -> dict:
	"""Read the hierarchy-related subset of Geo Settings with safe defaults."""
	defaults = {"auto_create_missing": True, "link_gazetteer_as_village": True}
	if frappe is None:
		return defaults
	try:
		s = frappe.get_single("Geo Settings")
		return {
			"auto_create_missing": bool(s.auto_create_missing),
			"link_gazetteer_as_village": bool(s.link_gazetteer_as_village),
		}
	except Exception:
		return defaults


def link_resolved_chain(resolution: dict, *, create_missing: bool = True) -> dict:
	"""Turn a resolver result into linked DocType rows.

	``resolution`` is the payload returned by ``geo_resolve._resolve_one``
	(or ``resolve_point``). The caller is responsible for permission checks;
	this function never writes a record the caller cannot create.
	"""
	cfg = hierarchy_settings()
	create_missing = create_missing and cfg["auto_create_missing"]
	raw_chain = resolution.get("admin_chain") or {}
	place = resolution.get("nearest_place") if cfg["link_gazetteer_as_village"] else None
	entries, gaps = normalise_chain(raw_chain, place)
	if frappe and resolution.get("dataset"):
		for entry in entries.values():
			if not entry.get("pcode"):
				continue
			boundary = frappe.db.get_value("Admin Boundary", {
				"dataset": resolution["dataset"],
				"pcode": entry["pcode"],
				"level": entry["level"],
			}, "name")
			if boundary:
				entry["boundary"] = boundary
				geo = frappe.db.get_value("Admin Boundary", boundary, "bbox")
				if geo and not entry.get("bbox"):
					entry["bbox"] = geo
	rows = chain_rows(entries)
	dataset = resolution.get("dataset")
	lat = resolution.get("lat")
	lon = resolution.get("lon")

	country_entry = entries.get("country") or {}
	country_code = country_entry.get("pcode")
	country_name = _resolve_country(country_code or country_entry.get("label_en")) if frappe else None
	if country_code and not country_name:
		country_name = _resolve_country(country_entry.get("label_en")) if frappe else None

	hierarchy: list[dict] = []
	parent_name = country_name
	unlinked: list[dict] = []
	for row in rows:
		if row["parent_field"] == "country" and not parent_name:
			unlinked.append({**row, "reason": "country_not_resolved"})
			continue
		result = upsert_level(row, parent_name, lat=lat, lon=lon, dataset=dataset,
		                      create_missing=create_missing)
		hierarchy.append({**row, **result})
		if result.get("name"):
			parent_name = result["name"]
		else:
			unlinked.append({**row, "reason": result.get("reason") or "not_created"})

	return {
		"country": {"name": country_name, "code": country_code,
		            "label_en": country_entry.get("label_en")},
		"hierarchy": hierarchy,
		"gaps": gaps,
		"unlinked": unlinked,
		"warnings": list(resolution.get("warnings") or []),
		"provenance": list(resolution.get("provenance") or []),
		"ambiguous": bool(resolution.get("ambiguous")),
		"on_land": bool(resolution.get("on_land")),
		"raw": resolution,
	}


def resolve_and_link(latitude, longitude, *, create_missing: bool = True,
                     use_online: bool = False) -> dict:
	"""Resolve coordinates locally and link the result to SIRAJ DocTypes."""
	from siraj_research.api.geo_resolve import resolve_point  # type: ignore[import-not-found]
	resolution = resolve_point(latitude, longitude, use_online=int(bool(use_online)))
	return link_resolved_chain(resolution, create_missing=create_missing)


if frappe is not None:  # pragma: no cover - bench only
	@frappe.whitelist()
	def resolve_and_link_point(latitude, longitude, create_missing=1, use_online=0):
		"""Whitelisted entry point for map clicks and bulk coordinate imports."""
		if not frappe.has_permission("Place", "read"):
			frappe.throw("Not permitted to resolve coordinates.", frappe.PermissionError)
		can_create = str(create_missing) in ("1", "true", "True") \
			and frappe.has_permission("Place", "create")
		return resolve_and_link(latitude, longitude, create_missing=can_create,
		                        use_online=str(use_online) in ("1", "true", "True"))


def ancestors(doctype: str, name: str) -> list[dict]:
	"""Walk ``parent_*`` Link fields upward from any hierarchy record."""
	if frappe is None:
		return []
	doc = frappe.get_doc(doctype, name)
	out = []
	current = doc
	seen = set()
	while current:
		for spec in LEVELS[1:]:
			field = spec["parent"]
			if current.doctype != spec["doctype"]:
				continue
			parent_name = current.get(field)
			if not parent_name:
				break
			parent_doctype = "Country" if field == "country" else level_spec(spec["level"] - 1)["doctype"]
			key = (parent_doctype, parent_name)
			if key in seen:
				break
			seen.add(key)
			out.append({"doctype": parent_doctype, "name": parent_name,
			            "level": level_spec(spec["level"] - 1)["level"]})
			current = frappe.get_doc(parent_doctype, parent_name)
			break
		else:
			break
	return list(reversed(out))


def editable_fields(level: int) -> tuple[str, ...]:
	"""Fields operators may safely edit on a manually added hierarchy row."""
	return ("label_en", "label_ar", "description_en", "description_ar",
	        "latitude", "longitude", "bbox", "boundary", "source_dataset",
	        "source_kind", "last_verified_on", "sort_order", "disabled")
