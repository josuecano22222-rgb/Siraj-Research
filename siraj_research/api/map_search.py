# siraj_research.api.map_search — advanced map search endpoint.
#
# One query answers four questions at once: is the text a coordinate, does
# it name a region (admin boundary / hierarchy registry), does it name a
# gazetteer place, or does it match a mapped research record. Results are
# ranked deterministically and every coordinate leaves the server as an
# exact string — see utils/map_search.py for the precision contract and
# docs/map-search.md for the user-facing rules.

from __future__ import annotations

import frappe

from siraj_research.report_access import readable_rows
from siraj_research.utils.map_search import (
	HIERARCHY_DOCTYPES,
	LEVEL_LABELS,
	normalise_name,
	parse_coordinate_query,
	parse_levels,
	parse_types,
	rank_candidates,
)
from siraj_research.visualization import ENTITIES, GEO_TYPES

MAX_LIMIT = 25
DEFAULT_LIMIT = 8
MIN_QUERY_CHARS = 2

# Hierarchy registry doctypes that carry label_en/label_ar + parent_pcode.
LABEL_FIELDS = ("label_en", "label_ar", "pcode", "parent_pcode",
                "latitude", "longitude", "disabled")


def _settings() -> dict:
	"""Active boundary/gazetteer datasets (search prefers them, never requires)."""
	try:
		s = frappe.get_single("Geo Settings")
		return {"boundary": s.active_boundary_dataset,
		        "gazetteer": s.active_gazetteer_dataset}
	except Exception:
		return {"boundary": None, "gazetteer": None}


def _coord_str(value):
	"""Stored coordinate → exact string. Floats use Python's shortest
	round-trip repr (the value as the database returned it); strings pass
	through untouched. Never routed through formatting that rounds."""
	if value is None or value == "":
		return None
	if isinstance(value, float):
		return str(value)
	return str(value).strip() or None


def _rows(doctype, fields, page_size=20000):
	"""One-shot role-permitted list read for the geo tables.

	Gazetteer/boundary/hierarchy ship no custom has_permission hooks
	(hooks.py keeps them commented), so the role check applied by
	``get_list`` is the full contract — and a single query keeps a
	16k-row gazetteer scan cheap enough for a debounced keystroke.
	"""
	if not frappe.has_permission(doctype, "read"):
		return []
	fields = list(dict.fromkeys(["name", *fields]))
	return frappe.get_list(
		doctype,
		fields=fields,
		limit_page_length=page_size,
		order_by="name asc",
	)


def _record_rows(doctype, fields):
	"""Permission-aware iterator for research records (document checks on)."""
	return list(readable_rows(doctype, fields, page_size=20000))


def _active_first(rows: list[dict], active, key="dataset") -> list[dict]:
	"""Put rows from the active dataset first; keep the rest as fallback."""
	if not active:
		return rows
	active_rows = [r for r in rows if r.get(key) == active]
	other = [r for r in rows if r.get(key) != active]
	return active_rows + other


# ---------------------------------------------------------------------------
# Coordinate branch
# ---------------------------------------------------------------------------

def _coordinate_branch(query: str):
	parsed = parse_coordinate_query(query)
	if parsed is None:
		return None, False
	if "error" in parsed:
		return parsed, True  # error dicts carry {"error", "input", "suggestion"}
	# Attach the human context: what contains this point, exactly.
	result = dict(parsed)
	return result, True


# ---------------------------------------------------------------------------
# Regions: Admin Boundary geometry rows + the hierarchy registry
# ---------------------------------------------------------------------------

def _boundary_regions(query: str, levels: list[int], active, limit: int) -> list[dict]:
	fields = ("name_en", "name_ar", "local_name", "pcode", "level", "parent_pcode",
	          "centroid_lat", "centroid_lon", "bbox_min_lat", "bbox_min_lon",
	          "bbox_max_lat", "bbox_max_lon", "dataset", "linked_hierarchy_doctype",
	          "linked_hierarchy")
	rows = _rows("Admin Boundary", fields)
	by_pcode = {}
	# Active dataset wins pcode collisions (iterate others first, active last).
	for row in reversed(_active_first(rows, active)):
		if row.get("pcode"):
			by_pcode[row["pcode"]] = row
	candidates = []
	for row in rows:
		level = row.get("level")
		if not isinstance(level, int):
			try:
				level = int(level)
			except (TypeError, ValueError):
				continue
		if levels and level not in levels:
			continue
		candidates.append({**row, "_level": level, "_source": "boundary"})
	ranked = rank_candidates(
		query, candidates,
		label_keys=("name_en", "name_ar", "local_name"),
		pcode_keys=("pcode", "parent_pcode"),
		tie_break=lambda r: r.get("_level", 99),
	)
	out = []
	for row in ranked[:limit]:
		out.append(_region_payload(row, by_pcode))
	return out


