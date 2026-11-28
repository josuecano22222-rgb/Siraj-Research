# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
"""Governorate geo-data completion.

Fills ``latitude``, ``longitude`` and ``bbox`` (W, S, E, N) on every
``Governorate`` so that map-click auto-fills country and governorate. All
geometry is derived from authoritative sources -- never hand-written:

* **Imported Admin Boundary** geometry (``pcode == code`` at ``level == 1``),
  which takes precedence;
* **Natural Earth** admin-1 (``iso_3166_2 == code``) as a fallback.

Every calculation uses ``shapely.representative_point`` (NOT centroid), with
antimeridian handling. The operation is idempotent, fills only empty fields,
sets ``source_kind`` only on an actual fill, and never calls ``frappe.db.commit``.

Run it via the ``bench execute`` entry point:

    bench --site frappe.com execute \
        siraj_research.api.governorate_geo.fill_governorate_geo --kwargs '{}'

Pass ``{"dry_run": true}`` to plan without writing.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

try:
    import frappe
    _HAS_FRAPPE = True
except Exception:  # pragma: no cover - pure-Python test gate
    frappe = None  # type: ignore[assignment]
    _HAS_FRAPPE = False


try:
    from shapely import get_coordinates as _get_coordinates
    from shapely import transform as _shapely_transform
    from shapely import wkb as _shapely_wkb
    from shapely import wkt as _shapely_wkt
    from shapely.geometry import Point as _shapely_Point
    from shapely.geometry import base as _shapely_base
    from shapely.geometry import shape as _shapely_shape

    _HAS_SHAPELY = True
except Exception:  # pragma: no cover - shapely is an optional runtime dep
    _shapely_shape = None  # type: ignore[assignment]
    _shapely_Point = None  # type: ignore[assignment]
    _shapely_base = None  # type: ignore[assignment]
    _shapely_wkb = None  # type: ignore[assignment]
    _shapely_wkt = None  # type: ignore[assignment]
    _get_coordinates = None  # type: ignore[assignment]
    _shapely_transform = None  # type: ignore[assignment]
    _HAS_SHAPELY = False


# ---------------------------------------------------------------------------
# Constants / contract
# ---------------------------------------------------------------------------

GOVERNORATE_DOCTYPE = "Governorate"
ADMIN_BOUNDARY_DOCTYPE = "Admin Boundary"
ADMIN_BOUNDARY_GEOM_DOCTYPE = "Admin Boundary Geom"

# Sources are recorded on the filled Governorate. "Imported" = imported Admin
# Boundary geometry; "Online" = Natural Earth (mirrors geo_resolve SOURCE_ONLINE).
SOURCE_IMPORTED = "Imported"
SOURCE_NATURAL_EARTH = "Online"

# Natural Earth admin-1 scales, finest first. The finest available scale is
# preferred; a coarser scale may never replace a finer one.
NE_SCALE_ORDER = ["10m", "50m", "110m"]

# Governorate fields that are filled (fill-only-empty) and never overwritten.
GEO_FIELDS = ("latitude", "longitude", "bbox")
# Non-coordinate provenance we own; set ONLY on an actual fill.
PROVENANCE_FIELD = "source_kind"


# ---------------------------------------------------------------------------
# Code normalization / matching
# ---------------------------------------------------------------------------

def normalize_code(code):
    """Trim + uppercase an administrative code. Returns ``None`` if empty."""
    if code is None:
        return None
    value = str(code).strip().upper()
    return value or None


def iso_suffix(code):
    """Extract the subdivision suffix from an ISO-3166-2 code (``US-MN`` -> ``MN``)."""
    value = normalize_code(code)
    if value is None:
        return None
    return value.split("-", 1)[1] if "-" in value else None


def _country_key(country):
    """Country key used for matching (case-insensitive)."""
    if country is None:
        return None
    return str(country).strip().upper() or None


def _country_iso_a2(name: str) -> str | None:
    """Best-effort ISO-3166-1 alpha-2 for a country *name*.

    Used only to compare NE ``iso_a2`` against the Governorate country. Falls
    back to comparing the alpha-2 present inside the Governorate ``code``
    (e.g. ``US-MN`` -> ``US``), which is more reliable than a name->code map.
    """
    if not name:
        return None
    # Direct alpha-2 (two uppercase letters) or alpha-3.
    token = str(name).strip()
    if len(token) == 2 and token.isalpha():
        return token.upper()
    # Code embedded in the name (e.g. "United States (US)") - take first 2 letters.
    return token[:2].upper() if token[:2].isalpha() else None


def match_admin_boundary(code, country, rows):
    """Return the unique matching Admin Boundary row for ``code`` at level 1.

    Matching is on normalized ``pcode`` and ``country``; ``level`` must be 1.
    A duplicate ``pcode`` (conflict) returns ``None`` so it can be reported and
    skipped rather than arbitrarily resolved.
    """
    target = normalize_code(code)
    if target is None:
        return None
    target_country = _country_key(country)
    matches = []
    for row in rows:
        if normalize_code(row.get("pcode")) != target:
            continue
        if row.get("level") != 1:
            continue
        row_country = _country_key(row.get("country"))
        if target_country and row_country and row_country != target_country:
            continue
        matches.append(row)
    return matches[0] if len(matches) == 1 else None


def match_natural_earth(code, country, features):
    """Return the unique matching NE admin-1 feature for ``code``.

    Matching is on ``iso_3166_2 == code`` (verified against the real bundled
    110m admin-1 schema). Country is used only as a secondary consistency
    check. A missing ``iso_3166_2`` never matches; there is **no name fallback**.
    """
    target = normalize_code(code)
    if target is None:
        return None
    target_country = _country_key(country)
    matches = []
    for feat in features:
        if normalize_code(feat.get("iso_3166_2")) != target:
            continue
        feat_country = _country_key(feat.get("iso_a2"))
        if target_country and feat_country and feat_country != target_country:
            continue
        matches.append(feat)
    return matches[0] if len(matches) == 1 else None


# ---------------------------------------------------------------------------
# Antimeridian + geometry
# ---------------------------------------------------------------------------

def wrap_longitude(lon):
    """Normalize a longitude into [-180, 180], preserving +180."""
    lon = float(lon)
    while lon > 180.0:
        lon -= 360.0
    while lon < -180.0:
        lon += 360.0
    return lon


def is_antimeridian_crossing(geom):
    """True if a geometry crosses the antimeridian.

    A polygon crosses the antimeridian when it is represented in a continuous
    frame: either a vertex longitude lies outside [-180, 180], or the
    longitude extent exceeds 180 degrees. Both representations (split across
    +/-180 in [-180,180], or continuous past 180) are detected.
    """
    if geom is None or getattr(geom, "is_empty", False):
        return False
    minx, _, maxx, _ = geom.bounds
    if maxx - minx > 180.0:
        return True
    if not _HAS_SHAPELY:
        return False
    for x, _ in _get_coordinates(geom):
        if x < -180.0 or x > 180.0:
            return True
    return False


def _to_continuous_frame(geom):
    """Return a copy of ``geom`` with longitudes in a continuous frame.

    Polygons that cross the antimeridian (longitude extent > 180, or vertices
    outside [-180,180]) are shifted so their longitudes are continuous (no
    wrap-back at +/-180). Polygons that do not cross are returned unchanged.
    """
    if not is_antimeridian_crossing(geom):
        return geom
    return _shapely_transform(geom, _shift_east_of_antimeridian)


def _shift_east_of_antimeridian(coords):
    """Vectorized longitude shift for shapely 2.x ``transform``.

    Receives an (N, 2) coordinate array; shifts negative longitudes (+360) so
    a polygon crossing the antimeridian becomes continuous in the frame where
    its longitudes increase past 180.
    """
    import numpy as np
    coords = np.asarray(coords, dtype=float)
    coords = coords.copy()
    coords[:, 0] = np.where(coords[:, 0] < 0, coords[:, 0] + 360.0, coords[:, 0])
    return coords


def _validated_polygonal(geom):
    """Validate ``geom`` is a non-empty Polygon/MultiPolygon; raise otherwise."""
    if geom is None or getattr(geom, "is_empty", True):
        raise ValueError("geometry is empty or missing")
    if not _HAS_SHAPELY:  # pragma: no cover
        raise RuntimeError("shapely is required for geometry calculations")
    if geom.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError(f"unsupported geometry type: {geom.geom_type}")
    if not geom.is_valid:
        # Detect-and-skip: an invalid geometry is reported, never silently
        # repaired (repairing could shift coordinates away from the source).
        raise ValueError("geometry is invalid")
    return geom


def representative_point(geom):
    """Return ``(lat, lon)`` for the shapely representative point.

    The representative point is guaranteed inside the polygon -- unlike the
    centroid, which may fall outside a concave polygon. Invalid, empty or
    non-Polygonal (e.g. GeometryCollection) geometries raise ``ValueError``.
    The longitude is normalized into [-180, 180].
    """
    geom = _validated_polygonal(geom)
    rp = geom.representative_point()
    return rp.y, wrap_longitude(rp.x)


def compute_bbox(geom):
    """Return ``(W, S, E, N)`` for ``geom`` with ``W <= E``.

    Antimeridian-crossing polygons are expressed in the continuous frame so
    ``W <= E`` always holds; the stored bbox is the continuous-frame bounds.
    """
    geom = _validated_polygonal(geom)
    cont = _to_continuous_frame(geom)
    minx, miny, maxx, maxy = cont.bounds
    return (float(minx), float(miny), float(maxx), float(maxy))


def bbox_contains(bbox, lat, lon):
    """True if point ``(lat, lon)`` falls inside bbox ``(W, S, E, N)``."""
    w, s, e, n = bbox
    return w <= lon <= e and s <= lat <= n


def _bbox_to_text(bbox):
    return f"{bbox[0]:.6f},{bbox[1]:.6f},{bbox[2]:.6f},{bbox[3]:.6f}"


# ---------------------------------------------------------------------------
# Empty / fill-only-empty
# ---------------------------------------------------------------------------

def is_empty(value):
    """True if a field value is empty (None or blank)."""
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def select_geometry(imported_geom, imported_kind, ne_geom, ne_kind):
    """Apply source precedence: imported first, NE only when no imported.

    Returns ``(geom, kind)``. A coarser-scale NE geometry never replaces a
    finer one -- that rule is enforced by the caller via scale ordering.
    """
    if imported_geom is not None:
        return imported_geom, imported_kind
    if ne_geom is not None:
        return ne_geom, ne_kind
    return None, None


def plan_fill(gov, geom, source_kind, source_dataset=None):
    """Return an update dict for ``gov`` or ``None`` when nothing can be filled.

    Fill-only-empty: only fields currently empty are set. A record that already
    has *any* geo value (lat/lon/bbox) is left untouched and reported as partial
    rather than partially completed -- partial completion would risk a
    malformed coord/bbox pair, so it is skipped, not guessed at.
    """
    if is_empty(gov.get("latitude")) and is_empty(gov.get("longitude")) \
            and is_empty(gov.get("bbox")):
        try:
            lat, lon = representative_point(geom)
            bbox = compute_bbox(geom)
        except (ValueError, RuntimeError):
            return None
        updates = {
            "latitude": lat,
            "longitude": lon,
            "bbox": _bbox_to_text(bbox),
            PROVENANCE_FIELD: source_kind,
        }
        if source_dataset is not None:
            updates["source_dataset"] = source_dataset
        return updates
    return None


# ---------------------------------------------------------------------------
# Orchestration (testable against stubbed providers)
# ---------------------------------------------------------------------------

def _norm_geom(geom):
    """Coerce a provider geometry (WKB/WKT/GeoJSON dict/shapely) to shapely."""
    if geom is None:
        return None
    if _HAS_SHAPELY:
        if isinstance(geom, _shapely_base.BaseGeometry):
            return geom
        if isinstance(geom, bytes | bytearray):
            return _shapely_wkb.loads(bytes(geom))
        if isinstance(geom, str):
            return _shapely_wkt.loads(geom)
        if isinstance(geom, dict):
            return _shapely_shape(geom)
    # Fallback: store raw; representative_point will reject non-shapely.
    return geom


def classify_and_fill(rows, imported_geoms, ne_features, dry_run=False,
                      apply=None):
    """Plan (and optionally apply) the fill for a batch of Governorate rows.

    ``rows`` are plain dicts (the Governorate fields). ``imported_geoms`` maps
    ``code -> shapely geometry`` from Admin Boundary. ``ne_features`` is a list
    of dicts each carrying ``iso_3166_2``, ``iso_a2`` and a ``geometry``.

    ``apply(code, updates)`` is the write callback; when omitted or ``dry_run``
    is True, nothing is written. Returns a coverage report dict that reconciles:
    ``total == filled + already_set + unmatched + partial + invalid_geometry
    + duplicate_match + conflicting_match``.
    """
    report = {
        "total": 0, "filled": 0, "imported": 0, "natural_earth": 0,
        "already_set": 0, "unmatched": 0, "partial": 0,
        "invalid_geometry": 0, "duplicate_match": 0, "conflicting_match": 0,
        "unmatched_codes": [], "dry_run": dry_run,
    }

    # Index imported geometries by normalized pcode for O(1) lookup.
    imported_by_code = {}
    for code, geom in imported_geoms.items():
        key = normalize_code(code)
        if key in imported_by_code:
            report["duplicate_match"] += 1
        imported_by_code[key] = geom

    for gov in rows:
        report["total"] += 1
        code = normalize_code(gov.get("code"))
        country = gov.get("country")

        # Already fully populated -> never touch.
        if not any(is_empty(gov.get(f)) for f in GEO_FIELDS):
            report["already_set"] += 1
            continue

        # Partial (some geo fields set, others empty) -> skip, do not guess.
        if any(is_empty(gov.get(f)) for f in GEO_FIELDS) and \
           any(not is_empty(gov.get(f)) for f in GEO_FIELDS):
            report["partial"] += 1
            continue

        # Resolve source geometry with precedence: imported first, NE fallback.
        geom = None
        kind = None
        imported_geom = None
        if code is not None and code in imported_by_code:
            imported_geom = _norm_geom(imported_by_code[code])
        if imported_geom is not None:
            geom, kind = select_geometry(imported_geom, SOURCE_IMPORTED, None, None)
        else:
            ne_match = match_natural_earth(code, country, ne_features) if code else None
            if ne_match is not None:
                candidate = _norm_geom(ne_match.get("geometry"))
                if candidate is not None:
                    geom, kind = select_geometry(None, None, candidate, SOURCE_NATURAL_EARTH)
                else:
                    report["invalid_geometry"] += 1
                    continue

        if geom is None:
            report["unmatched"] += 1
            report["unmatched_codes"].append(code)
            continue

        updates = plan_fill(gov, geom, kind, source_dataset=None)
        if updates is None:
            # geometry was invalid (representative_point/compute_bbox failed).
            report["invalid_geometry"] += 1
            continue

        if kind == SOURCE_IMPORTED:
            report["imported"] += 1
        elif kind == SOURCE_NATURAL_EARTH:
            report["natural_earth"] += 1
        report["filled"] += 1
        if apply is not None and not dry_run:
            apply(code, updates)

    return report


# ---------------------------------------------------------------------------
# Resolver: point -> governorate
# ---------------------------------------------------------------------------

def _haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km."""
    import math
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))


