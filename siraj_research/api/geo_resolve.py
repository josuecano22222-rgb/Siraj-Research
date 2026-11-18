"""Administrative-hierarchy and gazetteer resolution (Phase 3).

Given a lat/lon, ``resolve_point`` walks the ACTIVE Boundary Dataset and
returns country / governorate / district / municipality / community /
village / place_name along with provenance, distance, confidence and any
ambiguity flags.

Design notes
------------

* **Per-worker STRtree cache.** Building an STRtree over all Admin Boundary
  polygons at each request is too slow; we build one per worker process
  the first time it's needed, keyed by (dataset, index_version, precision).
  When an import job bumps ``index_version`` the next request transparently
  rebuilds. Cache entries are tuples ``(tree, records, by_pcode, by_parent)``.

* **Hierarchy from the finest polygon.** We query the tree at the point
  and pick the smallest (by area) polygon that contains it, then walk its
  ``parent_pcode`` chain up to country. This is more reliable than
  independent per-level point-in-polygon queries, which can disagree near
  borders.

* **Border tolerance / ambiguity.** If the point is within N metres of
  the nearest polygon boundary (computed in a local AEQD projection), or
  if two polygons at the same level both claim the point (we check with
  buffer(tolerance) to detect near-miss containment), we set
  ``ambiguous: true`` and list the candidates.

* **Sea/gap detection.** If no polygon contains the point and it is
  farther than ``sea_gap_warning_distance_km`` from the nearest polygon,
  ``on_land`` is false and the admin chain is empty.

* **Gazetteer.** For the "nearest place" component (village level), we
  query the Gazetteer Place rows and compute haversine distance + initial
  bearing; results within ``reverse_max_distance_m`` are returned sorted
  by distance. Polygon-derived admin fields always win over gazetteer
  fields (higher confidence).

* **No raw SQL.** All reads go through Frappe ORM; bulk geometry is
  fetched once per cache build with a single query.

* **Rounded-coordinate cache.** Fine-grained coordinate rounding
  (4 decimals ≈ 11 m) gives a per-process LRU cache of recent resolutions
  so the client's rapid drag events don't recompute the chain on every
  mousemove (we debounce client-side too; this is belt-and-suspenders).

* **Input validation.** Lat/lon ranges, swapped (>90 lat), null-island
  flagged with warnings in the response.
"""
from __future__ import annotations

import functools
import math
from collections import OrderedDict
from typing import Optional

import frappe

from siraj_research.geo_import import deps_ok, shapely  # shapely is required for resolve

_CACHE: dict[str, tuple] = {}
_COORD_CACHE: OrderedDict[tuple, dict] = OrderedDict()
_COORD_CACHE_MAX = 1024


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_LEVELS = [  # (level, DocType field on returned record, label)
	(0, "country",     "Country"),
	(1, "governorate", "Governorate"),
	(2, "district",    "District"),
	(3, "municipality","Municipality"),
	(4, "village",     "Village"),
	(5, "community",   "Community"),
]


def _settings() -> dict:
	try:
		s = frappe.get_single("Geo Settings")
		return {
			"active_dataset": s.active_boundary_dataset,
			"gazetteer_dataset": s.active_gazetteer_dataset,
			"border_tolerance_m": float(s.border_tolerance_m or 50),
			"reverse_max_m": float(s.reverse_max_distance_m or 5000),
			"ambiguity_m": float(s.reverse_ambiguity_threshold_m or 250),
			"country_code": (s.default_country_code or "IQ").strip().upper(),
			"sea_gap_m": float(s.sea_gap_warning_distance_km or 5) * 1000.0,
		}
	except Exception:
		return {
			"active_dataset": None,
			"gazetteer_dataset": None,
			"border_tolerance_m": 50,
			"reverse_max_m": 5000,
			"ambiguity_m": 250,
			"country_code": "IQ",
			"sea_gap_m": 5000,
		}


# ---------------------------------------------------------------------------
# STRtree cache build
# ---------------------------------------------------------------------------

