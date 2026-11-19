"""Server-side cached tile proxy.

Proxies raster tiles for every supported basemap (OSM standard, Esri aerial
& hybrid, NASA GIBS MODIS true-color, Stadia/Stamen Toner/Terrain/Watercolor,
USGS Topo), caching them to disk so subsequent requests never re-hit the
external provider. Once a tile has been fetched, the server can keep
serving it even when offline from the internet (stale-while-revalidate).

Clients never contact tile providers directly — all traffic routes through
``/api/method/siraj_research.tile_cache.tile``. End users do not see a
basemap switcher; the administrator picks the default layer in Geo Settings,
where each layer can be enabled/disabled independently and API keys are
stored.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import re
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

import frappe
from frappe.rate_limiter import rate_limit
from werkzeug.wrappers import Response

# ---- Layer catalog ---------------------------------------------------------
# Each layer declares its URL template, attribution, format, max zoom, and
# whether it needs an API key or date parameter. URL templates use {z}/{x}/{y}
# (XYZ / Google scheme — top-origin y — which Leaflet uses by default).
# {k} is substituted with the configured API key; {t} is substituted with
# the configured date (YYYY-MM-DD, or "default" when not set).
# NASA GIBS uses the WMTS webmercator endpoint (GoogleMapsCompatible_Level9
# for MODIS True Color = z 0..9, ~500 m/pixel) and requires a date.
# Stadia layers require an API key from https://client.stadiamaps.com/.
# USGS is US-only; no key required.
LAYERS = {
    "standard": {
        "label": "Standard (OpenStreetMap)",
        "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "attribution": "&copy; <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a> contributors",
        "content_type": "image/png",
        "ext": "png",
        "min_zoom": 0, "max_zoom": 19,
        "user_agent": "SIRAJ-Research/1.0",
        "needs_key": False,
    },
    "aerial": {
        "label": "Aerial — Esri World Imagery",
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attribution": "Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community",
        "content_type": "image/jpeg",
        "ext": "jpg",
        "min_zoom": 0, "max_zoom": 19,
        "user_agent": "SIRAJ-Research/1.0",
        "needs_key": False,
    },
    "hybrid": {
        "label": "Hybrid — Esri Imagery + Labels",
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "overlay_url": "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
        "attribution": "Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community",
        "content_type": "image/jpeg",
        "ext": "jpg",
        "min_zoom": 0, "max_zoom": 19,
        "user_agent": "SIRAJ-Research/1.0",
        "needs_key": False,
    },
    "toner": {
        "label": "Stamen Toner (high-contrast B&W)",
        "url": "https://tiles.stadiamaps.com/tiles/stamen_toner/{z}/{x}/{y}{r}.png?api_key={k}",
        "attribution": "&copy; <a href='https://stadiamaps.com/'>Stadia Maps</a> &copy; <a href='https://stamen.com'>Stamen Design</a> &copy; <a href='https://openmaptiles.org'>OpenMapTiles</a>",
        "content_type": "image/png",
        "ext": "png",
        "min_zoom": 0, "max_zoom": 20,
        "user_agent": "SIRAJ-Research/1.0",
        "needs_key": True, "key_field": "stadia_api_key",
        "retina_support": True,
    },
    "terrain": {
        "label": "Stamen Terrain (hillshade)",
        "url": "https://tiles.stadiamaps.com/tiles/stamen_terrain/{z}/{x}/{y}{r}.png?api_key={k}",
        "attribution": "&copy; <a href='https://stadiamaps.com/'>Stadia Maps</a> &copy; <a href='https://stamen.com'>Stamen Design</a> &copy; <a href='https://openmaptiles.org'>OpenMapTiles</a>",
        "content_type": "image/png",
        "ext": "png",
        "min_zoom": 0, "max_zoom": 18,
        "user_agent": "SIRAJ-Research/1.0",
        "needs_key": True, "key_field": "stadia_api_key",
        "retina_support": True,
    },
    "watercolor": {
        "label": "Stamen Watercolor (artistic)",
        "url": "https://tiles.stadiamaps.com/tiles/stamen_watercolor/{z}/{x}/{y}.jpg?api_key={k}",
        "attribution": "&copy; <a href='https://stadiamaps.com/'>Stadia Maps</a> &copy; <a href='https://stamen.com'>Stamen Design</a>",
        "content_type": "image/jpeg",
        "ext": "jpg",
        "min_zoom": 1, "max_zoom": 16,
        "user_agent": "SIRAJ-Research/1.0",
        "needs_key": True, "key_field": "stadia_api_key",
    },
    "usgs_topo": {
        "label": "USGS Topographic (North America)",
        "url": "https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}",
        "attribution": "Tiles courtesy of the <a href='https://usgs.gov/'>U.S. Geological Survey</a>",
        "content_type": "image/png",
        "ext": "png",
        "min_zoom": 0, "max_zoom": 16,
        "user_agent": "SIRAJ-Research/1.0",
        "needs_key": False,
    },
    "nasa_modis": {
        "label": "NASA MODIS True-Color (satellite, daily)",
        "url": "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/MODIS_Terra_CorrectedReflectance_TrueColor/default/{t}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg",
        "attribution": "Imagery by NASA EOSDIS <a href='https://earthdata.nasa.gov/eosdis/science-system-description/eosdis-components/gibs'>GIBS</a> / MODIS Terra Corrected Reflectance True Color",
        "content_type": "image/jpeg",
        "ext": "jpg",
        "min_zoom": 0, "max_zoom": 9,
        "user_agent": "SIRAJ-Research/1.0",
        "needs_key": False,
        "needs_date": True, "date_field": "nasa_gibs_date",
    },
}

_COORD = re.compile(r"^[0-9]{1,10}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DEFAULT_CACHE_DAYS = 90
_HTTP_TIMEOUT = 10
_MAX_TILE_BYTES = 2 * 1024 * 1024  # 2 MiB (some Esri tiles are slightly larger than 256KB)


def _settings():
    s = frappe.get_single("Geo Settings")
    return frappe._dict({
        "default_layer":   (getattr(s, "default_tile_layer", None) or "standard").strip(),
        "enable_standard": bool(getattr(s, "enable_standard_layer", 1)),
        "enable_aerial":   bool(getattr(s, "enable_aerial_layer", 1)),
        "enable_hybrid":   bool(getattr(s, "enable_hybrid_layer", 0)),
        "enable_toner":    bool(getattr(s, "enable_toner_layer", 0)),
        "enable_terrain":  bool(getattr(s, "enable_terrain_layer", 0)),
        "enable_watercolor": bool(getattr(s, "enable_watercolor_layer", 0)),
        "enable_usgs_topo": bool(getattr(s, "enable_usgs_topo_layer", 0)),
        "enable_nasa_modis": bool(getattr(s, "enable_nasa_modis_layer", 0)),
        "allow_fetch":     bool(getattr(s, "allow_tile_fetch", 1)),
        "cache_days":      int(getattr(s, "tile_cache_days", _DEFAULT_CACHE_DAYS) or _DEFAULT_CACHE_DAYS),
        "stadia_api_key":  (getattr(s, "stadia_api_key", "") or "").strip(),
        "nasa_gibs_date":  (getattr(s, "nasa_gibs_date", "") or "").strip(),
    })


_ENABLE_FLAG = {
    "standard":    "enable_standard",
    "aerial":      "enable_aerial",
    "hybrid":      "enable_hybrid",
    "toner":       "enable_toner",
    "terrain":     "enable_terrain",
    "watercolor":  "enable_watercolor",
    "usgs_topo":   "enable_usgs_topo",
    "nasa_modis":  "enable_nasa_modis",
}


def _authz():
    if frappe.session.user == "Guest":
        frappe.throw("Login required to access map tiles", frappe.PermissionError)
    if not frappe.has_permission("Place", "read"):
        frappe.throw("No permission to access map tiles", frappe.PermissionError)


def _cache_root():
    root = Path(frappe.get_site_path("private")).resolve() / "siraj_tile_cache"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _cache_path(layer: str, z: int, x: int, y: int, ext: str, variant: str = "") -> Path:
    # Shard by layer/variant/z/x/y so retina tiles, dated NASA tiles, etc. don't
    # collide on disk.
    safe_variant = re.sub(r"[^A-Za-z0-9_.-]", "_", variant) if variant else "_"
    return _cache_root() / layer / safe_variant / str(z) / str(x) / f"{y}.{ext}"


def _valid_coord(z, x, y):
    if not (_COORD.match(str(z)) and _COORD.match(str(x)) and _COORD.match(str(y))):
        return False
    z, x, y = int(z), int(x), int(y)
    if z < 0 or z > 22:
        return False
    max_xy = 2 ** z
    return 0 <= x < max_xy and 0 <= y < max_xy


def _resolve_url(spec: dict, s: frappe._dict, variant: str, z: int) -> str:
    url = spec["overlay_url"] if variant == "overlay" else spec["url"]
    url = url.replace("{z}", str(z)).replace("{x}", "{x}").replace("{y}", "{y}")  # x/y filled per-request
    key = s.get(spec.get("key_field", ""), "") if spec.get("needs_key") else ""
    if spec.get("needs_key") and not key:
        raise frappe.ValidationError(f"Layer requires an API key ({spec.get('key_field')})")
    url = url.replace("{k}", quote(key, safe=""))
    # Retina: @2x for high-DPI tiles where supported. We opt-out globally to
    # keep the cache footprint small; clients request non-retina only.
    url = url.replace("{r}", "")
    # Date parameter for NASA GIBS: use configured date, or fall back to
    # today's UTC date if none set.
    date_val = ""
    if spec.get("needs_date"):
        date_val = s.get(spec.get("date_field", ""), "") or ""
        if not date_val or not _DATE.match(date_val):
            date_val = _dt.datetime.utcnow().strftime("%Y-%m-%d")
    url = url.replace("{t}", date_val)
    return url


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


def _resolve_layer(name: str, s: frappe._dict):
    """Return (base_layer_name, variant) for a request like 'hybrid_labels'."""
    variant = "base"
    base = name
    if name.endswith("_labels"):
        base = name[: -len("_labels")]
        variant = "overlay"
    if base not in LAYERS:
        frappe.throw("Unknown layer", frappe.DoesNotExistError)
    flag = _ENABLE_FLAG.get(base)
    if flag and not getattr(s, flag, False) and base != "standard":
        frappe.throw("Layer disabled", frappe.PermissionError)
    if variant == "overlay" and "overlay_url" not in LAYERS[base]:
        frappe.throw("Layer has no overlay", frappe.DoesNotExistError)
    return base, variant


@frappe.whitelist(methods=["GET"])
@rate_limit(limit=1200, seconds=60)
def active_layer():
    """Return the single layer the client should render."""
    _authz()
    s = _settings()
    name = s.default_layer if s.default_layer in LAYERS else "standard"
    flag = _ENABLE_FLAG.get(name)
    if flag and not getattr(s, flag, False):
        # Fall back to standard if configured layer is disabled.
        name = "standard" if s.enable_standard else None
    if not name:
        return {"layer": None, "attribution": "", "layers": _enabled_layers(s)}
    spec = LAYERS[name]
    # Build a variant suffix for cache path + URL date/key resolution.
    variant_key = ""
    if spec.get("needs_date"):
        date_val = s.get(spec.get("date_field", ""), "") or _dt.datetime.utcnow().strftime("%Y-%m-%d")
        variant_key = date_val
    return {
        "layer": name,
        "url": f"/api/method/siraj_research.tile_cache.tile?layer={name}&z={{z}}&x={{x}}&y={{y}}",
        "overlayUrl": (f"/api/method/siraj_research.tile_cache.tile?layer={name}_labels&z={{z}}&x={{x}}&y={{y}}"
                       if name == "hybrid" else None),
        "attribution": spec["attribution"],
        "maxZoom": spec["max_zoom"],
        "minZoom": spec["min_zoom"],
        "variant": variant_key,
        # Offer the list of enabled layers so a future admin UI can build a
        # dropdown; clients don't render a switcher today.
        "layers": _enabled_layers(s),
    }


def _enabled_layers(s):
    return [
        {"key": k, "label": LAYERS[k]["label"]}
        for k in LAYERS
        if k + "_labels" not in LAYERS  # skip synthetic overlays
        and getattr(s, _ENABLE_FLAG.get(k, "enable_standard"), True)
        and (not LAYERS[k].get("needs_key") or s.get(LAYERS[k].get("key_field", ""), ""))
    ]


@frappe.whitelist(methods=["GET"])
@rate_limit(limit=300, seconds=60)
def cache_stats():
    """Return on-disk cache size + tile count (for Geo Settings UI)."""
    _authz()
    if not frappe.has_permission("Geo Settings", "write"):
        frappe.throw("Admin only", frappe.PermissionError)
    root = _cache_root()
    count = 0
    size = 0
    for p in root.rglob("*"):
        if p.is_file():
            count += 1
            size += p.stat().st_size
    return {"count": count, "size_mb": round(size / (1024 * 1024), 2)}


@frappe.whitelist(methods=["POST"])
def cache_purge():
    """Delete all cached tiles (admin only)."""
    _authz()
    if not frappe.has_permission("Geo Settings", "write"):
        frappe.throw("Admin only", frappe.PermissionError)
    import shutil
    root = _cache_root()
    for child in root.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            try: child.unlink()
            except OSError: pass
    return {"ok": True}


@frappe.whitelist(methods=["GET"])
@rate_limit(limit=1200, seconds=60)
def tile(layer, z, x, y):
    """Serve a tile from disk cache, fetching from upstream once if needed."""
    _authz()
    s = _settings()
    base, variant = _resolve_layer(layer, s)
    spec = LAYERS[base]
    z_int, x_int, y_int = int(z), int(x), int(y)
    if not _valid_coord(z_int, x_int, y_int):
        frappe.throw("Invalid tile coordinate", frappe.ValidationError)
    if z_int < spec.get("min_zoom", 0) or z_int > spec.get("max_zoom", 22):
        frappe.response["http_status_code"] = 404
        return _serve(b"", "image/png", hit=False)
    # Resolve variant-specific key for cache (date for NASA, "overlay" for hybrid).
    variant_key = "base" if variant == "base" else "overlay"
    if spec.get("needs_date") and variant == "base":
        d = s.get(spec.get("date_field", ""), "") or _dt.datetime.utcnow().strftime("%Y-%m-%d")
        if not _DATE.match(d):
            d = _dt.datetime.utcnow().strftime("%Y-%m-%d")
        variant_key = d
    # x/y filled here, z is fixed for clamping (NASA uses GoogleMapsCompatible_Level9).
    url = _resolve_url(spec, s, variant, z_int).replace("{x}", str(x_int)).replace("{y}", str(y_int))
    ext = spec["ext"]
    ctype = spec["content_type"]
    # Retina disabled (see _resolve_url) but keep subdir just in case.
    path = _cache_path(base, z_int, x_int, y_int, ext, variant_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    # 1) Serve from disk if fresh.
    try:
        if path.is_file():
            if time.time() - path.stat().st_mtime < s.cache_days * 86400:
                return _serve(path.read_bytes(), ctype, hit=True)
    except OSError:
        pass
    # 2) Fetch upstream if allowed.
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
    # 3) Persist atomically + serve.
    try:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
    except OSError as e:
        frappe.log_error(f"Tile cache write failed: {e}", "siraj.tile_cache")
    return _serve(data, ctype, hit=False)


def enable_shared_basemaps():
	"""Enable standard, aerial and hybrid layers for shared server caching.

	Bench-only helper (no web endpoint): every viewed tile is written once to
	the site's private disk cache and can then be served to any user, even if
	the upstream provider is unreachable. Optional keyed layers are untouched.
	"""
	settings = frappe.get_single("Geo Settings")
	settings.enable_standard_layer = 1
	settings.enable_aerial_layer = 1
	settings.enable_hybrid_layer = 1
	settings.allow_tile_fetch = 1
	if int(settings.tile_cache_days or 0) < 90:
		settings.tile_cache_days = 90
	settings.save(ignore_permissions=True)
	return {
		"standard": 1,
		"aerial": 1,
		"hybrid": 1,
		"allow_tile_fetch": 1,
		"tile_cache_days": int(settings.tile_cache_days),
	}
