"""``Geographic Administration`` — one linkable handle per administrative place.

A research record often needs to point at "where" without carrying five Link
fields and without caring whether the country has a municipality tier. The
``Geographic Administration`` DocType solves that: each row stores the full
Country → Community chain, the denormalised ancestry, the canonical field
names required by the module contract (``name_en``, ``name_local``,
``centroid_lat``, ``centroid_lng``, ``source``, ``is_active``) and an optional
geometry link. Any other DocType can then carry a single
``geographic_administration`` Link.

Rows are created in three ways:

* manually from the Desk form (pick any subset of levels);
* automatically by :func:`ensure_for_document` when a coordinate-bearing
  record is saved (the custom field added by the v1_2 patch);
* by :func:`ensure_for_values` from imports, the Explorer or scripts.

The deterministic ``code`` makes creation idempotent: the same chain always
resolves to the same row, so repeated map clicks never create duplicates.

Pure helpers at the top of the module (code generation, canonical payload,
chain selection) are Frappe-free and unit-tested without a bench.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any

try:  # pragma: no cover - exercised inside a bench
    import frappe
except Exception:  # pragma: no cover - pure-Python tests
    frappe = None  # type: ignore[assignment]

from siraj_research.geo_levels import LEVEL_FIELDS, effective_levels, level_spec
from siraj_research.geo_lineage import (
    build_ancestry,
    level_of_doctype,
    record_labels,
)

CODE_PREFIX = "GA:"
MAX_CODE_LENGTH = 140
_SAFE_RE = re.compile(r"[^A-Za-z0-9:/._-]+")


def chain_values(values: Mapping[str, Any] | Any) -> dict[str, Any]:
    """Extract the six hierarchy values from a mapping or a document."""
    if values is None:
        return {field: None for field in LEVEL_FIELDS}
    if isinstance(values, Mapping):
        source = values
    else:
        source = {field: getattr(values, field, None) for field in LEVEL_FIELDS}
    return {field: source.get(field) for field in LEVEL_FIELDS}


def deepest_level(values: Mapping[str, Any]) -> int:
    """Highest level number carrying a value (``0`` when only a country)."""
    deepest = -1
    for spec_level, field in enumerate(LEVEL_FIELDS):
        if values.get(field) not in (None, "", False):
            deepest = spec_level
    return deepest


def canonical_code(values: Mapping[str, Any]) -> str:
    """Deterministic, URL-safe code for a hierarchy chain.

    Example: ``GA:Iraq/IQ-BG/IQ-BG-KR`` (the first segment is the Country
    document name, i.e. the value stored in the Link field). Over-long chains are truncated and
    suffixed with a short SHA-1 so uniqueness survives the ``Data`` length
    limit (140 chars).
    """
    values = chain_values(values)
    segments = [
        _SAFE_RE.sub("-", str(values.get(field)).strip()).strip("-")
        for field in LEVEL_FIELDS
        if values.get(field) not in (None, "", False)
    ]
    body = CODE_PREFIX + "/".join(segments)
    if len(body) <= MAX_CODE_LENGTH:
        return body
    digest = hashlib.sha1(body.encode("utf-8")).hexdigest()[:10].upper()
    return body[: MAX_CODE_LENGTH - 11] + "-" + digest


def canonical_payload(
    values: Mapping[str, Any] | Any,
    *,
    levels: list[dict[str, Any]] | None = None,
    labels: Mapping[str, Mapping[str, str]] | None = None,
    name_en: str | None = None,
    name_local: str | None = None,
    source: str = "manual",
    is_active: bool = True,
    centroid_lat: float | None = None,
    centroid_lng: float | None = None,
) -> dict[str, Any]:
    """The module's canonical field contract for one hierarchy chain."""
    values = chain_values(values)
    deep = deepest_level(values)
    spec = level_spec(max(deep, 0)) or level_spec(0)
    doctype = str(spec["doctype"]) if deep >= 0 else None
    ancestry = build_ancestry(doctype, values, levels, labels=labels) if doctype else {
        "path": "", "labels": "", "level": None, "segments": []
    }
    own_field = str(spec["field"]) if spec else "country"
    resolved_labels = dict(labels or {})
    own_label = resolved_labels.get(own_field, {}) if deep >= 0 else {}
    return {
        "code": canonical_code(values),
        "title": ancestry["labels"] or canonical_code(values),
        "name_en": name_en or own_label.get("en") or (values.get(own_field) if deep >= 0 else None),
        "name_local": name_local or own_label.get("ar") or own_label.get("en"),
        "country": values.get("country"),
        "governorate": values.get("governorate"),
        "district": values.get("district"),
        "municipality": values.get("municipality"),
        "village": values.get("village"),
        "community": values.get("community"),
        "hierarchy_level": deep if deep >= 0 else None,
        "level_key": spec["key"] if spec and deep >= 0 else None,
        "level_label": spec["label_en"] if spec and deep >= 0 else None,
        "ancestry_path": ancestry["path"],
        "ancestry_labels": ancestry["labels"],
        "centroid_lat": centroid_lat,
        "centroid_lng": centroid_lng,
        "source": source or "manual",
        "is_active": 1 if is_active else 0,
        "segments": ancestry["segments"],
    }


