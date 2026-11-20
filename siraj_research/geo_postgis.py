"""PostGIS backend for offline reverse geocoding (primary spatial path).

Frappe v15 can run on either MariaDB or PostgreSQL. When the site is backed by
PostgreSQL **and** the PostGIS extension is installed, this module performs
point-in-polygon and distance lookups in the database:

* geometry is stored once per boundary in
  ``tabAdmin Boundary Geom.geom`` as ``geometry(Geometry, 4326)``;
* a GiST index makes ``ST_Contains``/``ST_DWithin`` millisecond queries even
  for country-sized datasets;
* every query is served from the local database — no network access at all.

When PostGIS is not available the resolver falls back to the in-process
Shapely ``STRtree`` implementation in :mod:`siraj_research.api.geo_resolve`.
Both backends return the same payload shape, so forms and the Explorer cannot
tell them apart except by the ``provenance`` entry.

Backfill
--------

Imported boundaries already carry WKB hex in ``Admin Boundary Geom``. Run::

    bench --site <site> geo postgis-init          # extension + column + index
    bench --site <site> geo postgis-backfill      # WKB hex → geometry
    bench --site <site> geo postgis-health        # counts + index check

``ensure_schema`` is idempotent and safe to run from a patch.

Dialect notes
-------------

* ``CREATE EXTENSION`` needs a database superuser (or a database where the
  extension is already installed). ``geo postgis-init`` reports a clear error
  instead of crashing when the privilege is missing.
* Identifiers use Frappe's backtick convention; Frappe's PostgreSQL layer
  converts them to double quotes (``frappe.database.utils``
  ``convert_backtick_identifiers``), so the same SQL text is safe on both
  engines. The PostGIS-specific statements are only ever executed after
  :func:`is_postgres` returns true.
* ``::geography`` casts are used for metre-accurate distances; SRID 4326 is
  enforced on insert/backfill.
"""

from __future__ import annotations

from typing import Any

try:  # pragma: no cover - exercised inside a bench
    import frappe
except Exception:  # pragma: no cover - pure-Python tests
    frappe = None  # type: ignore[assignment]

GEOM_TABLE = "tabAdmin Boundary Geom"
BOUNDARY_TABLE = "tabAdmin Boundary"
GEOM_COLUMN = "geom"
GEOM_INDEX = "idx_siraj_admin_boundary_geom"
CACHE_TTL_VERSION_FIELD = "index_version"

_INDEX_CACHE: dict[str, dict[str, Any]] = {}
_AVAILABILITY: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Dialect / availability
# ---------------------------------------------------------------------------

def db_type() -> str:
    """Return ``postgres`` or ``mariadb`` (Frappe's own configuration value)."""
    if frappe is None:
        return "none"
    try:
        return str(getattr(frappe.conf, "db_type", None) or "mariadb").lower()
    except Exception:  # pragma: no cover
        return "mariadb"


def is_postgres() -> bool:
    return db_type() in ("postgres", "postgresql")


def _sql(query: str, values: Any = None, **kwargs):
    if frappe is None:
        return []
    return frappe.db.sql(query, values, **kwargs)


def available(refresh: bool = False) -> bool:
    """True when PostgreSQL + the PostGIS extension are usable right now."""
    if frappe is None or not is_postgres():
        return False
    if not refresh and "available" in _AVAILABILITY:
        return bool(_AVAILABILITY["available"])
    try:
        rows = _sql("SELECT extversion FROM pg_extension WHERE extname = 'postgis'")
        _AVAILABILITY["available"] = bool(rows)
        _AVAILABILITY["version"] = rows[0][0] if rows else None
    except Exception:  # pragma: no cover - permission or transient DB error
        _AVAILABILITY["available"] = False
    return bool(_AVAILABILITY["available"])


def version() -> str | None:
    if not available():
        return None
    try:
        rows = _sql("SELECT postgis_version()")
        return row0(rows)
    except Exception:  # pragma: no cover
        return _AVAILABILITY.get("version")