def _hierarchy_regions(query: str, levels: list[int], limit: int) -> list[dict]:
	"""Search the hierarchy registry (Country → Community) by label/pcode."""
	by_pcode: dict[str, dict] = {}
	candidates: list[dict] = []
	for level, doctype in HIERARCHY_DOCTYPES.items():
		if levels and level not in levels:
			continue
		if doctype == "Country":
			# Country lives in ERPNext: plain `name`, no label_en columns.
			try:
				rows = _rows("Country", ("name",), page_size=5000)
			except Exception:
				rows = []
			for row in rows:
				item = {"_level": 0, "_source": "hierarchy", "doctype": "Country",
				        "name": row.get("name"), "name_en": row.get("name"),
				        "pcode": None, "label_en": row.get("name"), "label_ar": None}
				candidates.append(item)
				if row.get("name"):
					by_pcode[row["name"]] = item
			continue
		fields = (*LABEL_FIELDS, "name")
		try:
			rows = _rows(doctype, fields)
		except Exception:
			rows = []
		for row in rows:
			if row.get("disabled"):
				continue
			item = {"_level": level, "_source": "hierarchy", "doctype": doctype,
			        "name": row.get("name"),
			        "name_en": row.get("label_en"), "name_ar": row.get("label_ar"),
			        "pcode": row.get("pcode"), "parent_pcode": row.get("parent_pcode"),
			        "label_en": row.get("label_en"), "label_ar": row.get("label_ar"),
			        "centroid_lat": _coord_str(row.get("latitude")),
			        "centroid_lon": _coord_str(row.get("longitude"))}
			candidates.append(item)
			if row.get("pcode"):
				by_pcode[row["pcode"]] = item
	ranked = rank_candidates(
		query, candidates,
		label_keys=("label_en", "label_ar", "name_en", "name_ar"),
		pcode_keys=("pcode",),
		tie_break=lambda r: r.get("_level", 99),
	)
	# Hierarchy rows are the fallback: boundary results already carry the
	# same pcode → drop duplicates, prefer the geometry-bearing row.
	return [_region_payload(row, by_pcode) for row in ranked[:limit]]


def _region_payload(row: dict, by_pcode: dict) -> dict:
	chain = []
	seen = set()
	cursor = row
	while cursor is not None and len(chain) < 6:
		pcode = cursor.get("pcode")
		if pcode and pcode in seen:
			break
		if pcode:
			seen.add(pcode)
		label = cursor.get("name_en") or cursor.get("label_en") or cursor.get("name")
		label_ar = cursor.get("name_ar") or cursor.get("label_ar")
		if label or label_ar:
			chain.append({"level": cursor.get("_level", cursor.get("level")),
			              "name_en": label, "name_ar": label_ar,
			              "pcode": pcode})
		parent = cursor.get("parent_pcode")
		cursor = by_pcode.get(parent) if parent else None
	level = row.get("_level", row.get("level"))
	bbox = [row.get("bbox_min_lat"), row.get("bbox_min_lon"),
	        row.get("bbox_max_lat"), row.get("bbox_max_lon")]
	bbox = [ _coord_str(v) for v in bbox ]
	payload = {
		"kind": "region",
		"level": level if isinstance(level, int) else None,
		"level_name": LEVEL_LABELS.get(level if isinstance(level, int) else -1),
		"name_en": row.get("name_en") or row.get("label_en"),
		"name_ar": row.get("name_ar") or row.get("label_ar"),
		"pcode": row.get("pcode"),
		"parent_pcode": row.get("parent_pcode"),
		"source": row.get("_source", "boundary"),
		"dataset": row.get("dataset"),
		"centroid": [ _coord_str(row.get("centroid_lat")),
		              _coord_str(row.get("centroid_lon")) ],
		"bbox": bbox if all(bbox) else None,
		"chain": chain,
		"score": row.get("_score"),
	}
	return payload


def _search_regions(query: str, levels: list[int], active, limit: int) -> list[dict]:
	boundary = _boundary_regions(query, levels, active, limit)
	boundary_pcodes = {r.get("pcode") for r in boundary if r.get("pcode")}
	hierarchy = _hierarchy_regions(query, levels, limit)
	merged = boundary + [r for r in hierarchy
	                     if not (r.get("pcode") and r.get("pcode") in boundary_pcodes)]
	merged.sort(key=lambda r: (-r.get("score", 0), r.get("level") if r.get("level") is not None else 99,
	                           normalise_name(r.get("name_en") or r.get("name_ar") or "")))
	return merged[:limit]


# ---------------------------------------------------------------------------
# Gazetteer places
# ---------------------------------------------------------------------------

