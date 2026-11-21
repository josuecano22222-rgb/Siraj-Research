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


def _parent_doctype_for(parent_field: str | None) -> str | None:
	"""Doctype linked by a hierarchy row's ``parent_<level>`` field."""
	if not parent_field:
		return None
	if parent_field == "country":
		return "Country"
	for spec in LEVELS[1:]:
		if spec["parent"] == parent_field:
			return "Country" if spec["level"] == 1 else level_spec(spec["level"] - 1)["doctype"]
	return None


def _resolve_link_name(doctype: str, value: Any) -> str | None:
	"""Resolve a code/name carried by a resolver chain to a real DocType name."""
	if frappe is None or not value:
		return None
	if doctype == "Country":
		return _resolve_country(value)
	if frappe.db.exists(doctype, value):
		return value
	for field in ("code", "pcode", "name"):
		found = frappe.db.exists(doctype, {field: value})
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

	parent_field = entry.get("parent_field")
	parent_doctype = _parent_doctype_for(parent_field)
	resolved_parent = None
	if parent_doctype and parent_name:
		resolved_parent = _resolve_link_name(parent_doctype, parent_name)
		if not resolved_parent:
			# Never create a child pointing at a missing parent: Frappe's
			# _validate_links would raise and abort the whole resolution.
			return {
				"code": code, "name": None, "status": "missing",
				"reason": "parent_not_found", "parent_doctype": parent_doctype,
				"parent_value": parent_name,
			}

	existing = _find_existing_level(entry, resolved_parent, doctype, code)
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
	# Only the immediate parent Link is required. Resolver ancestor_codes are
	# deterministic *document names* for hierarchy DocTypes but not for the
	# built-in Country DocType, so writing them verbatim used to produce
	# "Could not find Country: PS". Ancestors are walked via parent Links.
	if parent_field and resolved_parent:
		values[parent_field] = resolved_parent
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
	try:
		doc.insert(ignore_permissions=True)
	except Exception as exc:
		# Two concurrent map events (drag-end + field change) can race the
		# same deterministic code. Treat a duplicate as a successful reuse
		# instead of returning HTTP 409 to the form.
		duplicate = frappe.DuplicateEntryError if hasattr(frappe, "DuplicateEntryError") else ()
		message = str(exc)
		if (duplicate and isinstance(exc, duplicate)) or "Duplicate entry" in message:
			reused = frappe.db.exists(doctype, code)
			if not reused:
				# Consistent reads use this session's snapshot: a concurrent
				# writer (the import job's auto-sync, another tab) can commit
				# this row after our first SELECT — the INSERT (a current
				# read) then raises the duplicate while exists() still misses
				# it. End the stale transaction (upserts are idempotent and
				# the sync loop commits in batches anyway) and look again.
				frappe.db.commit()
				reused = frappe.db.exists(doctype, code)
			if reused:
				_link_boundary(entry.get("boundary"), doctype, reused)
				return {"code": code, "name": reused, "status": "existing"}
		raise
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


# ---------------------------------------------------------------------------
# Polygon → hierarchy synchronisation
# ---------------------------------------------------------------------------

def _iso_from_pcode(pcode: Any) -> str | None:
    text = str(pcode or "").strip().upper()
    if "." in text:
        candidate = text.split(".", 1)[0]
        if len(candidate) in (2, 3) and candidate.isalpha():
            return candidate
    match = re.match(r"^([A-Z]{2,3})", text)
    return match.group(1) if match else None


def containing_ancestors(level: int, point, candidates: Iterable[dict]) -> dict[int, tuple[float, dict]]:
    """Return the smallest containing polygon for each level below ``level``.

    ``candidates`` is an iterable of records carrying ``level`` and ``geom``.
    This is pure geometry logic; the caller supplies the STRtree candidates.
    """
    best: dict[int, tuple[float, dict]] = {}
    for record in candidates or []:
        try:
            candidate_level = int(record.get("level") or 0)
        except (TypeError, ValueError):
            continue
        if candidate_level < 0 or candidate_level >= level:
            continue
        geom = record.get("geom")
        if geom is None:
            continue
        try:
            if not geom.contains(point):
                continue
            area = float(getattr(geom, "area", 0) or 0)
        except Exception:
            continue
        if candidate_level not in best or area < best[candidate_level][0]:
            best[candidate_level] = (area, record)
    return best


def _resolve_country_document(value, countries: dict[str, str]) -> str | None:
    """Resolve a source country tag/code to a known Country document name."""
    text = str(value or "").strip()
    if not text:
        return None
    if text in countries:
        return countries[text]
    upper = text.upper()
    if upper in countries:
        return countries[upper]
    match = re.match(r"^([A-Z]{2})(?:[-:_.\s]|$)", upper)
    if match and match.group(1) in countries:
        return countries[match.group(1)]
    return None


