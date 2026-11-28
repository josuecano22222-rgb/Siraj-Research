"""Natural Earth Vector pack management — provision, manifest, serve.

Natural Earth publishes the world's cultural + physical geography as vector
GeoJSON at three scales (1:10m / 1:50m / 1:110m; see
``siraj_research.natural_earth_catalog``). This module turns that public-domain
dataset into a *site-local pack*:

Pack layout (site private storage)
---------------------------------
``<site>/private/natural_earth_vector/<scale>/<layer>.geojson``
``<site>/private/natural_earth_vector/manifest.json``
``<site>/private/natural_earth_vector/natural_earth_vector.zip``

The 1:110m tier is additionally *bundled* in the app under
``public/natural_earth/110m`` so a fresh install renders a full offline vector
basemap with zero provisioning. The 50m and 10m tiers are provisioned by the
``Natural Earth Vector Pack`` admin DocType, either by fetching the dataset
from the canonical GitHub mirror (git protocol, no API rate limits) or by
copying from an admin-supplied local mirror directory (air-gapped sites).

Everything is public-domain map data; serving is unauthenticated like the
existing tile cache, and no privacy-sensitive data is involved.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path
from typing import Optional

import frappe

from siraj_research.natural_earth_catalog import (
    DATA_VERSION,
    SOURCE_REF,
    SOURCE_REPO,
    get_layer,
    layers_for_scale,
    scale_for_zoom,
)

PACK_DIRNAME = "natural_earth_vector"
BUNDLED_SCALE = "110m"
MANIFEST_NAME = "manifest.json"
ZIP_NAME = "natural_earth_vector.zip"

PROVISION_SOURCES = ("git_clone", "local_mirror")


class NaturalEarthPackError(Exception):
    """Raised for invalid pack operations (bad manifest, unsafe paths, …)."""


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _site_root() -> Path:
    return Path(frappe.get_site_path()).resolve()


def pack_root() -> Path:
    return _site_root() / "private" / PACK_DIRNAME


def bundled_root() -> Path:
    # frappe.local.app_path is only populated in a request context; use the
    # get_app_path API so the bundled tier resolves during run-tests / CLI too.
    return Path(frappe.get_app_path("siraj_research"), "public", "natural_earth",
                BUNDLED_SCALE).resolve()


def manifest_path() -> Path:
    return pack_root() / MANIFEST_NAME


def zip_path() -> Path:
    return pack_root() / ZIP_NAME


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _require_catalog_file(name: str) -> str:
    """Validate a layer file name against the catalog (path-traversal guard)."""
    layer = get_layer(name)
    if not layer:
        raise NaturalEarthPackError(f"Unknown Natural Earth layer: {name}")
    return name


# ---------------------------------------------------------------------------
# Bundled tier (ships in the app)
# ---------------------------------------------------------------------------

def bundled_manifest() -> dict:
    """Manifest for the bundled 1:110m tier (no pack required)."""
    root = bundled_root()
    layers = {}
    total = 0
    if root.is_dir():
        for path in sorted(root.glob("*.geojson")):
            data = path.read_bytes()
            meta = get_layer(path.name) or {}
            layers[path.name] = {
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
                "scale": meta.get("scale", BUNDLED_SCALE),
                "category": meta.get("category", "cultural"),
                "kind": meta.get("kind", "general"),
                "description": meta.get("description", ""),
                "source": "bundle",
            }
            total += len(data)
    return {
        "name": "natural_earth_vector",
        "kind": "bundle",
        "scale": BUNDLED_SCALE,
        "source": {"repo": SOURCE_REPO, "ref": SOURCE_REF, "data_version": DATA_VERSION,
                   "license": "public domain"},
        "layers": layers,
        "stats": {"file_count": len(layers), "total_bytes": total},
    }


# ---------------------------------------------------------------------------
# Pack manifest
# ---------------------------------------------------------------------------

def empty_manifest(scales) -> dict:
    return {
        "name": "natural_earth_vector",
        "kind": "pack",
        "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "scales": sorted(scales),
        "source": {"repo": SOURCE_REPO, "ref": SOURCE_REF, "data_version": DATA_VERSION,
                   "license": "public domain"},
        "layers": {},
        "stats": {"file_count": 0, "total_bytes": 0},
    }


def validate_manifest(manifest: dict) -> dict:
    """Structural validation of a pack manifest; raises on problems."""
    if not isinstance(manifest, dict):
        raise NaturalEarthPackError("Manifest must be a JSON object")
    for key in ("name", "scales", "layers", "stats", "source"):
        if key not in manifest:
            raise NaturalEarthPackError(f"Manifest missing key: {key}")
    scales = manifest.get("scales") or []
    if not set(scales).issubset({"10m", "50m", "110m"}):
        raise NaturalEarthPackError("Manifest declares unknown scales")
    layers = manifest.get("layers") or {}
    if not isinstance(layers, dict):
        raise NaturalEarthPackError("Manifest layers must be an object")
    for name, meta in layers.items():
        _require_catalog_file(name)
        if not isinstance(meta, dict) or "sha256" not in meta:
            raise NaturalEarthPackError(f"Manifest layer {name} lacks sha256")
    stats = manifest.get("stats") or {}
    if stats.get("file_count") != len(layers):
        raise NaturalEarthPackError("Manifest stats.file_count does not match layers")
    return manifest


def read_manifest() -> dict | None:
    path = manifest_path()
    if not path.is_file():
        return None
    try:
        manifest = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise NaturalEarthPackError(f"Unreadable pack manifest: {exc}") from exc
    return validate_manifest(manifest)


def write_manifest(manifest: dict) -> None:
    manifest = validate_manifest(manifest)
    root = pack_root()
    root.mkdir(parents=True, exist_ok=True)
    manifest_path().write_text(json.dumps(manifest, indent=2, sort_keys=True))


# ---------------------------------------------------------------------------
# Provisioning
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _clone_repo(dest: Path) -> Path:
    """Clone the canonical Natural Earth mirror (blob-filtered, sparse).

    The git protocol is used deliberately: it has no API rate limits, so the
    full 1:10m tier (129 files, ~1.1 GB) provisions reliably.
    """
    subprocess.run(
        [
            "git", "clone", "--depth", "1", "--filter=blob:none",
            "--sparse", "--no-checkout",
            f"https://github.com/{SOURCE_REPO}.git", str(dest),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return dest


def _fetch_file(mirror: Path, name: str) -> Path | None:
    """Locate ``name`` inside the mirror tree; returns None when absent."""
    rel = Path("geojson") / name
    candidate = mirror / rel
    if candidate.is_file():
        return candidate
    # Some mirrors flatten the layout; fall back to a recursive search.
    matches = list(mirror.rglob(name))
    if matches:
        return matches[0]
    return None


def provision_pack(scales, layers=None, source="git_clone", mirror_path=None,
                   pack_name=None) -> dict:
    """Download/copy the requested Natural Earth vector layers into the pack.

    Parameters
    ----------
    scales: iterable of scale codes to provision ("10m", "50m", "110m").
    layers: optional explicit layer names; defaults to the full catalog for
        the requested scales.
    source: "git_clone" (default, fetch from the canonical GitHub mirror) or
        "local_mirror" (copy from an admin-supplied directory).
    mirror_path: directory used when ``source == "local_mirror"``.

    Returns the written manifest. Raises ``NaturalEarthPackError`` on failure.
    """
    scales = [s for s in scales if s in ("10m", "50m", "110m")]
    if not scales:
        raise NaturalEarthPackError("No valid scales requested")

    if layers:
        wanted = [_require_catalog_file(n) for n in layers]
    else:
        wanted = []
        for scale in scales:
            wanted.extend(
                layer["file"] for layer in layers_for_scale(scale) if layer
            )

    root = pack_root()
    root.mkdir(parents=True, exist_ok=True)

    if source == "local_mirror":
        if not mirror_path:
            raise NaturalEarthPackError("local_mirror provisioning needs mirror_path")
        path = Path(mirror_path).resolve()
        if not _is_within(path, _site_root()):
            raise NaturalEarthPackError("Mirror directory must live inside the site")
        if not path.is_dir():
            raise NaturalEarthPackError(f"Mirror directory not found: {mirror_path}")
    elif source == "git_clone":
        path = _clone_repo(root / "_clone")
    else:
        raise NaturalEarthPackError(f"Unknown provision source: {source}")

    manifest = empty_manifest(scales)
    copied = 0
    missing = []
    for name in wanted:
        src = _fetch_file(path, name)
        if src is None:
            missing.append(name)
            continue
        dest = root / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        data = src.read_bytes()
        # Defensive: never write through symlinks out of the pack root.
        if dest.exists() and (dest.is_symlink() or not _is_within(dest, root)):
            dest.unlink()
        dest.write_bytes(data)
        meta = get_layer(name) or {}
        manifest["layers"][name] = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
            "scale": meta.get("scale", name.split("_")[1] if name.startswith("ne_") else ""),
            "category": meta.get("category", "cultural"),
            "kind": meta.get("kind", "general"),
            "description": meta.get("description", ""),
            "source": "pack",
        }
        copied += 1

    if not copied:
        raise NaturalEarthPackError("No layers could be provisioned from the mirror")

    manifest["stats"] = {"file_count": copied, "total_bytes": sum(
        m["bytes"] for m in manifest["layers"].values())}
    if missing:
        manifest["missing"] = missing
    write_manifest(manifest)

    # Compile the offline ZIP archive from the provisioned pack.
    build_zip(manifest)
    return manifest


def build_zip(manifest: dict | None = None) -> Path | None:
    """Compile the provisioned pack into the offline ZIP archive."""
    manifest = manifest or read_manifest()
    if not manifest:
        return None
    root = pack_root()
    out = zip_path()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
        for name in sorted(manifest["layers"]):
            path = root / name
            if path.is_file():
                zf.write(path, arcname=name)
    return out


# ---------------------------------------------------------------------------
# Availability + serving
# ---------------------------------------------------------------------------

def available_scales() -> list:
    """Scales with data available (bundled 110m always; pack tiers if ready)."""
    scales = {BUNDLED_SCALE}
    manifest = read_manifest()
    if manifest:
        scales.update(manifest.get("scales") or [])
    return sorted(scales)


def available_layers(scale: str | None = None) -> list:
    """Catalog layers available on the server, merged pack + bundle.

    Returns entries with ``name``, ``scale``, ``source`` ("bundle"/"pack")
    and catalog metadata.
    """
    bundle = bundled_manifest().get("layers", {})
    manifest = read_manifest()
    pack = manifest.get("layers", {}) if manifest else {}
    result = []
    for name, meta in sorted({**bundle, **pack}.items()):
        if scale and meta.get("scale") != scale:
            continue
        catalog = get_layer(name) or {}
        result.append({
            "name": name,
            "scale": meta.get("scale"),
            "source": meta.get("source", "pack"),
            "category": catalog.get("category", meta.get("category")),
            "kind": catalog.get("kind", meta.get("kind")),
            "description": catalog.get("description", meta.get("description")),
            "bytes": meta.get("bytes"),
            "sha256": meta.get("sha256"),
        })
    return result


def layer_file_path(name: str) -> Path | None:
    """Resolve a layer file on disk (pack first, then bundle)."""
    name = _require_catalog_file(name)
    pack = pack_root() / name
    if pack.is_file() and _is_within(pack, pack_root()):
        return pack
    bundled = bundled_root() / name
    if bundled.is_file() and _is_within(bundled, bundled_root()):
        return bundled
    return None


def read_layer(name: str) -> str | None:
    """Return the GeoJSON text for a layer, or None when unavailable."""
    path = layer_file_path(name)
    if path is None:
        return None
    return path.read_text()


def layer_etag(name: str) -> str | None:
    path = layer_file_path(name)
    if path is None:
        return None
    return f"ne-{name}:{path.stat().st_size}:{int(path.stat().st_mtime_ns)}"


def scale_for_zoom_with_fallback(zoom: float) -> str:
    """Scale tier for a zoom, falling back to the finest *available* tier."""
    wanted = scale_for_zoom(zoom)
    available = set(available_scales())
    if wanted in available:
        return wanted
    for candidate in ("10m", "50m", "110m"):
        if candidate in available:
            return candidate
    return wanted


def pack_stats() -> dict:
    manifest = read_manifest()
    bundle = bundled_manifest()
    return {
        "pack_ready": manifest is not None,
        "pack_scales": (manifest or {}).get("scales", []),
        "pack_layers": (manifest or {}).get("stats", {}).get("file_count", 0),
        "pack_bytes": (manifest or {}).get("stats", {}).get("total_bytes", 0),
        "zip_ready": zip_path().is_file() if manifest else False,
        "bundle_scale": BUNDLED_SCALE,
        "bundle_layers": bundle.get("stats", {}).get("file_count", 0),
        "bundle_bytes": bundle.get("stats", {}).get("total_bytes", 0),
        "available_scales": available_scales(),
    }