def row0(rows) -> Any:
    if not rows:
        return None
    row = rows[0]
    return row[0] if isinstance(row, list | tuple) else row


# ---------------------------------------------------------------------------
# Schema management
# ---------------------------------------------------------------------------

def ensure_extension() -> dict[str, Any]:
    """Install PostGIS if the connecting role may do so (idempotent)."""
    if not is_postgres():
        return {"ok": False, "reason": "not_postgres", "db_type": db_type()}
    try:
        _sql("CREATE EXTENSION IF NOT EXISTS postgis")
        _AVAILABILITY.clear()
        return {"ok": available(refresh=True), "version": version()}
    except Exception as exc:
        return {
            "ok": False,
            "reason": "create_extension_failed",
            "error": str(exc),
            "hint": "Run as a superuser: psql -d <db> -c 'CREATE EXTENSION postgis;'",
        }


def _column_exists() -> bool:
    rows = _sql(
        """SELECT 1 FROM information_schema.columns
           WHERE table_name = %s AND column_name = %s""",
        (GEOM_TABLE, GEOM_COLUMN),
    )
    return bool(rows)


def _index_exists() -> bool:
    rows = _sql("SELECT 1 FROM pg_indexes WHERE indexname = %s", (GEOM_INDEX,))
    return bool(rows)


def ensure_schema() -> dict[str, Any]:
    """Create the geometry column and its GiST index (idempotent)."""
    if not available():
        return {"ok": False, "reason": "postgis_unavailable"}
    created_column = created_index = False
    if not _column_exists():
        _sql(f"ALTER TABLE `{GEOM_TABLE}` ADD COLUMN {GEOM_COLUMN} geometry(Geometry, 4326)")
        created_column = True
    if not _index_exists():
        _sql(
            f"CREATE INDEX {GEOM_INDEX} ON `{GEOM_TABLE}` USING GIST ({GEOM_COLUMN})"
        )
        created_index = True
    return {
        "ok": True,
        "created_column": created_column,
        "created_index": created_index,
        "column_exists": _column_exists(),
        "index_exists": _index_exists(),
    }


def geometry_stats(dataset: str | None = None) -> dict[str, Any]:
    """Counts used by health checks and the documentation footprint table."""
    if not available():
        return {"ok": False, "reason": "postgis_unavailable"}
    where = " WHERE ab.dataset = %s" if dataset else ""
    values = (dataset,) if dataset else None
    rows = _sql(
        f"""SELECT COUNT(*),
                   COUNT(g.{GEOM_COLUMN}),
                   COALESCE(SUM(pg_total_relation_size('{GEOM_TABLE}')), 0)
            FROM `{BOUNDARY_TABLE}` ab
            LEFT JOIN `{GEOM_TABLE}` g
              ON g.parent = ab.name AND g.`precision` = 'full'
            {where}""",
        values,
    )
    row = rows[0] if rows else (0, 0, 0)
    return {
        "ok": True,
        "dataset": dataset,
        "boundaries": int(row[0] or 0),
        "with_geometry": int(row[1] or 0),
        "table_bytes": int(row[2] or 0),
    }