def _country_names() -> dict[str, str]:
    if frappe is None:
        return {}
    rows = frappe.get_all("Country", fields=["name", "code"], limit_page_length=0)
    result: dict[str, str] = {}
    for row in rows:
        if row.get("code"):
            result[str(row["code"]).upper()] = row["name"]
        result[row["name"]] = row["name"]
    return result


def _sorted_strtree(records: list[dict], strtree_cls: Any = None) -> Any:
    """Sort ``records`` parent-first and build an STRtree aligned with them.

    ``STRtree.query`` returns indices into the geometry list the tree was
    built from, so the tree must be constructed **after** the sort, from that
    same order. Sorting records afterwards (or building the tree first) leaves
    every index pointing at the wrong row, which made hierarchy sync skip
    almost every boundary that relies on spatial country/parent inference.

    Sorts ``records`` in place by ``(level, pcode)`` so callers still process
    parents before children. Pass ``strtree_cls`` to inject a stand-in in
    pure-Python tests; the default imports shapely lazily.
    """
    records.sort(key=lambda rec: (rec["level"], str(rec["pcode"] or "")))
    geoms = [rec["geom"] for rec in records]
    if not geoms:
        return None
    if strtree_cls is None:
        from shapely.strtree import STRtree
        strtree_cls = STRtree
    return strtree_cls(geoms)