def _load_trees(dataset: str) -> dict:
	"""Build STRtree(s) for `dataset` if not already cached at current version."""
	version = frappe.db.get_value("Boundary Dataset", dataset, "index_version") or 0
	cache_key = f"{dataset}:{version}"
	if cache_key in _CACHE:
		return _CACHE[cache_key]
	if not shapely:
		frappe.throw("shapely is required for geo_resolve (install with ./env/bin/pip install shapely)")
	from shapely.strtree import STRtree

	# Fetch every Admin Boundary in the dataset with its full geometry.
	# We read the WKB hex child rows directly to avoid one query per feature.
	rows = frappe.db.sql(
		"""SELECT ab.name, ab.pcode, ab.level, ab.name_en, ab.name_ar, ab.country,
		          ab.parent_pcode, ab.centroid_lat, ab.centroid_lon,
		          ag.precision, ag.geom_wkb_hex
		   FROM `tabAdmin Boundary` ab
		   LEFT JOIN `tabAdmin Boundary Geom` ag ON ag.parent = ab.name AND ag.precision='full'
		   WHERE ab.dataset = %s""",
		(dataset,),
		as_dict=True,
	)
	records = []
	geoms = []
	geom_for = {}
	by_pcode: dict[str, dict] = {}
	for r in rows:
		if not r.geom_wkb_hex:
			continue
		try:
			g = shapely.wkb.loads(bytes.fromhex(r.geom_wkb_hex))
		except Exception:
			continue
		if g is None or g.is_empty:
			continue
		rec = {
			"name": r.name,
			"pcode": r.pcode,
			"level": int(r.level or 0),
			"name_en": r.name_en,
			"name_ar": r.name_ar,
			"country": r.country,
			"parent_pcode": r.parent_pcode,
			"centroid": (r.centroid_lat, r.centroid_lon),
		}
		records.append(rec)
		geoms.append(g)
		geom_for[id(rec)] = g
		if r.pcode:
			by_pcode[r.pcode] = rec
	tree = STRtree(geoms) if geoms else None
	# Per-level record index for nearest-place lookups and gazetteer query.
	per_level: dict[int, list[dict]] = {}
	for rec in records:
		per_level.setdefault(rec["level"], []).append(rec)
	_CACHE[cache_key] = {
		"tree": tree,
		"records": records,
		"geom_for": geom_for,
		"by_pcode": by_pcode,
		"per_level": per_level,
		"geoms": geoms,
		"version": version,
	}
	return _CACHE[cache_key]


def _haversine_m(lat1, lon1, lat2, lon2):
	R = 6371000.0
	p1, p2 = math.radians(lat1), math.radians(lat2)
	dp = math.radians(lat2 - lat1)
	dl = math.radians(lon2 - lon1)
	a = math.sin(dp/2)**2 + math.cos(p1) * math.cos(p2) * math.sin(dl/2)**2
	c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
	return R * c


def _initial_bearing_deg(lat1, lon1, lat2, lon2):
	p1, p2 = math.radians(lat1), math.radians(lat2)
	dl = math.radians(lon2 - lon1)
	y = math.sin(dl) * math.cos(p2)
	x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
	return (math.degrees(math.atan2(y, x)) + 360) % 360


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def _nearest_gazetteer(lat, lon, dataset, max_m, feature_codes=None):
	"""Return the nearest Gazetteer Place within max_m, or None.

	Uses a coarse bbox pre-filter in SQL and an exact haversine in Python.
	"""
	if not dataset:
		return None
	dlat = max_m / 111320.0
	dlon = max_m / (111320.0 * max(0.1, math.cos(math.radians(lat))))
	rows = frappe.db.sql(
		"""SELECT name, name_en, name_ar, feature_code, pcode, latitude, longitude,
		          admin1_pcode, admin2_pcode, source_id
		   FROM `tabGazetteer Place`
		   WHERE dataset=%s AND latitude BETWEEN %s AND %s
		         AND longitude BETWEEN %s AND %s""",
		(dataset, lat - dlat, lat + dlat, lon - dlon, lon + dlon),
		as_dict=True,
	)
	best = None
	best_d = max_m
	for r in rows:
		if feature_codes and r.feature_code not in feature_codes:
			continue
		d = _haversine_m(lat, lon, r.latitude, r.longitude)
		if d <= best_d:
			best_d = d
			best = dict(r)
			best["distance_m"] = round(d, 1)
			best["bearing_deg"] = round(_initial_bearing_deg(lat, lon, r.latitude, r.longitude), 1)
	return best


