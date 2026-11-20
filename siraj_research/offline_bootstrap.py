"""One-shot, online-to-offline bootstrap for a SIRAJ bench.

Run ``prepare_offline_site`` once while the bench still has internet. It
downloads wheels, pre-caches map tiles for the active boundary dataset,
materialises hierarchy records, exports the browser package, then locks the
site into permanent offline mode. No later operation needs an external host.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import subprocess
import sys
import time
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

def progress_path() -> Path | None:
    if frappe is None:
        return None
    return Path(frappe.get_site_path("private", "offline-cache", "bootstrap-progress.json"))


def emit(stage: str, message: str, **extra) -> None:
    """Report progress immediately to the terminal and a tail-able file."""
    record = {"at": dt.datetime.now().isoformat(timespec="seconds"),
              "stage": stage, "message": message, **extra}
    line = json.dumps(record, ensure_ascii=False, default=str)
    try:
        print(f"[SIRAJ offline] {stage}: {message}", flush=True)
    except Exception:
        pass
    try:
        path = progress_path()
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
    except Exception:
        pass



class BootstrapStopped(RuntimeError):
    """Raised when an administrator requests a cooperative stop."""


def _settings_value(field: str):
    if frappe is None:
        return None
    return frappe.db.get_value("Geo Settings", "Geo Settings", field)


def stop_requested() -> bool:
    """True when Geo Settings → Stop requested has been checked."""
    if frappe is None:
        return False
    from frappe.utils import cint
    return bool(cint(_settings_value("bootstrap_stop_requested")))


def check_stop(stage: str) -> None:
    """Abort at a safe point if the administrator pressed Stop."""
    if stop_requested():
        emit(stage, "STOP requested from Geo Settings", level="warning")
        raise BootstrapStopped("Stopped by administrator from Geo Settings")


def _set_status(**values) -> None:
    if frappe is None:
        return
    for field, value in values.items():
        frappe.db.set_value("Geo Settings", "Geo Settings", field, value,
                            update_modified=False)
    frappe.db.commit()


if frappe is not None:  # pragma: no cover - bench only
    @frappe.whitelist()
    def request_stop():
        """Set the cooperative stop flag from the Geo Settings button."""
        _set_status(bootstrap_stop_requested=1,
                    bootstrap_last_status="stop requested")
        emit("stop", "Stop requested from Geo Settings")
        return {"stop_requested": True}

    @frappe.whitelist()
    def clear_stop():
        """Clear the stop flag before a new bootstrap run."""
        _set_status(bootstrap_stop_requested=0)
        return {"stop_requested": False}


def _step(stage: str, fn, **kwargs) -> dict:
	"""Run one bootstrap stage without aborting the remaining stages."""
	emit(stage, "starting")
	try:
		check_stop(stage)
		result = fn(**kwargs)
	except BootstrapStopped:
		raise
	except Exception as exc:
		emit(stage, f"FAILED: {exc}")
		return {"error": f"{type(exc).__name__}: {exc}"}
	emit(stage, "finished")
	return result


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
    emit("wheels", f"Downloading requirements to {target}", requirements=str(requirements))
    check_stop("wheels")
    cmd = [sys.executable, "-m", "pip", "download", "--dest", str(target), "-r", str(requirements)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    while proc.poll() is None:
        if stop_requested():
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
            check_stop("wheels")  # raises BootstrapStopped
        time.sleep(0.25)
    stdout, stderr = proc.communicate()
    count = len(list(target.glob("*.whl")))
    already_cached = proc.returncode != 0 and count > 0
    ok = proc.returncode == 0 or already_cached
    state = "complete" if proc.returncode == 0 else ("already available offline" if already_cached else "FAILED")
    emit("wheels", f"Wheel download {state}: {count} files", ok=ok, count=count)
    return {
        "ok": ok,
        "download_ok": proc.returncode == 0,
        "already_cached": already_cached,
        "target": str(target),
        "wheels": count,
        "stderr": (stderr or "")[-1000:],
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
    cached = 0
    failed = 0
    emit("tiles", f"Starting tile download for {dataset or 'active dataset'}", bbox=bbox, layers=list(layers))
    try:
        for layer in layers:
            emit("tiles", f"Layer {layer}: starting")
            base, variant = tile_cache._resolve_layer(layer, s)
            spec = tile_cache.LAYERS[base]
            ext = spec["ext"]
            variant_key = "base" if variant == "base" else "overlay"
            if spec.get("needs_date") and variant == "base":
                import datetime as _dt
                variant_key = s.get(spec.get("date_field", ""), "") or _dt.datetime.utcnow().strftime("%Y-%m-%d")
            for z in range(int(spec.get("min_zoom", 0)), min(int(max_zoom), int(spec.get("max_zoom", 22))) + 1):
                check_stop("tiles")
                xs, ys = tile_range(bbox, z)
                total = len(xs) * len(ys)
                emit("tiles", f"Layer {layer} zoom {z}: {total} tiles")
                url_tpl = tile_cache._resolve_url(spec, s, variant, z)
                layer_written = 0
                layer_cached = 0
                layer_failed = 0
                checked = 0
                for x in xs:
                    for y in ys:
                        if checked % 32 == 0:
                            check_stop("tiles")
                        checked += 1
                        path = tile_cache._cache_path(base, z, x, y, ext, variant_key)
                        if path.is_file():
                            cached += 1
                            layer_cached += 1
                            continue
                        url = url_tpl.replace("{x}", str(x)).replace("{y}", str(y))
                        try:
                            data = tile_cache._fetch(url, spec["user_agent"])
                        except Exception:
                            failed += 1
                            layer_failed += 1
                            continue
                        path.parent.mkdir(parents=True, exist_ok=True)
                        tmp = path.with_suffix(path.suffix + ".tmp")
                        tmp.write_bytes(data)
                        tmp.replace(path)
                        written += 1
                        layer_written += 1
                emit("tiles",
                     f"Layer {layer} zoom {z}: done ({layer_written} written, "
                     f"{layer_cached} cached, {layer_failed} failed)",
                     written=layer_written, cached=layer_cached, failed=layer_failed)
                if layer_failed:
                    emit("tiles", f"Layer {layer} zoom {z}: {layer_failed} tiles failed - "
                                  "run while online to complete the cache", level="warning")
            emit("tiles", f"Layer {layer}: complete")
    finally:
        frappe.db.set_value("Geo Settings", "Geo Settings", "allow_tile_fetch", int(previous),
                            update_modified=False)
        frappe.db.commit()
    emit("tiles", f"Tile pass finished ({written} written, {cached} cached, {failed} failed)",
         written=written, cached=cached, failed=failed, level="warning" if failed else "info")
    return {"bbox": bbox, "written": written, "cached": cached, "failed": failed,
            "ok": failed == 0, "layers": list(layers), "max_zoom": int(max_zoom)}


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
    emit("lock", "External network calls disabled", values=values)
    return values


def prepare_offline_site(dataset: str | None = None, max_zoom: int = 11,
                         wheels: bool = True, tiles: bool = True,
                         hierarchy: bool = True, package: bool = True,
                         lock: bool = True, force_lock: bool = False) -> dict:
    """Run every download while online, then lock the site offline.

    The Geo Settings → Stop Offline Bootstrap button sets a cooperative stop
    flag. The run checks it between stages and every 32 tiles, so a long tile
    sweep can be halted without leaving the site half-locked.
    """
    if frappe is None:
        return {"error": "bench required"}
    cfg = frappe.get_single("Geo Settings")
    dataset = dataset or getattr(cfg, "active_boundary_dataset", None)
    if not dataset:
        return {"error": "No active boundary dataset"}
    _set_status(bootstrap_stop_requested=0, bootstrap_running=1,
                bootstrap_last_status="running")
    emit("start", f"Offline bootstrap started for {dataset}", max_zoom=max_zoom)
    result: dict = {"dataset": dataset, "stopped": False}
    try:
        if wheels:
            result["wheels"] = _step("wheels", download_python_wheels)
        if tiles:
            result["tiles"] = _step("tiles", prewarm_tiles,
                                    dataset=dataset, max_zoom=max_zoom)
        if hierarchy:
            from siraj_research.geo_bulk import sync_boundary_hierarchy
            result["hierarchy"] = _step(
                "hierarchy", sync_boundary_hierarchy,
                dataset_code=dataset, create_missing=True)
        if package:
            from siraj_research.api.geo_package import export_offline_package
            result["package"] = _step("package", export_offline_package)
        incomplete = (
            (wheels and not result.get("wheels", {}).get("ok", False))
            or (tiles and not result.get("tiles", {}).get("ok", False))
        )
        if lock and incomplete and not force_lock:
            emit("lock", "Skipping offline lock: downloads were incomplete; rerun while online "
                         "or pass force_lock=True", level="warning")
            result["locked"] = {"skipped": "incomplete_downloads"}
        elif lock:
            result["locked"] = _step("lock", lock_offline_mode)
        emit("done", "Offline bootstrap complete", dataset=dataset, complete=not incomplete)
        _set_status(bootstrap_last_status="complete" if not incomplete else "complete_with_failures")
    except BootstrapStopped as exc:
        result["stopped"] = True
        emit("stopped", str(exc), level="warning")
        _set_status(bootstrap_last_status="stopped by user")
    finally:
        _set_status(bootstrap_running=0)
    return result
