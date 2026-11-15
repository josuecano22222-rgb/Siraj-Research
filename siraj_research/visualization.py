"""Permission-aware data for the SIRAJ visual explorer.

Only explicit, permission-level-zero fields are returned. get_list applies Frappe's
user and document permissions; neither SQL nor get_all bypasses them here.
"""
from __future__ import annotations

import math

import frappe
from frappe import _

from siraj_research.report_access import readable_rows

# Labels use the actual title fields, not the series identifier, where available.
ENTITIES = {
    "Person": "display_name",
    "Institution": "display_name",
    "Place": "display_name",
    "Event": "display_name",
    "Source": "display_name",
    "Military Unit": "unit_name",
    "Operational Deployment": "deployment_name",
}
GEO_TYPES = ("Person", "Institution", "Place", "Event", "Military Unit", "Operational Deployment")
GRAPH_TYPES = ("Person", "Institution", "Place", "Event", "Source")
STRUCTURES = {
    "people": ("Person", ("nationality", "classification", "workflow_state")),
    "institutions": ("Institution", ("institution_type", "country", "governance_system")),
    "places": ("Place", ("country", "place_type", "geo_precision")),
    "events": ("Event", ("event_type", "place", "documentation_level")),
    "relationships": ("Relationship", ("relationship_type", "direction", "authentication_level")),
    "sources": ("Source", ("source_type", "source_reliability", "workflow_state")),
    "units": ("Military Unit", ("region", "division", "echelon")),
}
MAX_RECORDS = 1500  # per type, bounded to keep the Desk responsive


def _records(doctype, fields):
    if not frappe.has_permission(doctype, "read"):
        return [], False
    rows = frappe.get_list(
        doctype, fields=list(dict.fromkeys(["name", *fields])),
        order_by="name asc", page_length=MAX_RECORDS + 1,
    )
    # get_list applies query-level restrictions; the additional document check
    # respects custom has_permission hooks which are not always expressible in SQL.
    visible = [row for row in rows[:MAX_RECORDS]
               if frappe.has_permission(doctype, "read", doc=row["name"], throw=False)]
    return visible, len(rows) > MAX_RECORDS


def _entity_rows(types, extra_fields=()):
    nodes, truncated = [], []
    for doctype in types:
        title = ENTITIES[doctype]
        rows, cut = _records(doctype, [title, *extra_fields])
        if cut:
            truncated.append(doctype)
        for row in rows:
            nodes.append({"doctype": doctype, "name": row["name"], "label": row.get(title) or row["name"],
                          **{field: row.get(field) for field in extra_fields}})
    return nodes, truncated


def _valid_point(lat, lon):
    try:
        lat, lon = float(lat), float(lon)
        # Frappe Float fields commonly default to zero. 0,0 is ambiguous and
        # cannot safely be distinguished from an unset pair in this schema.
        return math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180 and (lat != 0 or lon != 0)
    except (TypeError, ValueError):
        return False


@frappe.whitelist()
def geographic_data():
    """Only record-owned coordinates are shown; linked Place coordinates are never copied."""
    nodes, truncated = _entity_rows(GEO_TYPES, ("latitude", "longitude", "geo_precision", "geocoding_method", "geo_uncertainty_m", "geometry_source"))
    points = [node for node in nodes if _valid_point(node["latitude"], node["longitude"])]
    return {"points": points, "truncated": truncated, "limit": MAX_RECORDS}


@frappe.whitelist()
def relationship_data():
    """Only expose edges whose relationship and both endpoint records are visible."""
    nodes, truncated = _entity_rows(GRAPH_TYPES)
    visible = {(node["doctype"], node["name"]) for node in nodes}
    rows, cut = _records("Relationship", ["relationship_type", "subject_type", "subject", "object_type", "object", "direction", "description", "workflow_state"])
    if cut:
        truncated.append("Relationship")
    edges = []
    for row in rows:
        source = (row.get("subject_type"), row.get("subject"))
        target = (row.get("object_type"), row.get("object"))
        if source in visible and target in visible:
            edges.append({"name": row["name"], "source": list(source), "target": list(target),
                          "type": row.get("relationship_type") or "", "direction": row.get("direction") or "",
                          "description": row.get("description") or "", "state": row.get("workflow_state") or ""})
    return {"nodes": nodes, "edges": edges, "truncated": truncated, "limit": MAX_RECORDS}


# The original structure view folds wide branches instead of dropping them.
STRUCTURE_MAX_CHILDREN = 24


def _structure_counts(rows, dimensions):
    """Count all permitted rows in one streaming pass, without a record cutoff."""
    root = {"count": 0, "groups": {}}
    for row in rows:
        # get_list removes fields hidden by Frappe field-level permissions.
        # Never misreport restricted values as "not recorded".
        if any(field not in row for field in dimensions):
            frappe.throw(_("A structure grouping field is not readable."), frappe.PermissionError)
        node = root
        node["count"] += 1
        for field in dimensions:
            value = row.get(field)
            key = str(value) if value not in (None, "") else None
            node = node["groups"].setdefault(key, {"count": 0, "groups": {}})
            node["count"] += 1
    return root


def _structure_children(node, dimensions, depth=0):
    if depth >= len(dimensions):
        return []
    grouped = sorted(node["groups"].items(), key=lambda item: (-item[1]["count"], (item[0] or "").casefold()))
    budget = min(60, STRUCTURE_MAX_CHILDREN * 2) if depth == 0 else max(5, STRUCTURE_MAX_CHILDREN // (depth + 1))
    children = []
    for key, child in grouped[:budget]:
        children.append({"label": key if key is not None else _("Not recorded"),
                         "field": dimensions[depth], "count": child["count"],
                         "group_count": len(child["groups"]),
                         "children": _structure_children(child, dimensions, depth + 1)})
    tail = grouped[budget:]
    if tail:
        children.append({"label": _("{0} smaller groups").format(len(tail)),
                         "field": dimensions[depth], "count": sum(child["count"] for _, child in tail),
                         "folded_groups": len(tail), "group_count": 0, "children": []})
    return children


@frappe.whitelist()
def structure_data(source="people"):
    """Count every readable record; fold wide branches without losing counts.

    This synchronous scan can be expensive for large sites or custom permission
    hooks. Counts represent the current user's visible records, not global totals.
    """
    if source not in STRUCTURES:
        frappe.throw(_("Unknown structure source"), frappe.ValidationError)
    doctype, dimensions = STRUCTURES[source]
    if not frappe.has_permission(doctype, "read"):
        frappe.throw(_("Not permitted to read {0}").format(_(doctype)), frappe.PermissionError)
    root = _structure_counts(readable_rows(doctype, dimensions), dimensions)
    meta = frappe.get_meta(doctype)
    labels = [meta.get_field(field).label or field for field in dimensions]
    return {"doctype": doctype, "dimensions": labels, "count": root["count"], "truncated": False,
            "group_count": len(root["groups"]), "children": _structure_children(root, dimensions)}