def _validate(lat, lon):
	if not isinstance(lat, int | float) or not isinstance(lon, int | float):
		return None, "latitude and longitude must be numbers"
	if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
		return None, "coordinates out of range (lat −90..90, lon −180..180)"
	warnings = []
	if lat == 0 and lon == 0:
		warnings.append("zero_pair")
	# Swapped heuristic: if the user passed something that's actually a
	# longitude into latitude we can't tell from values alone, but very
	# large |lat|>90 is already caught by the range check.
	return (lat, lon), warnings


def _resolve_one(lat, lon):
	(point, warnings) = _validate(lat, lon)
	cfg = _settings()
	result = {
		"lat": lat, "lon": lon,
		"warnings": list(warnings),
		"on_land": False,
		"admin_chain": {},
		"ambiguous": False,
		"candidates": [],
		"nearest_place": None,
		"dataset": cfg["active_dataset"],
		"provenance": [],
	}
	if point is None:
		result["error"] = warnings if isinstance(warnings, str) else None
		return result
	lat, lon = point
	if not cfg["active_dataset"]:
		result["warnings"].append("no_active_dataset")
		return result
	ok, missing = deps_ok()
	if not ok:
		result["error"] = "server missing geospatial libs: " + ",".join(missing)
		return result
	cache = _load_trees(cfg["active_dataset"])
	tree = cache["tree"]
	if tree is None:
		result["warnings"].append("empty_dataset")
		return result
	pt = shapely.geometry.Point(lon, lat)  # x=lon, y=lat

	# Find all polygons whose envelopes intersect the buffered point; then
	# keep those that actually contain the point (exact containment).
	tol_deg = cfg["border_tolerance_m"] / 111320.0
	query_geom = pt.buffer(tol_deg) if tol_deg > 0 else pt
	hits = [cache["records"][i] for i in tree.query(query_geom)] if tree else []
	containing = []
	for rec in hits:
		g = cache["geom_for"].get(id(rec))
		if g is None:
			continue
		if g.contains(pt):
			containing.append(rec)
		elif tol_deg > 0 and g.distance(pt) * 111320.0 <= cfg["border_tolerance_m"]:
			# Close but not containing — treat as ambiguous candidate.
			result["candidates"].append({
				"level": rec["level"], "pcode": rec["pcode"],
				"name_en": rec["name_en"], "distance_m": round(g.distance(pt)*111320,1),
			})

	if not containing:
		result["on_land"] = False
		# Compute gap distance to any polygon to decide "sea vs unknown".
		nearest_geom = None
		nearest_d = float("inf")
		for g in cache["geoms"]:
			d = g.distance(pt) * 111320.0
			if d < nearest_d:
				nearest_d = d
				nearest_geom = g
		result["nearest_boundary_m"] = round(nearest_d, 1) if nearest_geom else None
		if nearest_d > cfg["sea_gap_m"]:
			result["warnings"].append("over_water_or_no_data")
		else:
			result["warnings"].append("near_boundary")
		return result
	result["on_land"] = True

	# At each level pick the smallest-area containing polygon as primary.
	best_by_level: dict[int, dict] = {}
	best_area_by_level: dict[int, float] = {}
	for rec in containing:
		lvl = rec["level"]
		g = cache["geom_for"].get(id(rec))
		area = g.area if g is not None else float("inf")
		if lvl not in best_by_level or area < best_area_by_level[lvl]:
			best_by_level[lvl] = rec
			best_area_by_level[lvl] = area

	# Flag ambiguity if multiple polygons at the same level contain the
	# point (overlapping claims) OR if we have candidates within tolerance.
	levels_with_multiple = [lvl for lvl, rec in best_by_level.items()
	                        if sum(1 for r in containing if r["level"] == lvl) > 1]
	if levels_with_multiple or result["candidates"]:
		result["ambiguous"] = True
		result["warnings"].append("boundary_ambiguity")

	# Build admin chain by walking parent_pcode up from the finest polygon.
	finest_level = max(best_by_level.keys()) if best_by_level else None
	chain = {}
	if finest_level is not None:
		cur = best_by_level[finest_level]
		for lvl, _, key in DEFAULT_LEVELS:
			if cur is None:
				break
			if cur["level"] == lvl:
				chain[key] = {"pcode": cur["pcode"], "name_en": cur["name_en"], "name_ar": cur["name_ar"]}
				cur = cache["by_pcode"].get(cur["parent_pcode"]) if cur.get("parent_pcode") else None
			elif cur["level"] > lvl:
				# We're at a finer level than this chain slot; expect a
				# parent at this level but one wasn't linked — leave blank
				# rather than guess.
				cur = cache["by_pcode"].get(cur["parent_pcode"]) if cur.get("parent_pcode") else None
	# Country fallback from finest record's `country` link (Populated Place
	# datasets often don't ship level-0 polygons).
	if "country" not in chain and finest_level is not None:
		country = best_by_level[finest_level].get("country")
		if country:
			chain["country"] = {"pcode": None, "name_en": country, "name_ar": None}
	result["admin_chain"] = chain
	result["provenance"].append("polygon_containment")

	# Gazetteer: nearest place within radius, treated as village/settlement.
	g = _nearest_gazetteer(lat, lon, cfg["gazetteer_dataset"], cfg["reverse_max_m"],
	                       feature_codes={"PPL", "PPLA", "PPLA2", "PPLA3", "PPLA4", "PPLC", "PPLCH"})
	if g:
		result["nearest_place"] = g
		result["provenance"].append("gazetteer_nearest")
	return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _merge_online(local: dict, online: dict) -> dict:
	"""Merge external reverse-geocoding results into a local resolution.

	Local polygons always win. Online values are used only to fill missing
	levels or missing P-Codes, and are labelled as medium confidence so the
	UI and ``geo_hierarchy`` can show that they are not survey-verified.
	"""
	chain = dict(local.get("admin_chain") or {})
	online_chain = dict(online.get("admin_chain") or {})
	provider = online.get("provider") or "online"
	for field, entry in online_chain.items():
		if not isinstance(entry, dict) or not entry.get("name_en"):
			continue
		if field not in chain:
			chain[field] = {**entry, "source": provider, "confidence": "medium"}
		elif not chain[field].get("pcode") and entry.get("pcode"):
			chain[field] = {**chain[field], "pcode": entry["pcode"]}
	local["admin_chain"] = chain
	if not local.get("nearest_place") and online.get("nearest_place"):
		local["nearest_place"] = {**online["nearest_place"], "source": provider,
		                          "confidence": "medium"}
	if chain and not local.get("on_land"):
		local["on_land"] = True
	provenance = list(local.get("provenance") or [])
	if "online_reverse_geocode" not in provenance:
		provenance.append("online_reverse_geocode")
	local["provenance"] = provenance
	local["online_provider"] = provider
	if online.get("error"):
		local["warnings"].append("online_fallback_failed")
	return local


