"""Shared full-hierarchy resolution, display and form-fill helpers.

This is the single server-side entry point used by Desk forms, the Siraj
Explorer and document hooks. It turns a coordinate into a bilingual
six-level chain (Country → Governorate → District → Municipality → Village →
Community), links/reuses hierarchy records when permitted, reports missing
levels as gaps, and produces values suitable for any DocType's fields.
"""
from __future__ import annotations

from typing import Any

try:  # pragma: no cover - pure tests run without a bench
	import frappe
except Exception:  # pragma: no cover
	frappe = None  # type: ignore[assignment]

from siraj_research.record_icons import COORDINATE_DOCS

LEVEL_META: tuple[dict[str, str], ...] = (
	{"field": "country", "doctype": "Country", "label": "Country", "label_ar": "الدولة"},
	{"field": "governorate", "doctype": "Governorate", "label": "Governorate", "label_ar": "المحافظة"},
	{"field": "district", "doctype": "District", "label": "District", "label_ar": "المنطقة"},
	{"field": "municipality", "doctype": "Municipality", "label": "Municipality", "label_ar": "البلدية"},
	{"field": "village", "doctype": "Village", "label": "Village", "label_ar": "القرية"},
	{"field": "community", "doctype": "Community", "label": "Community", "label_ar": "المجتمع"},
)


def _as_number(value, limit: float) -> float | None:
	try:
		number = float(value)
	except (TypeError, ValueError):
		return None
	return number if -limit <= number <= limit else None


def _level_row(meta: dict, entry: dict | None, gap: dict | None,
               *, linked_name: str | None = None) -> dict:
	entry = dict(entry or {})
	gap = dict(gap or {})
	label_en = str(entry.get("label_en") or entry.get("name_en") or linked_name or "").strip()
	label_ar = str(entry.get("label_ar") or entry.get("name_ar") or "").strip()
	code = str(entry.get("code") or entry.get("pcode") or "").strip()
	name = linked_name or code or label_en
	if name:
		status = "linked" if linked_name else "resolved"
	else:
		status = "gap"
	return {
		"level": int(meta.get("level", 0)),
		"field": meta["field"],
		"doctype": meta["doctype"],
		"label": meta["label"],
		"label_ar": meta["label_ar"],
		"name": name or None,
		"label_en": label_en or None,
		"label_ar_value": label_ar or None,
		"code": code or None,
		"pcode": str(entry.get("pcode") or "").strip() or None,
		"confidence": entry.get("confidence") or ("high" if name else None),
		"source": entry.get("source") or (gap.get("reason") if status == "gap" else None),
		"status": status,
	}


def _build_levels(linked: dict) -> list[dict]:
	hierarchy = {str(row.get("field")): row for row in linked.get("hierarchy") or []}
	gaps = {str(row.get("field")): row for row in linked.get("gaps") or []}
	levels: list[dict] = []
	for index, meta in enumerate(LEVEL_META):
		field = meta["field"]
		row = dict(meta, level=index)
		if field == "country":
			country = dict(linked.get("country") or {})
			entry = {
				"label_en": country.get("label_en"),
				"label_ar": country.get("label_ar"),
				"pcode": country.get("code"),
				"confidence": "high" if country.get("name") else None,
			}
			if not entry["label_en"]:
				entry["label_en"] = country.get("name")
			levels.append(_level_row(row, entry, gaps.get(field),
			                         linked_name=country.get("name")))
			continue
		levels.append(_level_row(row, hierarchy.get(field), gaps.get(field),
		                         linked_name=(hierarchy.get(field) or {}).get("name")))
	return levels


def display_resolution(latitude, longitude, *, create_missing: bool = True,
                       use_online: bool = False) -> dict:
    """Resolve a point and return a display-ready hierarchical result."""
    from siraj_research.geo_hierarchy import resolve_and_link

    lat, lon = _as_number(latitude, 90), _as_number(longitude, 180)
    if lat is None or lon is None:
        return {"error": "Invalid coordinates", "levels": [], "by_field": {},
                "warnings": ["invalid_coordinates"]}
    linked = resolve_and_link(lat, lon, create_missing=create_missing,
                              use_online=bool(use_online))
    raw = dict(linked.get("raw") or {})
    levels = _build_levels(linked)
    by_field = {row["field"]: row for row in levels}
    place = dict(raw.get("nearest_place") or {})
    nearest = place.get("name_ar") or place.get("name_en") or None
    result = {
        "lat": lat,
        "lon": lon,
        "levels": levels,
        "by_field": by_field,
        "gaps": [row for row in levels if row["status"] == "gap"],
        "nearest_place": place or None,
        "nearest_place_name": nearest,
        "warnings": list(linked.get("warnings") or []),
        "provenance": list(linked.get("provenance") or []),
        "ambiguous": bool(linked.get("ambiguous")),
        "on_land": bool(linked.get("on_land")),
        "dataset": raw.get("dataset"),
        "source": "online" if use_online else "local",
        "resolved_count": sum(1 for row in levels if row["status"] != "gap"),
        "deepest_level": max([row["level"] for row in levels if row["status"] != "gap"],
                             default=-1),
    }
    result["text_en"] = format_chain(result, language="en")
    result["text_ar"] = format_chain(result, language="ar")
    return result


