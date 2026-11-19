"""One-shot, online-to-offline bootstrap for a SIRAJ bench.

Run ``prepare_offline_site`` once while the bench still has internet. It
downloads wheels, pre-caches map tiles for the active boundary dataset,
materialises hierarchy records, exports the browser package, then locks the
site into permanent offline mode. No later operation needs an external host.
"""
from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

try:  # pragma: no cover - exercised inside a bench
    import frappe
except Exception:  # pragma: no cover - pure tests
    frappe = None

try:  # pragma: no cover - pure tests use only the math helpers
    from siraj_research import tile_cache
except Exception:  # pragma: no cover
    tile_cache = None


DEFAULT_BBOX = (29.4, 34.2, 33.4, 35.9)  # Israel + Palestine (lat_min, lon_min, lat_max, lon_max)
OFFLINE_LAYERS = ("standard", "aerial", "hybrid", "hybrid_labels")


def dataset_bbox(dataset: str | None) -> tuple[float, float, float, float]:
    """Return (lat_min, lon_min, lat_max, lon_max) for a boundary dataset."""
    if frappe is None:
        return DEFAULT_BBOX
    row = frappe.db.sql(
        """SELECT MIN(centroid_lat) AS lat_min, MIN(centroid_lon) AS lon_min,
                  MAX(centroid_lat) AS lat_max, MAX(centroid_lon) AS lon_max
           FROM `tabAdmin Boundary`
           WHERE dataset=%s AND centroid_lat IS NOT NULL AND centroid_lon IS NOT NULL""",
        (dataset,) if dataset else (),
        as_dict=True,
    )
    if not row or not row[0]:
        return DEFAULT_BBOX
    r = row[0]
    try:
        values = (float(r.lat_min), float(r.lon_min), float(r.lat_max), float(r.lon_max))
        if all(math.isfinite(v) for v in values) and values[0] <= values[2] and values[1] <= values[3]:
            return values
    except (TypeError, ValueError):
        pass
    return DEFAULT_BBOX


def _lon_to_x(lon: float, z: int) -> int:
    n = 2 ** z
    return max(0, min(n - 1, int((lon + 180.0) / 360.0 * n)))


def _lat_to_y(lat: float, z: int) -> int:
    n = 2 ** z
    lat = max(-85.05112878, min(85.05112878, lat))
    value = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return max(0, min(n - 1, int(value)))


def tile_range(bbox: tuple[float, float, float, float], z: int):
    lat_min, lon_min, lat_max, lon_max = bbox
    x0, x1 = _lon_to_x(lon_min, z), _lon_to_x(lon_max, z)
    y0, y1 = _lat_to_y(lat_max, z), _lat_to_y(lat_min, z)
    return range(x0, x1 + 1), range(y0, y1 + 1)


def download_python_wheels(target_dir: str | Path | None = None) -> dict:
    """Download pinned optional dependencies into a local wheel directory."""
    app = Path(frappe.get_app_path("siraj_research")) if frappe else Path(__file__).resolve().parent
    requirements = app / "requirements-offline.txt"
    target = Path(target_dir) if target_dir else (Path(frappe.get_site_path("private")) if frappe else app) / "offline-cache" / "wheels"
    target.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "download", "--dest", str(target), "-r", str(requirements)],
        capture_output=True, text=True, check=False,
    )
    return {
        "ok": proc.returncode == 0,
        "target": str(target),
        "wheels": len(list(target.glob("*.whl"))),
        "stderr": proc.stderr[-1000:],
    }


def prewarm_tiles(dataset: str | None = None, max_zoom: int = 11,
                  layers: tuple[str, ...] = OFFLINE_LAYERS) -> dict:
    """Fetch and cache every tile covering ``dataset`` for offline reuse."""
    if frappe is None:
        return {"error": "bench required", "written": 0}
    s = tile_cache._settings()
    previous = bool(s.allow_fetch)
    frappe.db.set_value("Geo Settings", "Geo Settings", "allow_tile_fetch", 1,
                        update_modified=False)
    bbox = dataset_bbox(dataset)
    written = 0
    skipped = 0
    try:
        for layer in layers:
            base, variant = tile_cache._resolve_layer(layer, s)
            spec = tile_cache.LAYERS[base]
            ext = spec["ext"]
            variant_key = "base" if variant == "base" else "overlay"
            if spec.get("needs_date") and variant == "base":
                import datetime as _dt
                variant_key = s.get(spec.get("date_field", ""), "") or _dt.datetime.utcnow().strftime("%Y-%m-%d")
            for z in range(int(spec.get("min_zoom", 0)), min(int(max_zoom), int(spec.get("max_zoom", 22))) + 1):
                xs, ys = tile_range(bbox, z)
                url_tpl = tile_cache._resolve_url(spec, s, variant, z)
                for x in xs:
                    for y in ys:
                        path = tile_cache._cache_path(base, z, x, y, ext, variant_key)
                        if path.is_file():
                            skipped += 1
                            continue
                        url = url_tpl.replace("{x}", str(x)).replace("{y}", str(y))
                        try:
                            data = tile_cache._fetch(url, spec["user_agent"])
                        except Exception:
                            skipped += 1
                            continue
                        path.parent.mkdir(parents=True, exist_ok=True)
                        tmp = path.with_suffix(path.suffix + ".tmp")
                        tmp.write_bytes(data)
                        tmp.replace(path)
                        written += 1
    finally:
        frappe.db.set_value("Geo Settings", "Geo Settings", "allow_tile_fetch", int(previous),
                            update_modified=False)
        frappe.db.commit()
    return {"bbox": bbox, "written": written, "skipped": skipped,
            "layers": list(layers), "max_zoom": int(max_zoom)}


def lock_offline_mode() -> dict:
    """Permanently stop external network calls from the live site."""
    if frappe is None:
        return {"error": "bench required"}
    values = {
        "allow_tile_fetch": 0,
        "online_geocoder_enabled": 0,
    }
    for field, value in values.items():
        frappe.db.set_value("Geo Settings", "Geo Settings", field, value, update_modified=False)
    frappe.db.commit()
    return values


def prepare_offline_site(dataset: str | None = None, max_zoom: int = 11,
                         wheels: bool = True, tiles: bool = True,
                         hierarchy: bool = True, package: bool = True,
                         lock: bool = True) -> dict:
    """Run every download while online, then lock the site offline."""
    if frappe is None:
        return {"error": "bench required"}
    cfg = frappe.get_single("Geo Settings")
    dataset = dataset or getattr(cfg, "active_boundary_dataset", None)
    if not dataset:
        return {"error": "No active boundary dataset"}
    result: dict = {"dataset": dataset}
    if wheels:
        result["wheels"] = download_python_wheels()
    if tiles:
        result["tiles"] = prewarm_tiles(dataset, max_zoom=max_zoom)
    if hierarchy:
        from siraj_research.geo_hierarchy import sync_boundary_hierarchy
        result["hierarchy"] = sync_boundary_hierarchy(dataset, create_missing=True)
    if package:
        from siraj_research.api.geo_package import export_offline_package
        result["package"] = export_offline_package()
    if lock:
        result["locked"] = lock_offline_mode()
    return result
