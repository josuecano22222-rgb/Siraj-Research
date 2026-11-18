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

    {
      "dataset": "<code>",
      "version": <int>,              // ETag
      "levels":  [0,1,2,3,4],        // admin levels present
      "polygons": [                  // simplified (tolerance_m) polygons
        [level, pcode, parent_pcode, name_en, name_ar,
         [ [ [lon,lat], ... ] ] ]   // GeoJSON-style coordinates (MultiPolygon)
      ],
      "places": [                    // gazetteer points
        [lat, lon, pcode, name_en, feature_code, admin1_pcode, admin2_pcode]
      ]
    }

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
from typing import Optional

import frappe

from siraj_research.geo_import import deps_ok, shapely


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


def _pack_polygons(dataset: str) -> tuple[list, int]:
    version = int(frappe.db.get_value("Boundary Dataset", dataset, "index_version") or 0)
    # Prefer 'simplified' geometries (smaller); fall back to 'full'.
    rows = frappe.db.sql(
        """SELECT ab.pcode, ab.parent_pcode, ab.level, ab.name_en, ab.name_ar,
                  ag.precision, ag.geom_wkb_hex, ag.point_count
           FROM `tabAdmin Boundary` ab
           LEFT JOIN (
               SELECT parent, precision, geom_wkb_hex, point_count,
                      ROW_NUMBER() OVER (PARTITION BY parent ORDER BY
                          CASE WHEN precision='simplified' THEN 0 ELSE 1 END) AS rn
               FROM `tabAdmin Boundary Geom`
           ) ag ON ag.parent = ab.name AND ag.rn = 1
           WHERE ab.dataset=%s AND ag.geom_wkb_hex IS NOT NULL""",
        (dataset,),
        as_dict=True,
    )
    out = []
    if not shapely:
        return out, version
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
        out.append([
            int(r.level or 0),
            r.pcode or "",
            r.parent_pcode or "",
            (r.name_en or "")[:120],
            (r.name_ar or "")[:120],
            coords,
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


@frappe.whitelist(methods=["GET"])
def current():
    """Return the active spatial package as JSON.

    The response sets ETag = str(version) and honours If-None-Match so the
    client can skip re-download when unchanged. Gzip is applied when the
    client accepts it (payload compresses ~75%).
    """
    if not frappe.has_permission("Place", "read"):
        frappe.throw("Not permitted.", frappe.PermissionError)
    cfg = _settings()
    dataset = cfg["active_boundary"]
    if not dataset:
        return {"dataset": None, "version": 0, "levels": [], "polygons": [], "places": []}
    ok, missing = deps_ok()
    polygons, version = _pack_polygons(dataset)
    places = _pack_places(cfg["active_gazetteer"])
    levels = sorted({row[0] for row in polygons})
    payload = {
        "dataset": dataset,
        "version": int(version or 0),
        "levels": levels,
        "polygons": polygons,
        "places": places,
    }
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    etag = '"' + hashlib.sha1(str(version).encode() + dataset.encode()).hexdigest()[:16] + '"'
    inm = frappe.request.headers.get("If-None-Match", "") if frappe.request else ""
    if inm and etag in inm:
        frappe.response["http_status_code"] = 304
        return ""
    accept_enc = (frappe.request.headers.get("Accept-Encoding", "") if frappe.request else "")
    if "gzip" in accept_enc:
        body = gzip.compress(body, compresslevel=6)
        frappe.response["headers"] = {"Content-Encoding": "gzip"}
    frappe.response["data"] = body
    frappe.response["type"] = "application/json; charset=utf-8"
    frappe.response["headers"] = frappe.response.get("headers") or {}
    frappe.response["headers"].update({
        "ETag": etag,
        "Cache-Control": "public, max-age=0, must-revalidate",
        "Vary": "Accept-Encoding",
    })
    return ""