def _payload_for_values(values: Mapping[str, Any], **kwargs) -> dict[str, Any]:
    levels = kwargs.pop("levels", None) or effective_levels()
    labels = kwargs.pop("labels", None)
    deep = deepest_level(values)
    if labels is None and deep >= 0:
        doctype = str(level_spec(deep)["doctype"])
        labels = record_labels(doctype, values)
    payload = canonical_payload(values, levels=levels, labels=labels, **kwargs)
    return payload


# ---------------------------------------------------------------------------
# Frappe integration
# ---------------------------------------------------------------------------

def _complete_country(values: dict[str, Any]) -> None:
    """Fill a missing country from the deepest populated ancestor."""
    if values.get("country") or frappe is None:
        return
    for spec_level in range(5, 0, -1):
        field = str(level_spec(spec_level)["field"])
        value = values.get(field)
        if value in (None, "", False):
            continue
        doctype = str(level_spec(spec_level)["doctype"])
        try:
            row = frappe.db.get_value(doctype, value, ["country"], as_dict=True)
        except Exception:  # pragma: no cover
            row = None
        if row and row.get("country"):
            values["country"] = row["country"]
            return


def _deepest_record(values: Mapping[str, Any]) -> dict[str, Any] | None:
    """Read the deepest hierarchy record (for labels, centroid and geometry)."""
    if frappe is None:
        return None
    deep = deepest_level(values)
    if deep < 1:
        return None
    spec = level_spec(deep)
    doctype = str(spec["doctype"])
    name = values.get(str(spec["field"]))
    fields = [f for f in ("name", "label_en", "label_ar", "latitude", "longitude", "boundary")
              if frappe.get_meta(doctype).has_field(f)]
    try:
        return frappe.db.get_value(doctype, name, fields, as_dict=True)
    except Exception:  # pragma: no cover
        return None