def format_chain(result: dict, *, language: str = "en") -> str:
    parts = []
    for row in result.get("levels") or []:
        label = (row.get("label_ar_value") if language == "ar" else row.get("label_en")) \
            or (row.get("label_ar") if language == "ar" else row.get("label"))
        parts.append(label or "—")
    return " › ".join(parts)


def field_values(doctype: str, result: dict) -> dict[str, Any]:
    """Map a resolved chain onto the configured fields of any DocType."""
    cfg = dict(COORDINATE_DOCS.get(doctype) or {})
    mapping = dict(cfg.get("admin_fields") or {})
    if not mapping:
        # Graceful fallback for custom DocTypes using conventional names.
        mapping = {meta["field"]: meta["field"] for meta in LEVEL_META}
    values: dict[str, Any] = {}
    meta = frappe.get_meta(doctype) if frappe is not None else None
    for chain_key, fieldname in mapping.items():
        if not fieldname:
            continue
        if chain_key == "place_name":
            value = result.get("nearest_place_name")
        else:
            row = (result.get("by_field") or {}).get(chain_key) or {}
            # A Link field only accepts a real DocType name. Falling back to a
            # P-Code/label here passes client validation but fails Frappe's
            # save-time _validate_links with LinkValidationError.
            linked_name = row.get("name") if row.get("status") == "linked" else None
            value = linked_name
            if value is None and meta is not None and meta.has_field(fieldname):
                field = meta.get_field(fieldname)
                if field is not None and getattr(field, "fieldtype", None) != "Link":
                    value = row.get("code") or row.get("label_en")
        if value:
            values[fieldname] = value
    return values


def build_cfg_from_meta(doctype: str) -> dict:
    """Derive a COORDINATE_DOCS-style config from any DocType's meta.

    Lets the cascade cover **any** DocType that carries the location field
    group (latitude/longitude + the standard administrative Link fields), not
    only the six registered in ``COORDINATE_DOCS``. Returns an empty dict when
    the DocType has no coordinate fields. Reuses the registered config when
    the DocType is already known.
    """
    if not doctype:
        return {}
    registered = dict(COORDINATE_DOCS.get(doctype) or {})
    if registered:
        return registered
    if frappe is None:
        return {}
    try:
        meta = frappe.get_meta(doctype)
    except Exception:  # pragma: no cover - defensive
        return {}
    if not (meta.has_field("latitude") and meta.has_field("longitude")):
        return {}
    admin_fields = {}
    for level_field in ("country", "governorate", "district", "municipality",
                        "village", "community"):
        if meta.has_field(level_field):
            admin_fields[level_field] = level_field
    if meta.has_field("place_name"):
        admin_fields["place_name"] = "place_name"
    elif meta.has_field("location"):
        admin_fields["place_name"] = "location"
    if not admin_fields:
        return {}
    linked_place_field = None
    for candidate in ("place", "birthplace", "linked_place"):
        if meta.has_field(candidate):
            linked_place_field = candidate
            break
    return {
        "map_field": "geo_point" if meta.has_field("geo_point") else None,
        "origin_confirmed_field": "coordinate_origin_confirmed",
        "lat_field": "latitude",
        "lon_field": "longitude",
        "uncertainty_field": "geo_uncertainty_m",
        "linked_place_field": linked_place_field,
        "admin_fields": admin_fields,
    }


def apply_to_doc(doc, *, result: dict | None = None, create_missing: bool = True,
                 use_online: bool = False) -> dict:
    """Fill only empty hierarchy fields on ``doc``; never overwrite research."""
    if doc is None:
        return {"updated": [], "result": result or {}}
    doctype = getattr(doc, "doctype", None)
    cfg = dict(COORDINATE_DOCS.get(doctype) or {})
    lat_field = cfg.get("lat_field") or "latitude"
    lon_field = cfg.get("lon_field") or "longitude"
    lat = getattr(doc, lat_field, None)
    lon = getattr(doc, lon_field, None)
    if result is None:
        if lat in (None, "") or lon in (None, ""):
            return {"updated": [], "skipped": "no_coordinates"}
        result = display_resolution(lat, lon, create_missing=create_missing,
                                    use_online=use_online)
    if result.get("error"):
        return {"updated": [], "result": result}
    meta = frappe.get_meta(doctype) if frappe is not None else None
    updated: list[str] = []
    for fieldname, value in field_values(doctype, result).items():
        if meta is not None and not meta.has_field(fieldname):
            continue
        if getattr(doc, fieldname, None) in (None, ""):
            setattr(doc, fieldname, value)
            updated.append(fieldname)
    if meta is not None:
        for fieldname, value in (("geocoding_method", "administrative"),
                                 ("geometry_source", "polygon_resolver")):
            if meta.has_field(fieldname) and not getattr(doc, fieldname, None):
                setattr(doc, fieldname, value)
                updated.append(fieldname)
    return {"updated": updated, "result": result}


if frappe is not None:  # pragma: no cover - bench only
	@frappe.whitelist()
	def hierarchy_for_point(latitude, longitude, create_missing=1, use_online=0):
		"""Full bilingual hierarchy for map clicks, manual entry and Explorer."""
		if not frappe.has_permission("Place", "read"):
			frappe.throw("Not permitted to resolve coordinates.", frappe.PermissionError)
		return display_resolution(
			latitude, longitude,
			create_missing=str(create_missing) in ("1", "true", "True"),
			use_online=str(use_online) in ("1", "true", "True"),
		)
