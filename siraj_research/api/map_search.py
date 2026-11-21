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
	HIERARCHY_CHILD_DOCTYPE,
	HIERARCHY_DOCTYPES,
	HIERARCHY_PARENT_FIELD,
	LEVEL_LABELS,
	bboxes_intersect,
	haversine_m,
	missing_chain_levels,
	normalise_name,
	parse_coordinate_query,
	parse_levels,
	parse_types,
	point_in_bbox,
	radial_bboxes,
	radial_lat_range,
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


def _rows(doctype, fields, page_size=20000, filters=None):
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
		filters=filters or {},
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

def _resolve_coordinate(result: dict, use_online: bool = False) -> dict:
	"""Attach the local administrative resolution to a parsed coordinate.

	Offline-first: `_resolve_one` reads local spatial data only; the hybrid
	Nominatim fallback is opt-in via ``use_online`` (geo_resolve's own
	contract). Any resolver failure degrades to ``resolve_error`` — a
	coordinate search must never die because geospatial libs are missing.
	"""
	try:
		from siraj_research.api.geo_resolve import _resolve_one, _with_fallback
		lat, lon = float(result["lat"]), float(result["lon"])
		resolved = _resolve_one(lat, lon)
		if use_online:
			resolved = _with_fallback(resolved, lat, lon, True)
		chain = resolved.get("admin_chain") or {}
		return {
			"admin_chain": chain,
			"missing_levels": missing_chain_levels(chain),
			"on_land": bool(resolved.get("on_land")),
			"nearest_place": resolved.get("nearest_place"),
			"provenance": list(resolved.get("provenance") or []),
			"warnings": list(resolved.get("warnings") or []),
		}
	except Exception as exc:  # degrade, never fail the search itself
		return {"resolve_error": str(exc)[:200]}


def _nearby(lat: float, lon: float, radius_m: float, types: list[str], limit: int) -> list[dict]:
	"""Record pins and gazetteer places within ``radius_m`` of a point.

	Distances are haversine metres (derived ranking values — the stored
	coordinates themselves are never rewritten). Bounding boxes prefilter
	per SQL; the exact radius test runs in Python.
	"""
	lat, lon = float(lat), float(lon)
	radius_m = max(1.0, float(radius_m))
	boxes = radial_bboxes(lat, lon, radius_m)
	min_lat, max_lat = radial_lat_range(lat, radius_m)
	out = []

	def keep(point_lat, point_lon):
		try:
			plat, plon = float(point_lat), float(point_lon)
		except (TypeError, ValueError):
			return None
		if not any(point_in_bbox(plat, plon, (min_lat, b0, max_lat, b1))
		           for b0, b1 in boxes):
			return None
		dist = haversine_m(lat, lon, plat, plon)
		return (dist, plat, plon) if dist <= radius_m else None

	# Records (small tables — load + filter in Python, same as the map does).
	for doctype in (types or list(GEO_TYPES)):
		if doctype not in GEO_TYPES:
			continue
		title = ENTITIES.get(doctype, "display_name")
		try:
			rows = _record_rows(doctype, (title, "latitude", "longitude"))
		except Exception:
			continue
		for row in rows:
			hit = keep(row.get("latitude"), row.get("longitude"))
			if hit is None:
				continue
			dist, plat, plon = hit
			out.append({
				"kind": "record", "doctype": doctype, "name": row.get("name"),
				"label": row.get(title) or row.get("name"),
				"point": [_coord_str(row.get("latitude")), _coord_str(row.get("longitude"))],
				"distance_m": round(dist, 1),
			})
	# Gazetteer places (larger — SQL range prefilter per box first).
	try:
		place_rows = []
		for b0, b1 in boxes:
			place_rows.extend(_rows(
				"Gazetteer Place",
				("name_en", "name_ar", "pcode", "feature_code", "latitude", "longitude"),
				# frappe's db_query only special-cases `between` for Date/
				# Datetime; on Float it does flt([a, b]) -> 0.0 and emits
				# broken SQL. Two-sided numeric ranges must be >= / <=.
				filters=[["latitude", ">=", min_lat], ["latitude", "<=", max_lat],
				         ["longitude", ">=", b0], ["longitude", "<=", b1]],
			))
	except Exception:
		place_rows = []
	seen = set()
	for row in place_rows:
		key = row.get("name")
		if key in seen:
			continue
		seen.add(key)
		hit = keep(row.get("latitude"), row.get("longitude"))
		if hit is None:
			continue
		dist, _plat, _plon = hit
		out.append({
			"kind": "place",
			"name_en": row.get("name_en"), "name_ar": row.get("name_ar"),
			"pcode": row.get("pcode"), "feature_code": row.get("feature_code"),
			"point": [_coord_str(row.get("latitude")), _coord_str(row.get("longitude"))],
			"distance_m": round(dist, 1),
		})
	out.sort(key=lambda r: r["distance_m"])
	return out[: max(1, int(limit))]