def prepare_document(doc) -> dict[str, Any]:
    """Validate and stamp a ``Geographic Administration`` document.

    Called from the controller's ``validate()`` and reused by
    :func:`ensure_for_values`, so manual and automatic rows follow exactly the
    same rules.
    """
    from siraj_research.geo_levels import country_config, validate_chain

    values = chain_values(doc)
    _complete_country(values)
    if not values.get("country"):
        if frappe is not None:
            frappe.throw(
                "Select a Country (or any level whose record has a Country).",
                frappe.ValidationError,
            )
        raise ValueError("country is required")
    for field in LEVEL_FIELDS:
        doc.set(field, values.get(field))

    config = country_config(values.get("country"))
    levels = list(config["levels"])
    deep = deepest_level(values)
    own_field = str(level_spec(max(deep, 0))["field"])
    errors = validate_chain(levels, values, own_field=own_field)
    if errors:
        message = "\n".join(err["message"] for err in errors)
        if frappe is not None:
            frappe.throw(message, frappe.ValidationError, title="Hierarchy configuration")
        raise ValueError(message)

    record = _deepest_record(values)
    labels = record_labels(
        str(level_spec(deep)["doctype"]) if deep >= 0 else None,
        values,
        {
            "en": (record or {}).get("label_en") or doc.get("name_en"),
            "ar": (record or {}).get("label_ar") or doc.get("name_local"),
        },
    )
    payload = canonical_payload(
        values,
        levels=levels,
        labels=labels,
        name_en=doc.get("name_en"),
        name_local=doc.get("name_local"),
        source=doc.get("source") or "manual",
        is_active=doc.get("is_active", 1) in (1, True, "1"),
        centroid_lat=doc.get("centroid_lat") or (record or {}).get("latitude"),
        centroid_lng=doc.get("centroid_lng") or (record or {}).get("longitude"),
    )
    if not doc.get("code"):
        doc.code = payload["code"]
    doc.title = payload["title"]
    doc.hierarchy_level = payload["hierarchy_level"]
    doc.level_key = payload["level_key"]
    doc.level_label = payload["level_label"]
    doc.ancestry_path = payload["ancestry_path"]
    doc.ancestry_labels = payload["ancestry_labels"]
    doc.name_en = payload["name_en"]
    doc.name_local = payload["name_local"]
    if payload["centroid_lat"] is not None:
        doc.centroid_lat = payload["centroid_lat"]
    if payload["centroid_lng"] is not None:
        doc.centroid_lng = payload["centroid_lng"]
    if not doc.get("boundary") and (record or {}).get("boundary"):
        doc.boundary = record["boundary"]
    if not doc.get("source"):
        doc.source = "manual"
    if not doc.get("resolved_on") and frappe is not None:
        from frappe.utils import now_datetime

        doc.resolved_on = now_datetime()
    if not doc.get("resolution_source"):
        doc.resolution_source = "manual"
    return payload


def ensure_for_values(
    values: Mapping[str, Any],
    *,
    source: str = "manual",
    resolution_source: str = "manual",
    create: bool = True,
    **extra: Any,
) -> dict[str, Any]:
    """Return (and optionally create) the row for a chain.

    Returns ``{"name": ..., "created": bool, "code": ...}``. Missing hierarchy
    records are not created here — call ``geo_hierarchy.resolve_and_link``
    first when a coordinate should materialise levels.
    """
    values = chain_values(values)
    _complete_country(values)
    code = canonical_code(values)
    if frappe is None:
        return {"name": None, "created": False, "code": code}
    existing = frappe.db.exists("Geographic Administration", {"code": code})
    if existing:
        return {"name": existing, "created": False, "code": code}
    if not create:
        return {"name": None, "created": False, "code": code}
    if not frappe.has_permission("Geographic Administration", "create"):
        return {"name": None, "created": False, "code": code, "reason": "no_create_permission"}
    doc = frappe.new_doc("Geographic Administration")
    for field in LEVEL_FIELDS:
        doc.set(field, values.get(field))
    doc.source = source
    doc.resolution_source = resolution_source
    for key, value in extra.items():
        if doc.meta.has_field(key) and value not in (None, ""):
            doc.set(key, value)
    doc.insert(ignore_permissions=True)
    return {"name": doc.name, "created": True, "code": doc.code}


def ensure_for_document(doc) -> str | None:
    """Create/reuse the administration row for any record with a hierarchy.

    Returns the Link value (or ``None``). Never raises: a missing field or an
    incomplete chain must not block saving a research record.
    """
    if frappe is None or doc is None:
        return None
    meta = getattr(doc, "meta", None)
    if meta is None or not meta.has_field("geographic_administration"):
        return None
    existing = doc.get("geographic_administration")
    if existing and frappe.db.exists("Geographic Administration", existing):
        return existing
    values = chain_values(doc)
    if deepest_level(values) < 0:
        return None
    values["country"] = values.get("country") or _country_from_record(doc, values)
    if not values.get("country"):
        return None
    try:
        result = ensure_for_values(
            values,
            source=_source_for_document(doc),
            resolution_source="local",
            create=True,
        )
    except Exception:  # pragma: no cover - defensive during save
        return None
    if result.get("name"):
        doc.set("geographic_administration", result["name"])
        return result["name"]
    return None


def _country_from_record(doc, values: Mapping[str, Any]) -> str | None:
    for spec_level in range(5, 0, -1):
        field = str(level_spec(spec_level)["field"])
        value = values.get(field)
        if not value:
            continue
        doctype = str(level_spec(spec_level)["doctype"])
        try:
            return frappe.db.get_value(doctype, value, "country")
        except Exception:  # pragma: no cover
            continue
    return None


