"""End-to-end offline verification (no outbound network allowed).

``bench --site <site> geo verify-offline`` runs the checks below and prints a
single JSON report:

1. **Spatial backend** — PostGIS or the in-process Shapely/STRtree fallback.
2. **Dataset** — an active ``Boundary Dataset`` with polygons is configured.
3. **Tiles/assets** — a local tile cache or MBTiles pack exists, and the
   bundled Leaflet/MapLibre/D3 assets are present (no CDN ``<script src>``).
4. **Blocked network** — while :func:`outbound_network_blocked` patches socket
   creation for every non-loopback host, a coordinate is resolved through the
   same server path the Desk form uses. Any attempt to reach Nominatim, a tile
   server or any other host raises, so a passing check is real evidence of
   offline behaviour.
5. **Result** — the chain is non-empty and carries no ``online`` provenance.

The helper is also used by the integration test in
``tests/test_offline_verification.py`` (pure-Python parts only).
"""

from __future__ import annotations

import contextlib
import http.client
import socket
from collections.abc import Iterator
from pathlib import Path
from typing import Any

try:  # pragma: no cover - exercised inside a bench
    import frappe
except Exception:  # pragma: no cover - pure-Python tests
    frappe = None  # type: ignore[assignment]

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}
CDN_MARKERS = (
    "unpkg.com",
    "cdn.jsdelivr.net",
    "cdnjs.cloudflare.com",
    "fonts.googleapis.com",
    "fonts.gstatic.com",
    "tile.openstreetmap.org",
    "server.arcgisonline.com",
    "basemaps.cartocdn.com",
)
REQUIRED_ASSETS = (
    "public/vendor/leaflet/leaflet.js",
    "public/vendor/leaflet/leaflet.css",
    "public/vendor/leaflet/images/marker-icon.png",
    "public/vendor/maplibre-gl/maplibre-gl.js",
    "public/vendor/maplibre-gl/maplibre-gl.css",
    "public/vendor/d3/d3.min.js",
    "public/offline_map/index.html",
    "public/offline_map/viewer.js",
)
DEFAULT_POINT = (33.3152, 44.3661)  # Baghdad


@contextlib.contextmanager
def outbound_network_blocked() -> Iterator[None]:
    """Fail every new non-loopback TCP connection for the duration."""
    original_create = socket.create_connection
    original_connect = socket.socket.connect
    original_http = http.client.HTTPConnection.connect

    def _host(address: Any) -> str:
        if isinstance(address, tuple) and address:
            return str(address[0])
        return str(address)

    def create_connection(address, *args, **kwargs):
        if _host(address) in LOCAL_HOSTS:
            return original_create(address, *args, **kwargs)
        raise OSError(f"SIRAJ offline verification: outbound connection to {_host(address)} blocked")

    def connect(self, address):
        if _host(address) in LOCAL_HOSTS:
            return original_connect(self, address)
        raise OSError(f"SIRAJ offline verification: outbound connection to {_host(address)} blocked")

    def http_connect(self):
        if str(getattr(self, "host", "")) in LOCAL_HOSTS:
            return original_http(self)
        raise OSError(
            f"SIRAJ offline verification: HTTP connection to {getattr(self, 'host', '?')} blocked"
        )

    socket.create_connection = create_connection
    socket.socket.connect = connect
    http.client.HTTPConnection.connect = http_connect
    try:
        yield
    finally:
        socket.create_connection = original_create
        socket.socket.connect = original_connect
        http.client.HTTPConnection.connect = original_http


def _public_root() -> Path:
    return Path(__file__).resolve().parent / "public"