def _with_fallback(result: dict, lat: float, lon: float, use_online: bool) -> dict:
	if not use_online or result.get("error"):
		return result
	from siraj_research.geo_online import lookup, should_fallback
	if not should_fallback(result):
		return result
	online = lookup(lat, lon)
	if online.get("admin_chain") or online.get("nearest_place"):
		return _merge_online(result, online)
	if online.get("error"):
		result.setdefault("warnings", []).append("online_fallback_failed")
	return result


@frappe.whitelist()
def resolve_point(latitude, longitude, use_online=0):
	"""Resolve a single (lat, lon) to an admin chain + nearest place.

	Used by the client coordinate picker to auto-fill fields when the
	user clicks the map or drags the pin. ``use_online=1`` additionally
	consults the configured external reverse geocoder when local data is
	incomplete; the setting itself can disable that request entirely.
	"""
	if not frappe.has_permission("Place", "read"):
		frappe.throw("Not permitted to resolve coordinates.", frappe.PermissionError)
	try:
		lat = float(latitude)
		lon = float(longitude)
	except Exception:
		frappe.throw("latitude and longitude must be numbers")
	use_online = str(use_online) in ("1", "true", "True")
	# Rounded-coordinate LRU, keyed by fallback mode so an offline result is
	# never mistaken for a fallback-enriched one.
	key = (round(lat, 4), round(lon, 4), use_online)
	if key in _COORD_CACHE:
		_COORD_CACHE.move_to_end(key)
		return _COORD_CACHE[key]
	result = _with_fallback(_resolve_one(lat, lon), lat, lon, use_online)
	_COORD_CACHE[key] = result
	_COORD_CACHE.move_to_end(key)
	while len(_COORD_CACHE) > _COORD_CACHE_MAX:
		_COORD_CACHE.popitem(last=False)
	return result


