"""Server-side cached tile proxy.

Proxies raster tiles for the configured standard/aerial/hybrid basemaps,
caching them to disk so subsequent requests never re-hit the external
provider and the server can continue serving tiles even when it is
offline from the internet (once a tile has been fetched once). All
client-side tile traffic goes through this endpoint — browsers never
contact tile.openstreetmap.org or server.arcgisonline.com directly.

Layers are administrator-configured in Geo Settings (default layer +
which layers are enabled). End users do not see a basemap switcher.
"""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from urllib.request import Request, urlopen

import frappe
from frappe.rate_limiter import rate_limit
from werkzeug.wrappers import Response

# Layer definitions. URL templates use {z}/{x}/{y} (XYZ / Google schema,
# which Esri also uses — TMS y-flip is not needed here). Attributions are
# forwarded verbatim to the client so they appear on every map.
LAYERS = {
    "standard": {
        "label": "Standard (OpenStreetMap)",
        "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "attribution": "&copy; <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a> contributors",
        "content_type": "image/png",
        "ext": "png",
        "max_zoom": 19,
        "user_agent": "SIRAJ-Research/1.0 (+https://github.com/josuecano22222-rgb/Siraj-Research)",
    },
    "aerial": {
        "label": "Aerial (Esri World Imagery)",
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attribution": "Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community",
        "content_type": "image/jpeg",
        "ext": "jpg",
        "max_zoom": 19,
        "user_agent": "SIRAJ-Research/1.0",
    },
    "hybrid": {
        "label": "Hybrid (Aerial + Labels)",
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "overlay_url": "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
        "attribution": "Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community",
        "content_type": "image/jpeg",
        "ext": "jpg",
        "max_zoom": 19,
        "user_agent": "SIRAJ-Research/1.0",
    },
}

_COORD = re.compile(r"^[0-9]{1,10}$")
_DEFAULT_CACHE_DAYS = 90
_HTTP_TIMEOUT = 8
_MAX_TILE_BYTES = 1024 * 1024  # 1 MiB


def _settings():
    s = frappe.get_single("Geo Settings")
    return frappe._dict({
        "enable_standard": bool(getattr(s, "enable_standard_layer", 1)),
        "enable_aerial":   bool(getattr(s, "enable_aerial_layer", 1)),
        "enable_hybrid":   bool(getattr(s, "enable_hybrid_layer", 0)),
        "default_layer":   getattr(s, "default_tile_layer", "standard") or "standard",
        "allow_fetch":     bool(getattr(s, "allow_tile_fetch", 1)),
        "cache_days":      int(getattr(s, "tile_cache_days", _DEFAULT_CACHE_DAYS) or _DEFAULT_CACHE_DAYS),
    })


def _authz():
    if frappe.session.user == "Guest":
        frappe.throw("Login required to access map tiles", frappe.PermissionError)
    if not frappe.has_permission("Place", "read"):
        frappe.throw("No permission to access map tiles", frappe.PermissionError)


def _cache_root():
    root = Path(frappe.get_site_path("private")).resolve() / "siraj_tile_cache"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _cache_path(layer: str, z: int, x: int, y: int, ext: str) -> Path:
    return _cache_root() / layer / str(z) / str(x) / f"{y}.{ext}"


def _valid_coord(z, x, y):
    if not (_COORD.match(str(z)) and _COORD.match(str(x)) and _COORD.match(str(y))):
        return False
    z, x, y = int(z), int(x), int(y)
    if z < 0 or z > 22:
        return False
    max_xy = 2 ** z
    return 0 <= x < max_xy and 0 <= y < max_xy


def _fetch(url: str, ua: str) -> bytes:
    req = Request(url, headers={"User-Agent": ua, "Accept": "image/*"})
    with urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
        if resp.status != 200:
            raise frappe.ValidationError(f"Upstream HTTP {resp.status}")
        data = resp.read(_MAX_TILE_BYTES + 1)
        if len(data) > _MAX_TILE_BYTES:
            raise frappe.ValidationError("Tile too large")
        return data


def _serve(data: bytes, ctype: str, hit: bool):
    return Response(
        data, content_type=ctype,
        headers={
            "Cache-Control": f"public, max-age={7*86400}, immutable",
            "X-Siraj-Cache": "HIT" if hit else "MISS",
            "X-Content-Type-Options": "nosniff",
        },
        direct_passthrough=True,
    )


@frappe.whitelist(methods=["GET"])
@rate_limit(limit=1200, seconds=60)
def active_layer():
    """Return the single active layer the client should render."""
    _authz()
    s = _settings()
    name = s.default_layer if s.default_layer in LAYERS else "standard"
    if not getattr(s, f"enable_{name}", False) and name != "standard":
        name = "standard" if s.enable_standard else None
    if not name:
        return {"layer": None, "attribution": ""}
    spec = LAYERS[name]
    return {
        "layer": name,
        "url": f"/api/method/siraj_research.tile_cache.tile?layer={name}&z={{z}}&x={{x}}&y={{y}}",
        "overlayUrl": (f"/api/method/siraj_research.tile_cache.tile?layer={name}_labels&z={{z}}&x={{x}}&y={{y}}"
                       if name == "hybrid" else None),
        "attribution": spec["attribution"],
        "maxZoom": spec["max_zoom"],
    }


@frappe.whitelist(methods=["GET"])
@rate_limit(limit=1200, seconds=60)
def tile(layer, z, x, y):
    """Serve a tile from disk cache, fetching once from upstream if needed."""
    _authz()
    s = _settings()
    base_layer = layer.replace("_labels", "")
    is_overlay = layer.endswith("_labels")
    if base_layer not in LAYERS:
        frappe.throw("Unknown layer", frappe.DoesNotExistError)
    if not getattr(s, f"enable_{base_layer}", False) and base_layer != "standard":
        frappe.throw("Layer disabled", frappe.PermissionError)
    if is_overlay and "overlay_url" not in LAYERS[base_layer]:
        frappe.throw("Layer has no overlay", frappe.DoesNotExistError)
    if not _valid_coord(z, x, y):
        frappe.throw("Invalid tile coordinate", frappe.ValidationError)
    z, x, y = int(z), int(x), int(y)
    spec = LAYERS[base_layer]
    url = (spec["overlay_url"] if is_overlay else spec["url"]).format(z=z, x=x, y=y)
    ext, ctype = spec["ext"], spec["content_type"]
    path = _cache_path(layer, z, x, y, ext)
    path.parent.mkdir(parents=True, exist_ok=True)
    # 1) Serve from disk if fresh.
    try:
        if path.is_file():
            if time.time() - path.stat().st_mtime < s.cache_days * 86400:
                return _serve(path.read_bytes(), ctype, hit=True)
    except OSError:
        pass
    # 2) Not cached or stale; fetch if allowed.
    if not s.allow_fetch:
        frappe.response["http_status_code"] = 503
        return _serve(b"", "image/png", hit=False)
    try:
        data = _fetch(url, spec["user_agent"])
    except Exception as e:  # noqa: BLE001
        try:
            if path.is_file():
                return _serve(path.read_bytes(), ctype, hit=True)  # stale-while-revalidate
        except OSError:
            pass
        frappe.log_error(f"Tile fetch failed {layer} {z}/{x}/{y}: {e}", "siraj.tile_cache")
        frappe.response["http_status_code"] = 502
        return _serve(b"", "image/png", hit=False)
    # 3) Persist + serve.
    try:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
    except OSError as e:
        frappe.log_error(f"Tile cache write failed: {e}", "siraj.tile_cache")
    return _serve(data, ctype, hit=False)