def asset_report() -> dict[str, Any]:
    """Check that every map asset is bundled locally and no CDN is referenced."""
    root = _public_root()
    missing = [rel for rel in REQUIRED_ASSETS if not (root.parent / rel).exists()]
    external_hits: list[dict[str, str]] = []
    scanned = 0
    for path in list(root.rglob("*.js")) + list(root.rglob("*.css")) + list(root.rglob("*.html")):
        if "vendor" in path.parts and path.name.upper().startswith("LICENSE"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:  # pragma: no cover
            continue
        scanned += 1
        lower = text.lower()
        for marker in CDN_MARKERS:
            if marker in lower:
                external_hits.append({"file": str(path.relative_to(root.parent)), "marker": marker})
                break
    total_bytes = sum(
        (root.parent / rel).stat().st_size for rel in REQUIRED_ASSETS if (root.parent / rel).exists()
    )
    return {
        "ok": not missing,
        "required": list(REQUIRED_ASSETS),
        "missing": missing,
        "files_scanned": scanned,
        "cdn_references": external_hits[:25],
        "cdn_reference_count": len(external_hits),
        "required_assets_bytes": total_bytes,
    }


def _dir_stats(path: Path) -> dict[str, Any]:
    files = 0
    total = 0
    if path.exists():
        for item in path.rglob("*"):
            if item.is_file():
                files += 1
                try:
                    total += item.stat().st_size
                except OSError:  # pragma: no cover
                    pass
    return {"path": str(path), "files": files, "bytes": total, "mb": round(total / (1024 * 1024), 2)}


def tile_report() -> dict[str, Any]:
    """Local tile cache and MBTiles packs, with their disk footprint."""
    if frappe is None:
        return {"ok": False, "reason": "frappe unavailable"}
    private = Path(frappe.get_site_path("private"))
    cache = _dir_stats(private / "siraj_tile_cache")
    packs_dir = private / "siraj_maps"
    packs = []
    if packs_dir.is_dir():
        for name in ("standard.mbtiles", "aerial.mbtiles"):
            path = packs_dir / name
            if path.is_file():
                packs.append({"name": name, "mb": round(path.stat().st_size / (1024 * 1024), 2)})
    return {
        "ok": cache["files"] > 0 or bool(packs),
        "cache": cache,
        "packs": packs,
        "note": "Tiles are served by /api/method/siraj_research.tile_cache.tile or "
                "siraj_research.local_maps.tile; both are same-origin and site-local.",
    }


def storage_report() -> dict[str, Any]:
    """Approximate disk footprint of boundaries, gazetteer and hierarchy rows."""
    if frappe is None:
        return {}
    report: dict[str, Any] = {}
    try:
        report["boundaries"] = frappe.db.sql(
            "SELECT COUNT(*), COALESCE(SUM(LENGTH(geom_wkb_hex))/2, 0) FROM `tabAdmin Boundary Geom`"
        )[0]
    except Exception:  # pragma: no cover
        report["boundaries"] = (0, 0)
    try:
        report["gazetteer"] = frappe.db.sql("SELECT COUNT(*) FROM `tabGazetteer Place`")[0][0]
    except Exception:  # pragma: no cover
        report["gazetteer"] = 0
    for doctype in ("Governorate", "District", "Municipality", "Village", "Community"):
        try:
            report[doctype] = frappe.db.count(doctype)
        except Exception:  # pragma: no cover
            report[doctype] = 0
    count, wkb_bytes = report.get("boundaries") or (0, 0)
    report["boundaries"] = {"rows": int(count or 0), "wkb_mb": round(float(wkb_bytes or 0) / (1024 * 1024), 2)}
    return report


def _backend() -> str:
    try:
        from siraj_research.api.geo_resolve import _spatial_backend

        return _spatial_backend()
    except Exception:  # pragma: no cover
        return "unknown"


def _settings() -> dict[str, Any]:
    if frappe is None:
        return {}
    try:
        s = frappe.get_single("Geo Settings")
        return {
            "dataset": s.active_boundary_dataset,
            "gazetteer": s.active_gazetteer_dataset,
            "online_enabled": bool(s.online_geocoder_enabled),
            "allow_tile_fetch": bool(s.allow_tile_fetch),
            "spatial_backend": s.spatial_backend,
        }
    except Exception:  # pragma: no cover
        return {}


def run(
    latitude: float = DEFAULT_POINT[0],
    longitude: float = DEFAULT_POINT[1],
    *,
    expect_levels: list[str] | None = None,
) -> dict[str, Any]:
    """Run every offline check and return a structured report."""
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: Any) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    settings = _settings()
    backend = _backend()
    add("spatial_backend", backend in ("postgis", "shapely"), {"backend": backend})
    add("dataset_configured", bool(settings.get("dataset")), settings)
    add("online_fallback_disabled", not settings.get("online_enabled"),
        {"online_geocoder_enabled": settings.get("online_enabled")})
    assets = asset_report()
    add("local_assets", assets["ok"], {"missing": assets["missing"], "cdn_hits": assets["cdn_reference_count"]})
    tiles = tile_report()
    add("local_tiles", tiles.get("ok", False), tiles)

    resolution: dict[str, Any] = {}
    error: str | None = None
    try:
        from siraj_research.geo_hierarchy_ui import display_resolution

        with outbound_network_blocked():
            resolution = display_resolution(latitude, longitude, create_missing=False, use_online=False)
    except Exception as exc:  # pragma: no cover - the interesting failure mode
        error = f"{type(exc).__name__}: {exc}"
    add("blocked_network_resolution", error is None and not resolution.get("error"),
        {"error": error or resolution.get("error")})
    resolved = [
        row for row in resolution.get("levels") or []
        if row.get("status") in ("linked", "resolved")
    ]
    add("chain_non_empty", bool(resolved),
        {row["field"]: row.get("label_en") for row in resolved})
    provenance = list(resolution.get("provenance") or [])
    add("no_online_provenance", "online_reverse_geocode" not in provenance, provenance)
    if expect_levels:
        got = {row["field"]: (row.get("label_en") or row.get("name")) for row in resolved}
        missing = [field for field in expect_levels if not got.get(field)]
        add("expected_levels", not missing, {"expected": expect_levels, "missing": missing, "got": got})

    return {
        "passed": all(check["ok"] for check in checks),
        "point": {"lat": latitude, "lon": longitude},
        "checks": checks,
        "resolution": {
            "text_en": resolution.get("text_en"),
            "text_ar": resolution.get("text_ar"),
            "deepest_level": resolution.get("deepest_level"),
            "warnings": resolution.get("warnings"),
            "provenance": provenance,
            "levels": [
                {
                    "field": row.get("field"),
                    "label_en": row.get("label_en"),
                    "label_ar": row.get("label_ar"),
                    "name": row.get("name"),
                    "status": row.get("status"),
                }
                for row in resolution.get("levels") or []
            ],
        },
        "assets": assets,
        "tiles": tiles,
        "storage": storage_report(),
        "settings": settings,
    }