def backfill_geometries(dataset: str | None = None, batch_size: int = 500) -> dict[str, Any]:
    """Copy ``geom_wkb_hex`` into the PostGIS column for rows that lack it.

    Chunked ``UPDATE … FROM (… LIMIT n)`` keeps transactions short on large
    datasets; each chunk commits, so an interrupted run resumes where it
    stopped. Re-running is a no-op once every row has a geometry.
    """
    if not available():
        return {"ok": False, "reason": "postgis_unavailable"}
    ensure_schema()
    total = 0
    chunks = 0
    limit = max(1, int(batch_size))
    dataset_clause = ""
    values_extra: tuple = ()
    if dataset:
        dataset_clause = (
            " AND EXISTS (SELECT 1 FROM `tabAdmin Boundary` ab "
            "WHERE ab.name = g.parent AND ab.dataset = %s)"
        )
        values_extra = (dataset,)
    while True:
        params: tuple = (*values_extra, limit)
        rows = _sql(
            f"""WITH batch AS (
                    SELECT g.name
                    FROM `{GEOM_TABLE}` g
                    WHERE g.{GEOM_COLUMN} IS NULL
                      AND g.geom_wkb_hex IS NOT NULL
                      AND length(g.geom_wkb_hex) > 20
                      {dataset_clause}
                    LIMIT %s
                )
                UPDATE `{GEOM_TABLE}` g
                SET {GEOM_COLUMN} = ST_GeomFromWKB(decode(g.geom_wkb_hex, 'hex'), 4326)
                FROM batch
                WHERE g.name = batch.name
                RETURNING g.name""",
            params,
        )
        updated = len(rows or [])
        total += updated
        chunks += 1
        frappe.db.commit()
        if updated == 0:
            break
        if chunks > 100000:  # pragma: no cover - runaway guard
            break
    invalidate_cache()
    return {
        "ok": True,
        "updated": total,
        "chunks": chunks - 1 if total == 0 else chunks,
        "stats": geometry_stats(dataset),
    }


def health() -> dict[str, Any]:
    """One dict suitable for ``bench geo postgis-health``."""
    report: dict[str, Any] = {
        "db_type": db_type(),
        "is_postgres": is_postgres(),
        "postgis_available": available(refresh=True),
        "postgis_version": version(),
    }
    if report["postgis_available"]:
        report["column_exists"] = _column_exists()
        report["index_exists"] = _index_exists()
        report["stats"] = geometry_stats()
    else:
        report["hint"] = (
            "PostGIS is optional; the Shapely/STRtree resolver is used instead. "
            "See docs/geographic-hierarchy/01-installation.md."
        )
    return report


# ---------------------------------------------------------------------------
# Dataset index cache (portable, used for parent_pcode walking)
# ---------------------------------------------------------------------------

def _dataset_version(dataset: str) -> int:
    try:
        return int(frappe.db.get_value("Boundary Dataset", dataset, CACHE_TTL_VERSION_FIELD) or 0)
    except Exception:  # pragma: no cover
        return 0


def dataset_index(dataset: str) -> dict[str, Any]:
    """Cache the lightweight boundary rows for a dataset (name/pcode/level/…)."""
    if frappe is None or not dataset:
        return {"records": [], "by_pcode": {}, "by_level": {}}
    key = f"{dataset}:{_dataset_version(dataset)}"
    cached = _INDEX_CACHE.get(key)
    if cached is not None:
        return cached
    rows = frappe.get_all(
        "Admin Boundary",
        filters={"dataset": dataset},
        fields=[
            "name", "pcode", "source_id", "level", "name_en", "name_ar", "country",
            "parent_pcode", "centroid_lat", "centroid_lon", "bbox",
        ],
        limit_page_length=0,
    )
    by_pcode: dict[str, dict] = {}
    by_level: dict[int, list[dict]] = {}
    for row in rows:
        record = dict(row)
        try:
            record["level"] = int(record.get("level") or 0)
        except (TypeError, ValueError):
            record["level"] = 0
        code = str(record.get("pcode") or record.get("source_id") or "").strip().upper()
        if code:
            by_pcode[code] = record
        by_level.setdefault(record["level"], []).append(record)
    payload = {"records": rows, "by_pcode": by_pcode, "by_level": by_level, "version": key}
    _INDEX_CACHE[key] = payload
    return payload


def invalidate_cache() -> None:
    _INDEX_CACHE.clear()
    _AVAILABILITY.clear()
    _GEOM_READY.clear()


_GEOM_READY: dict[str, bool] = {}