def _coordinate_branch(query: str, use_online: bool = False, radius=5000,
                       nearby_types=None, limit: int = DEFAULT_LIMIT):
	parsed = parse_coordinate_query(query)
	if parsed is None:
		return None, False
	if "error" in parsed:
		return parsed, True  # error dicts carry {"error", "input", "suggestion"}
	result = dict(parsed)
	result.update(_resolve_coordinate(result, use_online=use_online))
	try:
		lat, lon = float(result["lat"]), float(result["lon"])
		result["radius_m"] = float(radius)
		result["nearby"] = _nearby(lat, lon, radius, nearby_types, limit)
	except (TypeError, ValueError):
		result["nearby"] = []
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
def search(query="", scope="all", levels="", types="", limit=DEFAULT_LIMIT,
           use_online=0, radius=5000):
	"""Advanced map search: coordinates, regions, places, records.

	``scope``      all | regions | places | records
	``levels``     comma-separated region levels 0..5 (regions scope)
	``types``      comma-separated DocTypes (records scope, GEO_TYPES only)
	``limit``      per-group cap, 1..25
	``use_online`` coordinate resolution: 1 = allow the external
	               reverse-geocoder fallback (hybrid); default 0 = local only
	``radius``     nearby-search radius in metres around a coordinate

	Every coordinate in the payload is an exact string; a coordinate-like
	query always yields a ``coordinate`` entry (result or error) carrying
	the local admin chain, its explicitly-missing levels and nearby pins —
	never a coerced guess.
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

	online = str(use_online).lower() in ("1", "true", "yes")
	try:
		radius_val = max(1.0, min(float(radius), 50000.0))
	except (TypeError, ValueError):
		radius_val = 5000.0

	query = (query or "").strip()
	coordinate, saw_coordinate = (
		_coordinate_branch(query, use_online=online, radius=radius_val,
		                   nearby_types=types_wanted, limit=limit)
		if query else (None, False)
	)

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


# ---------------------------------------------------------------------------
# Viewport search ("search this area")
# ---------------------------------------------------------------------------

@frappe.whitelist()
def search_bbox(min_lat, min_lon, max_lat, max_lon, types="", limit=20):
	"""Records, gazetteer places and regions inside a map viewport.

	``min_lon > max_lon`` is accepted and treated as an antimeridian
	wrapping box (the west edge is east of the east edge). The echoed
	``bbox`` keeps the caller's strings verbatim — the float copies are
	used only for validation and the SQL prefilter, never for the reply.
	"""
	raw_bbox = [str(min_lat), str(min_lon), str(max_lat), str(max_lon)]
	try:
		min_lat, min_lon = float(min_lat), float(min_lon)
		max_lat, max_lon = float(max_lat), float(max_lon)
	except (TypeError, ValueError):
		return {"error": "invalid_bbox", "bbox": None,
		        "records": [], "places": [], "regions": [],
		        "counts": {"records": 0, "places": 0, "regions": 0}}
	if not (-90 <= min_lat <= max_lat <= 90
	        and -180 <= min_lon <= 180 and -180 <= max_lon <= 180):
		return {"error": "invalid_bbox", "bbox": None,
		        "records": [], "places": [], "regions": [],
		        "counts": {"records": 0, "places": 0, "regions": 0}}
	try:
		limit = max(1, min(int(limit), MAX_LIMIT))
	except (TypeError, ValueError):
		limit = 20
	bbox = (min_lat, min_lon, max_lat, max_lon)
	boxes = [(min_lon, max_lon)] if min_lon <= max_lon else [(min_lon, 180.0), (-180.0, max_lon)]
	types_wanted = parse_types(types, GEO_TYPES)

	records = []
	for doctype in types_wanted or list(GEO_TYPES):
		if doctype not in GEO_TYPES:
			continue
		title = ENTITIES.get(doctype, "display_name")
		try:
			rows = _record_rows(doctype, (title, "latitude", "longitude", "geo_precision"))
		except Exception:
			continue
		for row in rows:
			try:
				plat = float(row.get("latitude"))
				plon = float(row.get("longitude"))
			except (TypeError, ValueError):
				continue
			if not point_in_bbox(plat, plon, bbox):
				continue
			if plat == 0 and plon == 0:
				continue
			records.append({
				"kind": "record", "doctype": doctype, "name": row.get("name"),
				"label": row.get(title) or row.get("name"),
				"point": [_coord_str(row.get("latitude")), _coord_str(row.get("longitude"))],
				"geo_precision": row.get("geo_precision"),
			})
	records.sort(key=lambda r: (r["doctype"], normalise_name(r.get("label") or "")))

	places, seen = [], set()
	for b0, b1 in boxes:
		try:
			rows = _rows(
				"Gazetteer Place",
				("name_en", "name_ar", "pcode", "feature_code", "latitude", "longitude"),
				# See _nearby: numeric between is broken in db_query — use >= / <=.
				filters=[["latitude", ">=", min_lat], ["latitude", "<=", max_lat],
				         ["longitude", ">=", b0], ["longitude", "<=", b1]],
			)
		except Exception:
			rows = []
		for row in rows:
			if row.get("name") in seen:
				continue
			seen.add(row.get("name"))
			try:
				plat, plon = float(row.get("latitude")), float(row.get("longitude"))
			except (TypeError, ValueError):
				continue
			if not point_in_bbox(plat, plon, bbox):
				continue
			places.append({
				"kind": "place",
				"name_en": row.get("name_en"), "name_ar": row.get("name_ar"),
				"pcode": row.get("pcode"), "feature_code": row.get("feature_code"),
				"point": [_coord_str(row.get("latitude")), _coord_str(row.get("longitude"))],
			})

	regions = []
	try:
		boundary_rows = _rows(
			"Admin Boundary",
			("name_en", "name_ar", "level", "pcode", "centroid_lat", "centroid_lon",
			 "bbox_min_lat", "bbox_min_lon", "bbox_max_lat", "bbox_max_lon", "dataset"),
		)
	except Exception:
		boundary_rows = []
	active = _settings()["boundary"]
	for row in _active_first(boundary_rows, active):
		row_bbox = [_coord_str(row.get(k)) for k in
		            ("bbox_min_lat", "bbox_min_lon", "bbox_max_lat", "bbox_max_lon")]
		region_bbox = None
		if all(row_bbox):
			try:
				region_bbox = tuple(float(v) for v in row_bbox)
			except (TypeError, ValueError):
				region_bbox = None
		centroid = (_coord_str(row.get("centroid_lat")), _coord_str(row.get("centroid_lon")))
		hit = False
		if region_bbox and bboxes_intersect(region_bbox, bbox):
			hit = True
		elif all(centroid):
			try:
				hit = point_in_bbox(float(centroid[0]), float(centroid[1]), bbox)
			except (TypeError, ValueError):
				hit = False
		if not hit:
			continue
		level = row.get("level")
		try:
			level = int(level)
		except (TypeError, ValueError):
			level = None
		regions.append({
			"kind": "region",
			"level": level,
			"level_name": LEVEL_LABELS.get(level if level is not None else -1),
			"name_en": row.get("name_en"), "name_ar": row.get("name_ar"),
			"pcode": row.get("pcode"),
			"source": "boundary", "dataset": row.get("dataset"),
			"centroid": list(centroid),
			"bbox": row_bbox if region_bbox else None,
			"chain": [],
		})

	return {
		"bbox": raw_bbox,
		"records": records[:limit],
		"places": places[:limit],
		"regions": regions[:limit],
		"counts": {"records": len(records), "places": len(places),
		           "regions": len(regions)},
	}


# ---------------------------------------------------------------------------
# Cascading region browser (Country → Community)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def region_children(level, parent="", query="", limit=50):
	"""Children of one hierarchy selection — the cascade behind the picker.

	``level`` 0 = countries (ERPNext Country registry, ISO code as pcode);
	1..5 = Governorate…Community filtered by the previous selection's
	DocType name through the registry's Link fields. Each child carries
	its exact centroid strings and, when the active boundary dataset has
	its pcode, the polygon bbox for a precise fly-to.
	"""
	try:
		level = int(level)
	except (TypeError, ValueError):
		return {"error": "invalid_level", "level": None, "children": []}
	if level not in range(0, 6):
		return {"error": "invalid_level", "level": None, "children": []}
	try:
		limit = max(1, min(int(limit), 200))
	except (TypeError, ValueError):
		limit = 50
	parent = (parent or "").strip()
	query_norm = normalise_name(query)

	children = []
	if level == 0:
		try:
			rows = _rows("Country", ("name", "code"), page_size=5000)
		except Exception:
			rows = []
		for row in rows:
			children.append({
				"name": row.get("name"),
				"pcode": row.get("code"),
				"name_en": row.get("name"), "name_ar": None,
				"level": 0, "level_name": LEVEL_LABELS[0],
				"centroid": [None, None], "bbox": None,
			})
	else:
		doctype = HIERARCHY_CHILD_DOCTYPE[level]
		parent_field = HIERARCHY_PARENT_FIELD[level]
		filters = {"disabled": 0}
		if parent:
			filters[parent_field] = parent
		try:
			rows = _rows(doctype, ("name", "label_en", "label_ar", "pcode",
			                       "latitude", "longitude"), filters=filters)
		except Exception:
			rows = []
		pcodes = [r.get("pcode") for r in rows if r.get("pcode")]
		bbox_by_pcode = {}
		if pcodes:
			try:
				for b in _rows("Admin Boundary",
				               ("pcode", "bbox_min_lat", "bbox_min_lon",
				                "bbox_max_lat", "bbox_max_lon"),
				               filters={"pcode": ["in", pcodes]}):
					vals = [_coord_str(b.get(k)) for k in
					        ("bbox_min_lat", "bbox_min_lon", "bbox_max_lat", "bbox_max_lon")]
					if all(vals) and b.get("pcode"):
						bbox_by_pcode[b["pcode"]] = vals
			except Exception:
				bbox_by_pcode = {}
		for row in rows:
			children.append({
				"name": row.get("name"),
				"pcode": row.get("pcode"),
				"name_en": row.get("label_en"), "name_ar": row.get("label_ar"),
				"level": level, "level_name": LEVEL_LABELS[level],
				"centroid": [_coord_str(row.get("latitude")),
				             _coord_str(row.get("longitude"))],
				"bbox": bbox_by_pcode.get(row.get("pcode")),
			})

	if query_norm:
		children = [c for c in children
		            if query_norm in normalise_name(c.get("name_en"))
		            or query_norm in normalise_name(c.get("name_ar"))
		            or query_norm in normalise_name(c.get("pcode"))]
	children.sort(key=lambda c: (normalise_name(c.get("name_en") or ""),
	                             normalise_name(c.get("name_ar") or "")))
	return {"level": level, "parent": parent,
	        "children": children[:limit], "counts": {"children": len(children)}}
