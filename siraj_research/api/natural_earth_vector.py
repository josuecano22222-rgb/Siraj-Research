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

Country-intelligence endpoints (public, cacheable — derived from the bundled
1:110m pack, no Siraj site data, no privacy-sensitive content):

- ``GET /api/method/siraj_research.api.natural_earth_vector.country_profile``
  Normalized country facts (capital, population, GDP, area, Arabic name) by
  ISO_A3 code or a WGS84 coordinate.
- ``GET /api/method/siraj_research.api.natural_earth_vector.country_choropleth``
  Data-driven choropleth: aggregates Siraj site records (count / sum / mean
  of a numeric field) onto Natural Earth countries and returns classified
  breaks + a per-country class map for the JS map to render. Respects the
  site doctype's data-group isolation via its normal read permissions.

The map data is public-domain world map data; country profiles require no
authentication (mirroring the existing tile cache), and the site-data
choropleth only aggregates records the caller can already read.
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
from siraj_research.natural_earth_geography import (
    NaturalEarthGeographyError,
    aggregate_site_data,
    choropleth_from_values,
)
from siraj_research.natural_earth_geography import (
    country_profile as build_country_profile,
)

_CACHE_CONTROL = "public, max-age=3600"

# Siraj module name — only doctypes in this module may be aggregated by the
# site-data choropleth (prevents querying arbitrary/unrelated doctypes).
_SIRAJ_MODULE = "Siraj Research"


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


@frappe.whitelist(methods=["GET"])
def country_profile(code: str | None = None, longitude: float | None = None,
                    latitude: float | None = None):
    """Country facts from the bundled Natural Earth pack (public, cacheable).

    Provide either an ISO_A3/boundary ``code`` or a WGS84 ``longitude`` +
    ``latitude``. Returns ``None`` when the code or coordinate does not match
    a known country (e.g. a point over open ocean).
    """
    try:
        profile = build_country_profile(
            code=code or None,
            longitude=longitude,
            latitude=latitude,
        )
    except NaturalEarthGeographyError as exc:
        frappe.throw(str(exc), frappe.ValidationError)
    return profile


def _validate_choropleth_doctype(doctype: str) -> frappe.model.meta.DocumentMeta:
    """Ensure ``doctype`` is a Siraj doctype carrying latitude/longitude."""
    if not doctype:
        frappe.throw("Missing doctype for choropleth.", frappe.ValidationError)
    try:
        meta = frappe.get_meta(doctype)
    except frappe.exceptions.DoesNotExistError:
        frappe.throw(f"Unknown doctype {doctype}.", frappe.ValidationError)
    if meta.module != _SIRAJ_MODULE:
        frappe.throw("Only Siraj doctypes may be aggregated.", frappe.PermissionError)
    if not (meta.has_field("latitude") and meta.has_field("longitude")):
        frappe.throw(
            f"Doctype {doctype} must have latitude/longitude fields.",
            frappe.ValidationError,
        )
    return meta


@frappe.whitelist(methods=["GET"])
def country_choropleth(doctype: str, agg: str = "count",
                       value_field: str | None = None, method: str = "quantile",
                       classes: int = 5):
    """Data-driven choropleth: aggregate Siraj site records onto countries.

    Parameters (form dict):
    - ``doctype`` (required): a Siraj doctype with ``latitude``/``longitude``.
      Only records the caller can read are aggregated (data-group isolation is
      applied via the doctype's normal permission query conditions).
    - ``agg``: ``count`` | ``sum`` | ``mean`` (default ``count``).
    - ``value_field``: numeric field for ``sum``/``mean`` (validated against
      the doctype). Required for ``sum``/``mean``.
    - ``method``: ``quantile`` | ``equal_interval`` (default ``quantile``).
    - ``classes``: number of choropleth classes (2-9, default 5).

    Returns classification breaks, a per-ISO_A3 ``valueByKey`` map, a
    per-ISO_A3 ``classByKey`` map, ``recordCount`` (records aggregated),
    ``unmatchedCount`` (records with no country), and ``matchedCount``
    (distinct countries colored). Callers without read access to the
    doctype receive an empty (fail-closed) choropleth rather than any
    site data.
    """
    meta = _validate_choropleth_doctype(doctype)
    agg = (agg or "count").strip().lower()
    if agg not in ("count", "sum", "mean"):
        frappe.throw(f"Unknown aggregation {agg!r}.", frappe.ValidationError)

    # Form-dict values arrive as strings; coerce ``classes`` to a valid int.
    try:
        classes = int(classes)
    except (TypeError, ValueError):
        frappe.throw("classes must be an integer between 2 and 9.",
                     frappe.ValidationError)
    if not 2 <= classes <= 9:
        frappe.throw("classes must be between 2 and 9.", frappe.ValidationError)

    if agg == "count":
        fields = ["latitude", "longitude", "country"]
    else:
        if not value_field:
            frappe.throw("value_field is required for sum/mean aggregation.",
                         frappe.ValidationError)
        try:
            field = meta.get_field(value_field)
        except Exception:
            field = None
        if not field or field.fieldtype not in ("Int", "Float", "Currency",
                                                "Percent"):
            frappe.throw(f"{value_field} is not a numeric field.",
                         frappe.ValidationError)
        fields = ["latitude", "longitude", "country", value_field]

    try:
        rows = frappe.get_list(
            doctype,
            fields=fields,
            limit_page_length=0,
            ignore_permissions=False,
        )
    except frappe.exceptions.PermissionError:
        # Fail-closed: caller cannot read the doctype -> no site data.
        return {
            "doctype": doctype, "agg": agg, "method": method, "classes": classes,
            "breaks": [], "min": None, "max": None, "empty": True,
            "valueByKey": {}, "classByKey": {}, "matchedCount": 0,
            "unmatchedCount": 0, "recordCount": 0, "source": "no_access",
        }

    records = []
    for row in rows:
        record = {
            "latitude": row.get("latitude"),
            "longitude": row.get("longitude"),
            "country": row.get("country"),
        }
        if agg != "count":
            record["value"] = row.get(value_field)
        records.append(record)

    try:
        values_by_code = aggregate_site_data(records, agg=agg)
    except NaturalEarthGeographyError as exc:
        frappe.throw(str(exc), frappe.ValidationError)

    unmatched = values_by_code.pop("unmatched", 0)
    try:
        payload = choropleth_from_values(values_by_code, method=method, classes=classes)
    except NaturalEarthGeographyError as exc:
        frappe.throw(str(exc), frappe.ValidationError)

    payload.update({
        "doctype": doctype,
        "agg": agg,
        "value_field": value_field,
        "recordCount": len(records),
        "unmatchedCount": unmatched,
        "source": "siraj_site_data",
    })
    return payload