def _source_for_document(doc) -> str:
    source_kind = str(doc.get("source_kind") or "").strip().lower()
    if source_kind in ("online", "manual", "imported"):
        return {"online": "online", "manual": "manual", "imported": "gadm"}.get(source_kind, "manual")
    return "manual"


def payload_for(name: str) -> dict[str, Any]:
    """Read a row and return its canonical payload (permission-checked)."""
    if frappe is None:
        return {}
    if not frappe.has_permission("Geographic Administration", "read"):
        frappe.throw("Not permitted to read Geographic Administration.", frappe.PermissionError)
    doc = frappe.get_doc("Geographic Administration", name)
    return {
        "name": doc.name,
        "code": doc.code,
        "title": doc.title,
        "name_en": doc.name_en,
        "name_local": doc.name_local,
        "country": doc.country,
        "governorate": doc.governorate,
        "district": doc.district,
        "municipality": doc.municipality,
        "village": doc.village,
        "community": doc.community,
        "hierarchy_level": doc.hierarchy_level,
        "level_key": doc.level_key,
        "level_label": doc.level_label,
        "ancestry_path": doc.ancestry_path,
        "ancestry_labels": doc.ancestry_labels,
        "centroid_lat": doc.centroid_lat,
        "centroid_lng": doc.centroid_lng,
        "boundary": doc.boundary,
        "source": doc.source,
        "is_active": doc.is_active,
        "resolved_on": str(doc.resolved_on or ""),
        "resolution_source": doc.resolution_source,
    }


if frappe is not None:  # pragma: no cover - bench only

    @frappe.whitelist()
    def get_geographic_administration(name):
        """Return one administration row as a canonical payload."""
        return payload_for(name)

    @frappe.whitelist()
    def ensure_geographic_administration(country, governorate=None, district=None,
                                         municipality=None, village=None,
                                         community=None, source="manual"):
        """Idempotently create/reuse the row for a chain (Link target)."""
        if not frappe.has_permission("Geographic Administration", "create"):
            frappe.throw("Not permitted to create Geographic Administration.", frappe.PermissionError)
        from siraj_research.api.throttle import guard

        guard("ga_ensure")
        values = {
            "country": country,
            "governorate": governorate,
            "district": district,
            "municipality": municipality,
            "village": village,
            "community": community,
        }
        result = ensure_for_values(values, source=source or "manual")
        if not result.get("name"):
            frappe.throw("Could not create Geographic Administration for this chain.")
        return {**result, "payload": payload_for(result["name"])}

    @frappe.whitelist()
    def resolve_geographic_administration(latitude, longitude, create_missing=1,
                                         use_online=0):
        """Resolve a coordinate and return the matching administration row.

        The hierarchy resolution is exactly the one used by forms and the
        Explorer (local polygons first); no separate code path can drift.
        """
        if not frappe.has_permission("Place", "read"):
            frappe.throw("Not permitted to resolve coordinates.", frappe.PermissionError)
        from siraj_research.api.throttle import guard

        guard("ga_resolve")
        from siraj_research.geo_hierarchy_ui import display_resolution

        create = str(create_missing) in ("1", "true", "True")
        result = display_resolution(
            latitude,
            longitude,
            create_missing=create,
            use_online=str(use_online) in ("1", "true", "True"),
        )
        if result.get("error"):
            return {"error": result["error"], "resolution": result}
        by_field = result.get("by_field") or {}
        values = {
            field: ((by_field.get(field) or {}).get("name")
                    if (by_field.get(field) or {}).get("status") == "linked" else None)
            for field in LEVEL_FIELDS
        }
        if not values.get("country"):
            return {"error": "unresolved", "resolution": result}
        ensured = ensure_for_values(
            values,
            source="online" if use_online else "osm",
            resolution_source="online" if use_online else "local",
            create=create,
            centroid_lat=result.get("lat"),
            centroid_lng=result.get("lon"),
        )
        return {
            "name": ensured.get("name"),
            "created": ensured.get("created"),
            "payload": payload_for(ensured["name"]) if ensured.get("name") else None,
            "resolution": result,
        }