def has_geometry(dataset: str) -> bool:
    """Cheap, cached check that a dataset has PostGIS geometries."""
    if not available() or not dataset:
        return False
    key = f"{dataset}:{_dataset_version(dataset)}"
    if key in _GEOM_READY:
        return _GEOM_READY[key]
    try:
        rows = _sql(
            f"""SELECT 1 FROM `{BOUNDARY_TABLE}` ab
                JOIN `{GEOM_TABLE}` g
                  ON g.parent = ab.name AND g.`precision` = 'full'
                WHERE ab.dataset = %s AND g.{GEOM_COLUMN} IS NOT NULL
                LIMIT 1""",
            (dataset,),
        )
        _GEOM_READY[key] = bool(rows)
    except Exception:  # pragma: no cover - schema absent
        _GEOM_READY[key] = False
    return _GEOM_READY[key]


# ---------------------------------------------------------------------------
# Point resolution
# ---------------------------------------------------------------------------

_CHAIN_FIELDS = ("country", "governorate", "district", "municipality", "village", "community")


def _chain_from_matches(matches: dict[int, dict], index: dict[str, Any]) -> dict[str, dict]:
    """Build the chain from the finest match, walking ``parent_pcode``."""
    if not matches:
        return {}
    finest = max(matches)
    record = matches[finest]
    chain: dict[str, dict] = {}
    seen: set[str] = set()
    while record:
        level = int(record.get("level") or 0)
        if 0 <= level < len(_CHAIN_FIELDS):
            field = _CHAIN_FIELDS[level]
            chain.setdefault(
                field,
                {
                    "pcode": record.get("pcode") or record.get("source_id"),
                    "name_en": record.get("name_en"),
                    "name_ar": record.get("name_ar"),
                    "level": level,
                    "boundary": record.get("name"),
                    "bbox": record.get("bbox"),
                    "country": record.get("country"),
                },
            )
        parent = str(record.get("parent_pcode") or "").strip().upper()
        if not parent or parent in seen:
            break
        seen.add(parent)
        record = index.get("by_pcode", {}).get(parent)
    # Fill lower levels from independent matches when parent codes were absent.
    for level, match in matches.items():
        field = _CHAIN_FIELDS[level]
        if field not in chain:
            chain[field] = {
                "pcode": match.get("pcode") or match.get("source_id"),
                "name_en": match.get("name_en"),
                "name_ar": match.get("name_ar"),
                "level": level,
                "boundary": match.get("name"),
                "bbox": match.get("bbox"),
                "country": match.get("country"),
            }
    if "country" not in chain:
        country = (matches[max(matches)] or {}).get("country")
        if country:
            chain["country"] = {"pcode": None, "name_en": country, "name_ar": None, "level": 0}
    return chain


