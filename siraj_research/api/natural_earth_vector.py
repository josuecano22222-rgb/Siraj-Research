"""HTTP endpoints for the Natural Earth Vector pack.

Public, cacheable endpoints:

- ``GET /api/method/siraj_research.api.natural_earth_vector.catalog``
  Full layer catalog + server availability summary.
- ``GET /api/method/siraj_research.api.natural_earth_vector.manifest``
  Combined manifest (bundle + provisioned pack).
- ``GET /api/method/siraj_research.api.natural_earth_vector.index?scale=110m``
  Layers available on the server for a scale.
- ``GET /api/method/siraj_research.api.natural_earth_vector.layer?layer=<name>``
  The raw GeoJSON for one layer (ETag / 304, Content-Type
  ``application/geo+json``).

Administrator endpoints (whitelisted, permission-checked):

- ``GET /api/method/siraj_research.api.natural_earth_vector.status``
  Pack/bundle statistics.
- ``POST /api/method/siraj_research.api.natural_earth_vector.provision``
  Provision the pack (``source`` = ``git_clone`` | ``local_mirror``).

The data is public-domain world map data; serving requires no authentication
(mirroring the existing tile cache), and no privacy-sensitive content exists.
"""

from __future__ import annotations

import json

import frappe
from werkzeug.wrappers import Response

from siraj_research import natural_earth_vector as nev
from siraj_research.natural_earth_catalog import (
    DATA_VERSION,
    SCALES,
    SOURCE_REF,
    SOURCE_REPO,
    ZOOM_TIERS,
    catalog_summary,
    scale_for_zoom,
)

_CACHE_CONTROL = "public, max-age=3600"


@frappe.whitelist(methods=["GET"])
def catalog():
    """Full catalog metadata plus server-side availability."""
    summary = catalog_summary()
    summary["available_scales"] = nev.available_scales()
    summary["pack"] = nev.pack_stats()
    return summary


@frappe.whitelist(methods=["GET"])
def manifest():
    """Combined manifest: bundled tier + provisioned pack (if any)."""
    bundle = nev.bundled_manifest()
    pack = nev.read_manifest()
    return {
        "source": {"repo": SOURCE_REPO, "ref": SOURCE_REF,
                   "data_version": DATA_VERSION, "license": "public domain"},
        "scales": SCALES,
        "bundle": bundle,
        "pack": pack,
        "available_scales": nev.available_scales(),
        "zoom_tiers": [
            {"max_zoom": t["max_zoom"], "scale": t["scale"]}
            for t in ZOOM_TIERS
        ],
        "scale_for_zoom": scale_for_zoom(
            float(frappe.form_dict.get("zoom") or 4)
        ),
    }


@frappe.whitelist(methods=["GET"])
def index(scale: str | None = None):
    """Layers available on the server (merged pack + bundle)."""
    if scale and scale not in SCALES:
        frappe.throw("Unknown scale", frappe.ValidationError)
    layers = nev.available_layers(scale)
    return {
        "scales": nev.available_scales(),
        "count": len(layers),
        "layers": layers,
    }


@frappe.whitelist(methods=["GET"])
def layer(layer: str):
    """Serve the raw GeoJSON for one Natural Earth layer."""
    if not layer:
        frappe.throw("Missing layer name", frappe.ValidationError)
    try:
        text = nev.read_layer(layer)
    except nev.NaturalEarthPackError:
        return Response(status=404, headers={"Cache-Control": _CACHE_CONTROL})
    if text is None:
        return Response(status=404, headers={"Cache-Control": _CACHE_CONTROL})
    etag = nev.layer_etag(layer)
    if frappe.request:
        inm = frappe.request.headers.get("If-None-Match", "") or ""
        if etag and inm == etag:
            return Response(status=304, headers={"Cache-Control": _CACHE_CONTROL,
                                                 "ETag": etag})
    return Response(
        text,
        status=200,
        content_type="application/geo+json",
        headers={"Cache-Control": _CACHE_CONTROL, "ETag": etag or ""},
    )


def _require_admin():
    if frappe.session.user == "Guest" or not frappe.has_permission(
        "Natural Earth Vector Pack", "read"
    ):
        frappe.throw("Administrator role required", frappe.PermissionError)


@frappe.whitelist(methods=["GET"])
def status():
    """Pack/bundle statistics (administrators)."""
    _require_admin()
    stats = nev.pack_stats()
    stats["catalog"] = catalog_summary()
    return stats


@frappe.whitelist(methods=["POST"])
def provision():
    """Provision the Natural Earth Vector pack (administrators only).

    Parameters (form dict): ``source`` (``git_clone`` | ``local_mirror``),
    ``scales`` (comma-separated or JSON list), ``layers`` (optional explicit
    layer names), ``mirror_path`` (required for ``local_mirror``).

    Runs synchronously; large tiers (10m, ~1.1 GB) take several minutes and
    are best run from the admin tool's background job wrapper.
    """
    _require_admin()
    source = frappe.form_dict.get("source") or "git_clone"
    if source not in nev.PROVISION_SOURCES:
        frappe.throw("Unknown provision source", frappe.ValidationError)

    scales_raw = frappe.form_dict.get("scales") or "110m,50m,10m"
    if isinstance(scales_raw, str):
        scales = [s.strip() for s in scales_raw.split(",") if s.strip()]
    else:
        scales = list(scales_raw)

    layers_raw = frappe.form_dict.get("layers")
    layers = None
    if layers_raw:
        layers = (json.loads(layers_raw) if isinstance(layers_raw, str)
                  else list(layers_raw))

    mirror_path = frappe.form_dict.get("mirror_path") or None
    try:
        manifest = nev.provision_pack(
            scales, layers=layers, source=source, mirror_path=mirror_path
        )
    except nev.NaturalEarthPackError as exc:
        frappe.throw(f"Provisioning failed: {exc}", frappe.ValidationError)

    frappe.clear_cache()
    return {
        "ok": True,
        "source": source,
        "scales": manifest["scales"],
        "file_count": manifest["stats"]["file_count"],
        "total_bytes": manifest["stats"]["total_bytes"],
        "missing": manifest.get("missing", []),
        "zip": str(nev.zip_path()) if nev.zip_path().is_file() else None,
    }