def resolve_point(lat, lon, candidates, max_distance_km=0):
    """Resolve a map-click ``(lat, lon)`` to a governorate.

    ``candidates`` is a list of ``{"code", "geometry"}`` dicts. Strict mode
    (``max_distance_km == 0``): return the candidate whose geometry contains the
    point; a boundary point or an ambiguous (overlapping) match returns ``None``
    rather than being arbitrarily assigned. Fallback mode
    (``max_distance_km > 0``): if no candidate contains the point, return the
    nearest candidate within the threshold; otherwise ``None``.
    """
    point = None
    if _HAS_SHAPELY:
        point = _shapely_Point(lon, lat)
    if point is None:  # pragma: no cover
        return None

    containing = []
    valid = []
    for cand in candidates:
        geom = _norm_geom(cand.get("geometry"))
        if geom is None or getattr(geom, "is_empty", True):
            continue
        try:
            valid.append((cand, geom))
        except Exception:
            continue
    for cand, geom in valid:
        try:
            if geom.contains(point):
                containing.append(cand["code"])
        except Exception:
            continue

    if len(containing) == 1:
        return {"code": containing[0], "lat": lat, "lon": lon}
    if len(containing) > 1:
        # Ambiguous overlap -> do not arbitrarily assign.
        return None

    if max_distance_km and max_distance_km > 0:
        best = None
        best_d = None
        for cand, geom in valid:
            try:
                rp = geom.representative_point()
            except Exception:
                continue
            d = _haversine_km(lat, lon, rp.y, rp.x)
            if best_d is None or d < best_d:
                best_d, best = d, cand["code"]
        if best is not None and best_d is not None and best_d <= max_distance_km:
            return {"code": best, "lat": lat, "lon": lon, "distance_km": best_d}
    return None