def resolve_point(
    lat: float,
    lon: float,
    dataset: str,
    tolerance_m: float = 50.0,
    sea_gap_m: float = 5000.0,
) -> dict[str, Any] | None:
    """Resolve a point using PostGIS. ``None`` means "backend not usable".

    The returned mapping matches the pieces of
    :func:`siraj_research.api.geo_resolve._resolve_one` it owns:
    ``on_land``, ``admin_chain``, ``ambiguous``, ``candidates``,
    ``nearest_boundary_m``, ``warnings``, ``provenance``.
    """
    if not has_geometry(dataset):
        return None

    try:
        rows = _sql(
            f"""SELECT ab.name, ab.pcode, ab.source_id, ab.level, ab.parent_pcode,
                       ab.name_en, ab.name_ar, ab.country, ab.bbox,
                       ST_Area(g.{GEOM_COLUMN}::geography) AS area_m2
                FROM `{BOUNDARY_TABLE}` ab
                JOIN `{GEOM_TABLE}` g
                  ON g.parent = ab.name AND g.`precision` = 'full'
                WHERE ab.dataset = %s
                  AND g.{GEOM_COLUMN} IS NOT NULL
                  AND ST_Contains(g.{GEOM_COLUMN}, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                ORDER BY ab.level ASC, area_m2 ASC""",
            (dataset, lon, lat),
            as_dict=True,
        )
    except Exception:  # pragma: no cover - malformed geometry / permissions
        return None

    warnings: list[str] = []
    matches: dict[int, dict] = {}
    duplicates: set[int] = set()
    for row in rows or []:
        level = int(row.get("level") or 0)
        if level in matches:
            duplicates.add(level)
            continue
        matches[level] = dict(row)
    if rows:
        result: dict[str, Any] = {
            "on_land": True,
            "admin_chain": _chain_from_matches(matches, dataset_index(dataset)),
            "ambiguous": bool(duplicates),
            "candidates": [
                {
                    "level": int(row.get("level") or 0),
                    "pcode": row.get("pcode"),
                    "name_en": row.get("name_en"),
                    "reason": "overlapping_polygon",
                }
                for row in rows
                if int(row.get("level") or 0) in duplicates
            ],
            "nearest_boundary_m": 0.0,
            "warnings": warnings,
            "provenance": ["postgis_containment"],
        }
        if duplicates:
            warnings.append("boundary_ambiguity")
        return result

    # No polygon contains the point: measure the distance to the nearest one to
    # distinguish "just offshore" from "no data at all".
    nearest_m: float | None = None
    try:
        nearest_rows = _sql(
            f"""SELECT MIN(ST_Distance(g.{GEOM_COLUMN}::geography,
                                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography)) AS distance_m
                FROM `{BOUNDARY_TABLE}` ab
                JOIN `{GEOM_TABLE}` g
                  ON g.parent = ab.name AND g.`precision` = 'full'
                WHERE ab.dataset = %s AND g.{GEOM_COLUMN} IS NOT NULL""",
            (lon, lat, dataset),
            as_dict=True,
        )
        if nearest_rows:
            nearest_m = float(nearest_rows[0].get("distance_m") or 0.0)
    except Exception:  # pragma: no cover
        nearest_m = None
    if nearest_m is not None and nearest_m > sea_gap_m:
        warnings.append("over_water_or_no_data")
    else:
        warnings.append("near_boundary")
    return {
        "on_land": False,
        "admin_chain": {},
        "ambiguous": False,
        "candidates": [],
        "nearest_boundary_m": round(nearest_m, 1) if nearest_m is not None else None,
        "warnings": warnings,
        "provenance": ["postgis_nearest"],
    }


def benchmark(
    dataset: str | None = None,
    *,
    points: list[tuple[float, float]] | None = None,
    repeats: int = 20,
) -> dict[str, Any]:
    """Time local resolution for a handful of points (target: < 200 ms)."""
    import time

    if frappe is None:
        return {"error": "frappe unavailable"}
    if not available():
        return {"error": "postgis_unavailable", "health": health()}
    if not dataset:
        dataset = frappe.db.get_single_value("Geo Settings", "active_boundary_dataset")
    if not dataset:
        return {"error": "no_active_dataset"}
    points = points or [(33.3152, 44.3661), (30.5081, 47.7835), (36.3350, 43.1189)]
    samples: list[float] = []
    for _ in range(max(1, int(repeats))):
        for lat, lon in points:
            started = time.perf_counter()
            resolve_point(lat, lon, dataset)
            samples.append((time.perf_counter() - started) * 1000.0)
    samples.sort()
    return {
        "dataset": dataset,
        "queries": len(samples),
        "points": points,
        "median_ms": round(samples[len(samples) // 2], 2),
        "p95_ms": round(samples[int(len(samples) * 0.95) - 1], 2),
        "max_ms": round(samples[-1], 2),
        "target_ms": 200,
        "passed": samples[int(len(samples) * 0.95) - 1] < 200,
        "backend": "postgis",
    }