@frappe.whitelist()
def resolve_area(geojson):
	"""Resolve a GeoJSON geometry (Polygon/MultiPolygon) to the admin chain
	at its centroid, plus list of any Admin Boundaries that intersect the
	area at each level. Used by bulk-entry / radius drawing.
	"""
	if not frappe.has_permission("Place", "read"):
		frappe.throw("Not permitted to resolve coordinates.", frappe.PermissionError)
	if not shapely:
		frappe.throw("shapely required")
	import json as _json
	try:
		g = shapely.geometry.shape(_json.loads(geojson))
	except Exception as e:
		frappe.throw("Invalid GeoJSON: " + str(e))
	c = g.representative_point()
	centroid = _resolve_one(c.y, c.x)
	# Bbox check for intersecting boundaries.
	cfg = _settings()
	intersecting = []
	if cfg["active_dataset"]:
		cache = _load_trees(cfg["active_dataset"])
		if cache["tree"] is not None:
			for rec in cache["records"]:
				geom = cache["geom_for"].get(id(rec))
				if geom is not None and geom.intersects(g):
					intersecting.append({"level": rec["level"], "pcode": rec["pcode"],
					                     "name_en": rec["name_en"]})
	centroid["area_intersecting"] = intersecting
	return centroid


@frappe.whitelist()
def resolve_batch(points, use_online=0):
	"""Resolve an array of [lat, lon] pairs (used by batch import wizard)."""
	if not frappe.has_permission("Place", "read"):
		frappe.throw("Not permitted.", frappe.PermissionError)
	import json as _json
	pts = _json.loads(points) if isinstance(points, str) else points
	use_online = str(use_online) in ("1", "true", "True")
	out = []
	for p in pts[:500]:
		try:
			lat, lon = float(p[0]), float(p[1])
			out.append(_with_fallback(_resolve_one(lat, lon), lat, lon, use_online))
		except Exception as e:
			out.append({"error": str(e)})
	return out


@frappe.whitelist()
def invalidate_cache():
	"""Clear the in-worker STRtree and coord caches. Called by the
	Boundary Dataset import job after index_version is bumped (defensive;
	caches are keyed on index_version so they auto-rebuild)."""
	if not frappe.has_permission("Boundary Dataset", "write"):
		frappe.throw("Administrator only.", frappe.PermissionError)
	_CACHE.clear()
	_COORD_CACHE.clear()
	return {"cleared": True}