# ---------------------------------------------------------------------------
# Data loading (bench-only)
# ---------------------------------------------------------------------------

def _load_governorates():
    """Load all Governorate rows as dicts (code/country/geo fields)."""
    if not _HAS_FRAPPE:
        raise RuntimeError("frappe is required to load Governorates")
    return frappe.db.get_all(
        GOVERNORATE_DOCTYPE,
        fields=["name", "code", "country", "latitude", "longitude", "bbox",
                PROVENANCE_FIELD, "source_dataset"],
    )


def _load_admin_boundary_geoms():
    """Load imported Admin Boundary level-1 geometries keyed by pcode.

    Returns ``{pcode: shapely_geometry}``. Admin Boundary geometries live in
    the ``geometries`` child table (Admin Boundary Geom); a conflict (duplicate
    pcode) is reported by omitting the key from the map and counted separately
    by the caller via the conflicting-match count.
    """
    if not _HAS_FRAPPE:
        raise RuntimeError("frappe is required to load Admin Boundary geoms")
    rows = frappe.db.get_all(
        ADMIN_BOUNDARY_DOCTYPE,
        fields=["name", "pcode", "country", "level"],
        filters={"level": 1},
    )
    geoms = {}
    for row in rows:
        pcode = normalize_code(row.get("pcode"))
        if pcode is None:
            continue
        geom_rows = frappe.db.get_all(
            ADMIN_BOUNDARY_GEOM_DOCTYPE,
            fields=["geometry"],
            filters={"parent": row["name"]},
        )
        for g in geom_rows:
            geom = _norm_geom(g.get("geometry"))
            if geom is not None and pcode not in geoms:
                geoms[pcode] = geom
    return geoms


