"""Spatial data package endpoint for client-side offline reverse geocoding.

For every active Boundary Dataset the server produces a compact, compressed
GeoJSON package of simplified polygons (+ gazetteer points) that the client
downloads once per version and stores in IndexedDB. The package carries an
ETag equal to ``index_version``; subsequent requests get HTTP 304 until the
administrator runs a new import and bumps ``index_version``, at which point
the client re-fetches.

Package format
--------------
``GET /api/method/siraj_research.api.geo_package.current`` returns
``application/json``:

    {"message": {
      "dataset": "<code>",
      "version": <int>,              // ETag
      "levels":  [0,1,2,3,4],        // admin levels present
      "polygons": [                  // simplified (tolerance_m) polygons
        [level, pcode, parent_pcode, name_en, name_ar,
         [ [ [lon,lat], ... ] ], // GeoJSON-style coordinates (MultiPolygon)
         "<linked doc name>"      // deterministic name if a hierarchy row exists
      ],
      "places": [                    // gazetteer points
        [lat, lon, pcode, name_en, feature_code, admin1_pcode, admin2_pcode]
      ],
      "etag": "<dataset>:<version>"
    }}

Coordinates are already EPSG:4326. The polygon geometries are the *simplified*
variant (see Boundary Dataset.simplification_tolerance_m) so a typical
country pack compresses to <1 MB. The client feeds this into a Web Worker
that builds an in-memory rtree over the polygon bboxes and resolves points
locally in <5 ms — no server round-trip, works when the browser is offline
from the server.

Security / privacy
------------------
- Requires Place-read permission (same as resolve_point).
- Only the ACTIVE boundary + gazetteer datasets are served; disabled or
  imported-but-not-activated datasets are never downloadable.
- Polygons are served at the configured simplification tolerance (default
  ~500 m for the client pack) — that's sufficient for click/geocode accuracy
  while keeping payload small and reducing risk of misuse.
- Cache-Control: public, max-age=0, must-revalidate (the ETag drives reuse).
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
from pathlib import Path
from typing import Optional

import frappe

from siraj_research.geo_hierarchy import LEVELS, _country_names, level_spec, make_code, normalize_code
from siraj_research.geo_import import deps_ok, shapely

# Bump when the polygon row shape changes so browsers re-fetch the static
# package after an app update. Format 2 adds the Country code at row[7].
PACKAGE_FORMAT = 2


def _settings() -> dict:
    try:
        s = frappe.get_single("Geo Settings")
        return {
            "active_boundary": s.active_boundary_dataset,
            "active_gazetteer": s.active_gazetteer_dataset,
        }
    except Exception:
        return {"active_boundary": None, "active_gazetteer": None}


def _flat_coords(geom) -> list:
    """Recursively flatten a shapely geometry into GeoJSON-style coordinates.
    Returns a list for Polygon and MultiPolygon; other geometry types are
    dropped (client only needs admin polygons, which are MultiPolygons).
    """
    gtype = geom.geom_type
    if gtype == "Polygon":
        return _poly_coords(geom)
    if gtype == "MultiPolygon":
        return [_poly_coords(p) for p in geom.geoms]
    return []


def _poly_coords(poly):
    exterior = list(poly.exterior.coords)
    rings = [exterior]
    for interior in poly.interiors:
        rings.append(list(interior.coords))
    return rings


def _linked_name_maps() -> dict[str, dict[str, str]]:
	"""Map pcode/code → real DocType name for every hierarchy level.

	The offline worker can only write a Link field safely when it knows the
	linked document exists. Shipping these names with the package lets it
	fill Country/Governorate (and deeper levels) with no server round-trip.
	"""
	maps: dict[str, dict[str, str]] = {}
	for spec in LEVELS[1:]:
		field = str(spec["field"])
		maps[field] = {}
		try:
			rows = frappe.get_all(spec["doctype"], fields=["name", "code", "pcode"],
			                      limit_page_length=0)
		except Exception:
			continue
		for row in rows:
			name = str(row.get("name") or "")
			if not name:
				continue
			for value in (row.get("pcode"), row.get("code")):
				if value:
					maps[field][normalize_code(value)] = name
	return maps


def _pack_polygons(dataset: str) -> tuple[list, int]:
    version = int(frappe.db.get_value("Boundary Dataset", dataset, "index_version") or 0)
    # Prefer 'simplified' geometries (smaller); fall back to 'full'.
    rows = frappe.db.sql(
        """SELECT ab.pcode, ab.parent_pcode, ab.level, ab.name_en, ab.name_ar,
                  ab.country, ag.`precision`, ag.geom_wkb_hex, ag.point_count
           FROM `tabAdmin Boundary` ab
           LEFT JOIN (
               SELECT `parent`, `precision`, geom_wkb_hex, point_count,
                      ROW_NUMBER() OVER (PARTITION BY `parent` ORDER BY
                          CASE WHEN `precision`='simplified' THEN 0 ELSE 1 END) AS rn
               FROM `tabAdmin Boundary Geom`
           ) ag ON ag.parent = ab.name AND ag.rn = 1
           WHERE ab.dataset=%s AND ag.geom_wkb_hex IS NOT NULL""",
        (dataset,),
        as_dict=True,
    )
    out = []
    if not shapely:
        return out, version
    linked_maps = _linked_name_maps()
    countries = _country_names()
    for r in rows:
        try:
            g = shapely.wkb.loads(bytes.fromhex(r.geom_wkb_hex))
        except Exception:
            continue
        if g is None or g.is_empty:
            continue
        coords = _flat_coords(g)
        if not coords:
            continue
        # Round to 5 decimals (~1.1 m) to shrink payload further without
        # meaningfully affecting point-in-polygon accuracy.
        coords = _round_coords(coords, 5)
        level = int(r.level or 0)
        pcode = r.pcode or ""
        name_en = (r.name_en or "")[:120]
        # Only reuse a real document name; never invent one offline.
        linked_name = ""
        if level == 0:
            linked_name = countries.get(pcode.upper()) or countries.get(name_en) or ""
        else:
            field = str(level_spec(level)["field"])
            candidates = [pcode, make_code(pcode, name_en, r.parent_pcode or "", level)]
            for candidate in candidates:
                linked_name = linked_maps.get(field, {}).get(normalize_code(candidate), "")
                if linked_name:
                    break
        out.append([
            level,
            pcode,
            r.parent_pcode or "",
            name_en,
            (r.name_ar or "")[:120],
            coords,
            linked_name,
            (r.country or ""),
        ])
    return out, version


def _round_coords(obj, ndigits):
    if isinstance(obj, int | float):
        return round(obj, ndigits)
    return [_round_coords(x, ndigits) for x in obj]


def _pack_places(dataset: str | None) -> list:
    if not dataset:
        return []
    rows = frappe.db.sql(
        """SELECT latitude, longitude, pcode, name_en, feature_code,
                  admin1_pcode, admin2_pcode
           FROM `tabGazetteer Place`
           WHERE dataset=%s AND latitude IS NOT NULL AND longitude IS NOT NULL""",
        (dataset,),
        as_dict=True,
    )
    out = []
    for r in rows:
        out.append([
            round(float(r.latitude), 5),
            round(float(r.longitude), 5),
            r.pcode or "",
            (r.name_en or "")[:80],
            (r.feature_code or "")[:8],
            r.admin1_pcode or "",
            r.admin2_pcode or "",
        ])
    return out


def build_package(dataset: str | None, gazetteer: str | None = None) -> dict:
    """Build the client package entirely from local bench data."""
    if not dataset:
        return {"dataset": None, "version": 0, "format": PACKAGE_FORMAT,
                "levels": [], "polygons": [], "places": [], "etag": "none:0"}
    ok, missing = deps_ok()
    if not ok:
        return {"dataset": dataset, "version": 0, "format": PACKAGE_FORMAT,
                "levels": [], "polygons": [], "places": [],
                "etag": f"{dataset}:0.{PACKAGE_FORMAT}", "error": "missing_dependencies",
                "missing": missing}
    polygons, version = _pack_polygons(dataset)
    places = _pack_places(gazetteer)
    return {
        "dataset": dataset,
        "version": int(version or 0),
        "format": PACKAGE_FORMAT,
        "levels": sorted({row[0] for row in polygons}),
        "polygons": polygons,
        "places": places,
        "etag": f"{dataset}:{int(version or 0)}.{PACKAGE_FORMAT}",
    }


@frappe.whitelist(methods=["GET"])
def current():
    """Return the active spatial package as a normal JSON response.

    Frappe serialises the returned dict through its normal JSON
    machinery; writing raw gzip bytes there serialised every byte as an
    integer array and produced a 500 once the package became non-empty.
    Clients send the last etag as ``?version=`` and get a 304 when nothing
    changed, which keeps repeat loads cheap.
    """
    if not frappe.has_permission("Place", "read"):
        frappe.throw("Not permitted.", frappe.PermissionError)
    cfg = _settings()
    payload = build_package(cfg["active_boundary"], cfg["active_gazetteer"])
    inm = ""
    if frappe.request:
        inm = frappe.request.headers.get("If-None-Match", "") or ""
    inm = inm or str((getattr(frappe, "form_dict", None) or {}).get("version") or "")
    if payload.get("etag") and payload["etag"] in inm:
        frappe.response["http_status_code"] = 304
        return ""
    return payload


def export_offline_package(path: str | None = None) -> dict:
    """Materialise the package as a same-origin static asset.

    This is the zero-internet bootstrap: run it on the bench after local
    imports, then the browser can load ``/assets/siraj_research/data/
    geo-package.json`` without calling any remote service.
    """
    cfg = _settings()
    if not cfg["active_boundary"]:
        return {"error": "No active boundary dataset", "written": False}
    payload = build_package(cfg["active_boundary"], cfg["active_gazetteer"])
    if payload.get("error"):
        return {**payload, "written": False}
    target = Path(path) if path else Path(frappe.get_app_path(
        "siraj_research", "public", "data", "geo-package.json"))
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
                   encoding="utf-8")
    tmp.replace(target)
    return {
        "written": True,
        "path": str(target),
        "dataset": payload["dataset"],
        "version": payload["version"],
        "polygons": len(payload["polygons"]),
        "places": len(payload["places"]),
        "etag": payload["etag"],
    }
