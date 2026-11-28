"""Unified hierarchical location-cascade API.

A single authoritative entry point that turns a location into the full
administrative chain (Country → Governorate → District → Municipality →
Village → Community) and applies Natural Earth country enrichment. It accepts
either **coordinates** (location data entered) or a **selected Place record**
(a location selected), so any DocType with the location field group can
auto-populate its country/province/city fields from one call.

- ``GET /api/method/siraj_research.api.location_cascade.resolve_location_chain``
  resolve by ``latitude``/``longitude`` **or** by ``place_doctype`` +
  ``place_name``. Optional ``doctype`` returns the resolved values mapped onto
  that DocType's fields (via ``geo_hierarchy_ui.field_values``).

The country level is enriched (and globally fallback-resolved) from the
bundled Natural Earth pack: when a coordinate falls outside Siraj's scoped
reference countries, the country is still identified and given its Arabic
name, ISO codes and population.
"""

from __future__ import annotations

import frappe

from siraj_research.geo_hierarchy_ui import (
    build_cfg_from_meta,
    display_resolution,
    field_values,
)
from siraj_research.natural_earth_geography import enrich_chain_country


def _as_bool(value) -> bool:
    return str(value) in ("1", "true", "True", "yes", "on")


def resolve_chain(latitude, longitude, *, create_missing: bool = True,
                  use_online: bool = False) -> dict:
    """Resolve a coordinate to the full chain, with country enrichment."""
    result = display_resolution(
        latitude, longitude,
        create_missing=create_missing, use_online=use_online,
    )
    if result.get("error"):
        return result
    result["country_enrichment"] = enrich_chain_country(result)
    return result


def resolve_for_place(place_doctype: str, place_name: str, *,
                      create_missing: bool = True,
                      use_online: bool = False) -> dict:
    """Resolve a selected Place record to the full chain.

    Fetches the Place's own coordinates and resolves from them, so picking a
    location (not just typing coordinates) auto-populates the hierarchy.
    """
    if not place_doctype or not place_name:
        return {"error": "Missing place_doctype or place_name", "levels": [],
                "by_field": {}, "gaps": [], "warnings": ["missing_place"]}
    try:
        place = frappe.get_doc(place_doctype, place_name)
    except frappe.exceptions.DoesNotExistError:
        return {"error": "Place not found", "levels": [], "by_field": {},
                "gaps": [], "warnings": ["place_not_found"]}
    lat = place.get("latitude")
    lon = place.get("longitude")
    if lat in (None, "") or lon in (None, ""):
        return {"error": "Place has no coordinates", "levels": [],
                "by_field": {}, "gaps": [], "warnings": ["place_no_coordinates"]}
    result = resolve_chain(lat, lon, create_missing=create_missing,
                           use_online=use_online)
    result["place"] = {
        "doctype": place_doctype, "name": place_name,
        "latitude": lat, "longitude": lon,
    }
    return result


@frappe.whitelist(methods=["GET"])
def resolve_location_chain(latitude=None, longitude=None, place_doctype=None,
                           place_name=None, doctype=None, create_missing=1,
                           use_online=0):
    """Resolve a location (coordinates or a selected Place) to the full chain.

    Parameters (form dict):
    - ``latitude`` / ``longitude``: a WGS84 point (location data entered).
    - ``place_doctype`` + ``place_name``: a selected Place record.
    - ``doctype``: optional target DocType; the response includes
      ``field_values`` mapped onto that DocType's location fields.
    - ``create_missing`` / ``use_online``: forwarded to the resolver.

    Returns the bilingual chain (``levels``, ``by_field``, ``gaps``), the
    Natural Earth ``country_enrichment``, and (when ``doctype`` is given)
    ``field_values`` ready to apply to a form.
    """
    if not frappe.has_permission("Place", "read"):
        frappe.throw("Not permitted to resolve locations.",
                     frappe.PermissionError)

    if place_doctype and place_name:
        result = resolve_for_place(
            place_doctype, place_name,
            create_missing=_as_bool(create_missing),
            use_online=_as_bool(use_online),
        )
    elif latitude is not None and longitude is not None:
        result = resolve_chain(
            latitude, longitude,
            create_missing=_as_bool(create_missing),
            use_online=_as_bool(use_online),
        )
    else:
        frappe.throw(
            "Provide latitude/longitude or place_doctype/place_name.",
            frappe.ValidationError,
        )

    if result.get("error"):
        return result

    response = dict(result)
    response["source"] = "place" if (place_doctype and place_name) else "coordinate"
    if doctype:
        cfg = build_cfg_from_meta(doctype)
        response["field_values"] = field_values(doctype, result)
        response["cfg"] = cfg
    return response