def _load_natural_earth_features(scales=None):
    """Load Natural Earth admin-1 features for the available scales.

    Reuses the existing Natural Earth Vector API (``read_layer`` +
    ``available_scales``) -- no second provisioning implementation. Returns a
    list of dicts each carrying ``iso_3166_2``, ``iso_a2`` and a shapely
    ``geometry``. Scales are consumed finest-first; the finest available is
    preferred and a coarser scale never replaces it.
    """
    if not _HAS_FRAPPE:
        raise RuntimeError("frappe is required to load Natural Earth features")
    from siraj_research.api.natural_earth_vector import (
        available_scales,
        read_layer,
    )

    scales = scales or [s for s in NE_SCALE_ORDER if s in available_scales()]
    if not scales:
        return []
    # finest first: a code already seen at a finer scale is kept; a coarser
    # scale never replaces it.
    scales = sorted(scales, key=lambda s: NE_SCALE_ORDER.index(s)
                    if s in NE_SCALE_ORDER else 99)
    layer = "admin_1_states_provinces"
    features_by_code = {}
    for scale in scales:
        try:
            geojson = read_layer(layer, scale)
        except Exception:
            continue
        for feat in geojson.get("features", []):
            props = feat.get("properties", {})
            code = normalize_code(props.get("iso_3166_2"))
            if code is None or code in features_by_code:
                continue
            features_by_code[code] = {
                "iso_3166_2": props.get("iso_3166_2"),
                "iso_a2": props.get("iso_a2"),
                "geometry": _shapely_shape(feat["geometry"]),
            }
    return list(features_by_code.values())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def fill_governorate_geo(dry_run=False, scales=None, **_kwargs):
    """Execute the Governorate geo fill. Safe, idempotent, no ``commit()``.

    Args:
        dry_run: plan without writing any document (still returns the report).
        scales: optional Natural Earth scale list (finest-first); defaults to
            the available scales.
    """
    if not _HAS_FRAPPE:
        raise RuntimeError("fill_governorate_geo requires the Frappe bench")

    governorates = _load_governorates()
    imported_geoms = _load_admin_boundary_geoms()
    ne_features = _load_natural_earth_features(scales=scales)

    def _apply(code, updates):
        if not frappe.db.exists(GOVERNORATE_DOCTYPE, {"code": code}):
            return
        # Set only the computed fields on the existing Governorate document.
        # update_modified=False keeps the fill idempotent and does not touch
        # last_modified noise; no commit() is made here.
        frappe.db.set(
            GOVERNORATE_DOCTYPE, updates,
            filters={"code": code}, update_modified=False,
        )

    report = classify_and_fill(
        rows=governorates,
        imported_geoms=imported_geoms,
        ne_features=ne_features,
        dry_run=dry_run,
        apply=None if dry_run else _apply,
    )
    if dry_run:
        frappe.log_error(
            title="Governorate geo fill (dry run)",
            message=json.dumps(report, default=str),
        )
    return report