def sync_hierarchy_from_boundaries(dataset: str, *, levels: Iterable[int] | None = None,
                                   create_missing: bool = True,
                                   batch_size: int = 200) -> dict:
    """Create/update hierarchy rows from every polygon in a Boundary Dataset.

    This is the step that turns imported GADM/OSM geometry into actual
    Governorate/District/Municipality/Village/Community records at the final
    level. Parents come from ``parent_pcode`` when present; otherwise they are
    inferred spatially from the smallest containing polygon at each lower
    level. Existing rows are never overwritten — only empty spatial fields are
    back-filled by :func:`upsert_level`. Nameless source features (the import
    fell back to the pcode for ``name_en``) are not promoted into the
    hierarchy — they would only surface as hash labels; their geometry stays
    on the boundary for map pinning and is reported as ``unnamed``.
    """
    if frappe is None:
        return {"error": "frappe unavailable", "dataset": dataset}
    from siraj_research.geo_import import deps_ok, shapely
    ok, missing = deps_ok()
    if not ok or shapely is None:
        return {"error": "geospatial dependencies missing: " + ",".join(missing),
                "dataset": dataset}
    from shapely import wkb as shapely_wkb

    rows = frappe.db.sql(
        """SELECT ab.name, ab.pcode, ab.level, ab.name_en, ab.name_ar, ab.country,
                  ab.parent_pcode, ab.centroid_lat, ab.centroid_lon, ab.bbox,
                  ab.source_id, ag_s.geom_wkb_hex AS simplified_wkb,
                  ag_f.geom_wkb_hex AS full_wkb
           FROM `tabAdmin Boundary` ab
           LEFT JOIN `tabAdmin Boundary Geom` ag_s
             ON ag_s.parent = ab.name AND ag_s.precision='simplified'
           LEFT JOIN `tabAdmin Boundary Geom` ag_f
             ON ag_f.parent = ab.name AND ag_f.precision='full'
           WHERE ab.dataset = %s""",
        (dataset,),
        as_dict=True,
    )
    records: list[dict] = []
    by_pcode: dict[str, dict] = {}
    for row in rows:
        hex_wkb = row.simplified_wkb or row.full_wkb
        if not hex_wkb:
            continue
        try:
            geom = shapely_wkb.loads(bytes.fromhex(hex_wkb))
        except Exception:
            continue
        if geom is None or geom.is_empty:
            continue
        try:
            level = int(row.level or 0)
        except (TypeError, ValueError):
            continue
        record = {
            "name": row.name,
            "pcode": row.pcode or row.source_id,
            "source_id": row.source_id,
            "level": level,
            "name_en": row.name_en,
            "name_ar": row.name_ar,
            "country": row.country,
            "parent_pcode": row.parent_pcode,
            "centroid_lat": row.centroid_lat,
            "centroid_lon": row.centroid_lon,
            "bbox": row.bbox,
            "geom": geom,
        }
        records.append(record)
        if record["pcode"]:
            by_pcode[normalize_code(record["pcode"])] = record
    # Sort parent-first and build the STRtree from that same order — tree
    # indices address the geometry list they were built from (regression:
    # sorting after STRtree() mis-mapped ~97% of spatial candidate lookups
    # and hierarchy sync skipped nearly every OSM boundary).
    tree = _sorted_strtree(records)

    wanted_levels = {int(level) for level in levels} if levels else {1, 2, 3, 4, 5}
    countries = _country_names()
    name_by_pcode: dict[str, str] = {}
    counts: dict[int, dict[str, int]] = {}
    inferred_parents = 0
    skipped = 0
    unnamed = 0
    processed = 0

    for record in records:
        level = record["level"]
        if level not in wanted_levels or level < 1 or level > 5:
            continue
        # Nameless source features fell back to the pcode at import time
        # (name_en == pcode): they have no honest label, so they must not
        # appear as hash rows in the editable hierarchy. Their geometry
        # stays on the boundary for map pinning, and spatial parent
        # inference simply walks past them (they never enter name_by_pcode).
        if not record["name_en"] or record["name_en"] == record["pcode"]:
            unnamed += 1
            continue
        pcode = record["pcode"] or record["name"]
        if not pcode:
            skipped += 1
            continue
        iso = (record["country"] or _iso_from_pcode(pcode)
               or _iso_from_pcode(record["source_id"]))
        country_name = countries.get(iso) if iso else None

        point = record["geom"].representative_point()
        candidates = [records[i] for i in tree.query(point)] if tree is not None else []
        best = containing_ancestors(level, point, candidates)
        if not country_name and 0 in best:
            # OSM child objects rarely carry an ISO tag. Inherit the country
            # from the containing admin_level=2 polygon in the same dataset.
            country_record = best[0][1]
            country_name = _resolve_country_document(
                country_record.get("country") or country_record.get("name_en"),
                countries,
            )
        if not country_name:
            skipped += 1
            continue

        ancestors: dict[str, str] = {"country": country_name}
        parent_name: str | None = None
        parent_level = 0
        parent_code = normalize_code(record["parent_pcode"]) if record["parent_pcode"] else None
        if parent_code and parent_code in name_by_pcode:
            parent_name = name_by_pcode[parent_code]
            parent_record = by_pcode.get(parent_code)
            try:
                parent_level = int(parent_record["level"]) if parent_record else level - 1
            except (TypeError, ValueError, KeyError):
                parent_level = level - 1
        else:
            for ancestor_level, (_, ancestor_record) in best.items():
                if ancestor_level == 0:
                    continue
                ancestor_name = name_by_pcode.get(normalize_code(ancestor_record["pcode"]))
                if ancestor_name:
                    ancestors[str(LEVELS[ancestor_level]["field"])] = ancestor_name
            # Walk deepest-first and take the first ancestor that actually
            # exists as a row: nameless boundaries are in `best` (their
            # geometry contains the point) but never became hierarchy rows,
            # so a bare max() would pick them and the last-resort country
            # branch would discard a valid shallower named parent.
            ancestor_levels = sorted(
                (level_key for level_key in best if level_key > 0), reverse=True)
            for ancestor_level in ancestor_levels:
                ancestor_record = best[ancestor_level][1]
                ancestor_name = name_by_pcode.get(
                    normalize_code(ancestor_record["pcode"]))
                if ancestor_name:
                    parent_level = ancestor_level
                    parent_record = ancestor_record
                    parent_name = ancestor_name
                    inferred_parents += 1
                    break
        if not parent_name:
            # Last resort: attach to the country. Intermediate Links stay
            # empty, which the DocTypes now explicitly allow.
            parent_name = country_name
            parent_level = 0

        parent_field = "country" if parent_level == 0 else str(LEVELS[parent_level]["field"])
        spec = LEVELS[level]
        entry = {
            "doctype": spec["doctype"],
            "level": level,
            "field": spec["field"],
            "pcode": pcode,
            "code": make_code(pcode, record["name_en"], normalize_code(parent_code), level),
            "label_en": record["name_en"] or str(pcode),
            "label_ar": record["name_ar"],
            "parent_code": parent_code,
            "parent_field": parent_field,
            "ancestor_codes": ancestors,
            "boundary": record["name"],
            "bbox": record["bbox"],
            "source": dataset,
            "admin_level_type": f"Imported level {level}",
        }
        result = upsert_level(
            entry, parent_name,
            lat=record["centroid_lat"], lon=record["centroid_lon"],
            dataset=dataset, create_missing=create_missing,
        )
        if result.get("name"):
            name_by_pcode[normalize_code(pcode)] = result["name"]
        bucket = counts.setdefault(level, {"created": 0, "existing": 0, "missing": 0})
        status = result.get("status", "missing")
        bucket[status] = bucket.get(status, 0) + 1
        processed += 1
        if processed % max(1, batch_size) == 0:
            frappe.db.commit()

    frappe.db.commit()
    return {
        "dataset": dataset,
        "boundaries": len(records),
        "synced": processed,
        "skipped": skipped,
        "unnamed": unnamed,
        "inferred_parents": inferred_parents,
        "by_level": {str(level): counts.get(level, {}) for level in sorted(wanted_levels)},
    }