def _search_places(query: str, active, limit: int) -> list[dict]:
	fields = ("name_en", "name_ar", "asciiname", "pcode", "feature_code",
	          "latitude", "longitude", "admin1_pcode", "admin2_pcode", "dataset")
	rows = _rows("Gazetteer Place", fields)
	candidates = _active_first(rows, active)
	ranked = rank_candidates(
		query, candidates,
		label_keys=("name_en", "name_ar", "asciiname"),
		pcode_keys=("pcode",),
	)
	out = []
	for row in ranked[:limit]:
		out.append({
			"kind": "place",
			"name_en": row.get("name_en"),
			"name_ar": row.get("name_ar"),
			"pcode": row.get("pcode"),
			"feature_code": row.get("feature_code"),
			"admin1_pcode": row.get("admin1_pcode"),
			"admin2_pcode": row.get("admin2_pcode"),
			"dataset": row.get("dataset"),
			"point": [_coord_str(row.get("latitude")), _coord_str(row.get("longitude"))],
			"score": row.get("_score"),
		})
	return out


# ---------------------------------------------------------------------------
# Research records (the pins already drawn on the map)
# ---------------------------------------------------------------------------

def _search_records(query: str, types: list[str], limit: int) -> list[dict]:
	allowed = types or list(GEO_TYPES)
	out = []
	for doctype in allowed:
		if doctype not in GEO_TYPES:
			continue
		title = ENTITIES.get(doctype, "display_name")
		try:
			rows = _record_rows(doctype, (title, "latitude", "longitude", "geo_precision"))
		except Exception:
			continue
		candidates = []
		for row in rows:
			lat = _coord_str(row.get("latitude"))
			lon = _coord_str(row.get("longitude"))
			if lat is None or lon is None:
				continue
			try:
				lat_f, lon_f = float(lat), float(lon)
			except ValueError:
				continue
			if not (-90 <= lat_f <= 90 and -180 <= lon_f <= 180):
				continue
			if lat_f == 0 and lon_f == 0:  # historic unset pair (see visualization)
				continue
			candidates.append({**row, "_label": row.get(title) or row.get("name")})
		ranked = rank_candidates(query, candidates, label_keys=("_label",), pcode_keys=())
		for row in ranked:
			out.append({
				"kind": "record",
				"doctype": doctype,
				"name": row.get("name"),
				"label": row.get("_label"),
				"point": [_coord_str(row.get("latitude")), _coord_str(row.get("longitude"))],
				"geo_precision": row.get("geo_precision"),
				"score": row.get("_score"),
			})
	out.sort(key=lambda r: (-r.get("score", 0), normalise_name(r.get("label") or "")))
	return out[:limit]


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@frappe.whitelist()
def search(query="", scope="all", levels="", types="", limit=DEFAULT_LIMIT):
	"""Advanced map search: coordinates, regions, places, records.

	``scope``      all | regions | places | records
	``levels``     comma-separated region levels 0..5 (regions scope)
	``types``      comma-separated DocTypes (records scope, GEO_TYPES only)
	``limit``      per-group cap, 1..25

	Every coordinate in the payload is an exact string; a coordinate-like
	query always yields a ``coordinate`` entry (result or error), never a
	coerced guess.
	"""
	try:
		limit = max(1, min(int(limit), MAX_LIMIT))
	except (TypeError, ValueError):
		limit = DEFAULT_LIMIT
	scope = (scope or "all").strip().lower()
	if scope not in ("all", "regions", "places", "records"):
		scope = "all"
	levels_wanted = parse_levels(levels)
	types_wanted = parse_types(types, GEO_TYPES)

	query = (query or "").strip()
	coordinate, saw_coordinate = _coordinate_branch(query) if query else (None, False)

	result = {
		"query": query,
		"scope": scope,
		"coordinate": coordinate,
		"regions": [],
		"places": [],
		"records": [],
		"counts": {"regions": 0, "places": 0, "records": 0},
	}
	# A coordinate query answers for itself; textual scopes still run so a
	# pasted coordinate that also matches a name (rare) stays discoverable.
	need_text = len(query) >= MIN_QUERY_CHARS and not (saw_coordinate and coordinate and "error" not in coordinate)
	if not need_text:
		if saw_coordinate and coordinate and "error" in coordinate:
			result["counts"] = {"regions": 0, "places": 0, "records": 0}
		return result

	cfg = _settings()
	if scope in ("all", "regions"):
		result["regions"] = _search_regions(query, levels_wanted, cfg["boundary"], limit)
	if scope in ("all", "places"):
		result["places"] = _search_places(query, cfg["gazetteer"], limit)
	if scope in ("all", "records"):
		result["records"] = _search_records(query, types_wanted, limit)
	result["counts"] = {
		"regions": len(result["regions"]),
		"places": len(result["places"]),
		"records": len(result["records"]),
	}
	return result
