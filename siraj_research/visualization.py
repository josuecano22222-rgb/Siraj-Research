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
    "Command Region": "region_name",
}
# Explicit, low-sensitivity fields already readable on each record's form.
DETAIL_FIELDS = {
    "Person": ("nationality", "classification", "person_status", "current_position_as_stated", "workflow_state", "authentication_level"),
    "Institution": ("institution_type", "country", "governance_system", "workflow_state", "authentication_level"),
    "Place": ("place_type", "country", "governorate", "workflow_state", "authentication_level"),
    "Event": ("event_type", "start_date_as_stated", "place", "documentation_level", "workflow_state"),
    "Source": ("source_type", "publisher", "source_reliability", "workflow_state"),
    "Military Unit": ("echelon", "status", "region", "division", "direct_personnel", "workflow_state"),
    "Relationship": ("relationship_type", "direction", "description", "authentication_level", "workflow_state"),
    "Command Region": ("region_type", "country", "workflow_state"),
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
    "forces": ("Military Unit", ("echelon", "status", "classification")),
}
STRUCTURE_MAX_LEAVES = 48


def _records(doctype, fields):
    """Read all list- and document-visible records, without silently cutting off the atlas."""
    return list(readable_rows(doctype, fields)), False


def _entity_rows(types, extra_fields=(), include_details=False):
    nodes, truncated = [], []
    for doctype in types:
        title = ENTITIES[doctype]
        details = DETAIL_FIELDS.get(doctype, ()) if include_details else ()
        rows, cut = _records(doctype, [title, *extra_fields, *details])
        meta = frappe.get_meta(doctype) if details else None
        if cut:
            truncated.append(doctype)
        for row in rows:
            nodes.append({"doctype": doctype, "name": row["name"], "label": row.get(title) or row["name"],
                          **{field: row.get(field) for field in extra_fields},
                          "details": {meta.get_field(field).label or field: row.get(field)
                                      for field in details if field in row}})
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
    return {"points": points, "truncated": truncated}


@frappe.whitelist()
def relationship_data():
    """Only expose edges whose relationship and both endpoint records are visible."""
    nodes, truncated = _entity_rows(GRAPH_TYPES, include_details=True)
    visible = {(node["doctype"], node["name"]) for node in nodes}
    rows, cut = _records("Relationship", ["relationship_type", "subject_type", "subject", "object_type", "object", "direction", "description", "workflow_state", "is_current", "end_date", "authentication_level", "primary_source"])
    if cut:
        truncated.append("Relationship")
    edges = []
    for row in rows:
        source = (row.get("subject_type"), row.get("subject"))
        target = (row.get("object_type"), row.get("object"))
        if source in visible and target in visible:
            edges.append({"name": row["name"], "source": list(source), "target": list(target),
                          "type": row.get("relationship_type") or "", "direction": row.get("direction") or "",
                          "description": row.get("description") or "", "state": row.get("workflow_state") or "",
                          "is_current": row.get("is_current"), "end_date": row.get("end_date"),
                          "authentication_level": row.get("authentication_level") or "", "primary_source": row.get("primary_source") or ""})
    return {"nodes": nodes, "edges": edges, "truncated": truncated}


@frappe.whitelist()
def record_detail(doctype, name):
    """Return a small permission-filtered dossier for a structure record leaf."""
    if doctype not in DETAIL_FIELDS or not isinstance(name, str) or not name:
        frappe.throw(_("Unknown record"), frappe.ValidationError)
    if not frappe.has_permission(doctype, "read"):
        frappe.throw(_("Not permitted to read {0}").format(_(doctype)), frappe.PermissionError)
    title = ENTITIES.get(doctype, "display_name")
    rows = readable_rows(doctype, (title, *DETAIL_FIELDS[doctype]), filters={"name": name})
    row = next(rows, None)
    if row is None:
        frappe.throw(_("Record not found or not permitted"), frappe.PermissionError)
    meta = frappe.get_meta(doctype)
    return {"doctype": doctype, "name": row["name"], "label": row.get(title) or row["name"],
            "details": {meta.get_field(field).label or field: row.get(field)
                        for field in DETAIL_FIELDS[doctype] if field in row}}


# The original structure view folds wide branches instead of dropping them.
STRUCTURE_MAX_CHILDREN = 24


def _structure_counts(rows, dimensions, title_field=None):
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
        if title_field is not None:
            records = node.setdefault("records", [])
            if len(records) < STRUCTURE_MAX_LEAVES:
                records.append({"name": row["name"], "label": row.get(title_field) or row["name"]})
    return root


def _structure_children(node, dimensions, depth=0):
    if depth >= len(dimensions):
        records = node.get("records", [])
        children = [{"label": record["label"], "name": record["name"], "record": True,
                     "count": 1, "group_count": 0, "children": []} for record in records]
        if records and node["count"] > len(records):
            missing = node["count"] - len(records)
            children.append({"label": _("{0} more records").format(missing), "count": missing,
                             "folded_records": missing, "group_count": 0, "children": []})
        return children
    grouped = sorted(node["groups"].items(), key=lambda item: (-item[1]["count"], (item[0] or "").casefold()))
    budget = min(60, STRUCTURE_MAX_CHILDREN * 2) if depth == 0 else max(5, STRUCTURE_MAX_CHILDREN // (depth + 1))
    children = []
    for key, child in grouped[:budget]:
        children.append({"label": key if key is not None else _("Not recorded"), "key": key,
                         "field": dimensions[depth], "count": child["count"],
                         "group_count": len(child["groups"]),
                         "record_count": child["count"] if depth == len(dimensions) - 1 else 0,
                         "children": _structure_children(child, dimensions, depth + 1)})
    tail = grouped[budget:]
    if tail:
        children.append({"label": _("{0} smaller groups").format(len(tail)),
                         "field": dimensions[depth], "count": sum(child["count"] for _, child in tail),
                         "folded_groups": len(tail), "group_count": 0, "children": []})
    return children


def _hierarchy(doctype, title_field, parent_field):
    """Build a permission-visible command tree; unreadable parents become roots.

    Each record counts once, including the record represented by a branch. Broken
    links and cycles are detached rather than exposing inaccessible parent IDs.
    """
    if not frappe.has_permission(doctype, "read"):
        frappe.throw(_("Not permitted to read {0}").format(_(doctype)), frappe.PermissionError)
    rows = list(readable_rows(doctype, (title_field, parent_field)))
    if any(parent_field not in row for row in rows):
        frappe.throw(_("A structure grouping field is not readable."), frappe.PermissionError)
    by_name = {row["name"]: row for row in rows}
    parents = {name: row.get(parent_field) if row.get(parent_field) in by_name else None
               for name, row in by_name.items()}
    # Detach one edge in every cycle, deterministically by name.
    done = set()
    for name in sorted(parents):
        trail, index, cur = [], {}, name
        while cur and cur not in done and cur not in index:
            index[cur] = len(trail)
            trail.append(cur)
            cur = parents[cur]
        if cur in index:
            parents[min(trail[index[cur]:])] = None
        done.update(trail)
    nodes = {name: {"label": row.get(title_field) or name, "name": name,
                    "target": True, "count": 1, "group_count": 0, "children": []}
             for name, row in by_name.items()}
    root = {"count": 0, "children": []}
    for name, node in nodes.items():
        parent = parents[name]
        (nodes[parent] if parent else root)["children"].append(node)
    stack = [(root, False, 0)]
    while stack:
        node, visited, depth = stack.pop()
        if not visited:
            stack.append((node, True, depth))
            stack.extend((child, False, depth + 1) for child in node["children"])
            continue
        children = sorted(node["children"], key=lambda child: (-child["count"], child["label"].casefold(), child["name"]))
        node["count"] = (0 if node is root else 1) + sum(child["count"] for child in children)
        node["group_count"] = len(children)
        budget = min(60, STRUCTURE_MAX_CHILDREN * 2) if depth == 0 else max(5, STRUCTURE_MAX_CHILDREN // (depth + 1))
        tail = children[budget:]
        node["children"] = children[:budget]
        if tail:
            node["children"].append({"label": _("{0} smaller groups").format(len(tail)),
                                     "count": sum(child["count"] for child in tail),
                                     "folded_groups": len(tail), "group_count": 0, "children": []})
    return {"doctype": doctype, "dimensions": [_('Command hierarchy')], "count": root["count"],
            "truncated": False, "group_count": root["group_count"], "children": root["children"]}


@frappe.whitelist()
def structure_data(source="people"):
    """Count every readable record; fold wide branches without losing counts.

    This synchronous scan can be expensive for large sites or custom permission
    hooks. Counts represent the current user's visible records, not global totals.
    """
    if source == "units":
        return _hierarchy("Military Unit", "unit_name", "parent_unit")
    if source == "regions":
        return _hierarchy("Command Region", "region_name", "parent_region")
    if source not in STRUCTURES:
        frappe.throw(_("Unknown structure source"), frappe.ValidationError)
    doctype, dimensions = STRUCTURES[source]
    if not frappe.has_permission(doctype, "read"):
        frappe.throw(_("Not permitted to read {0}").format(_(doctype)), frappe.PermissionError)
    title = ENTITIES.get(doctype, "display_name")
    root = _structure_counts(readable_rows(doctype, (*dimensions, title)), dimensions, title)
    meta = frappe.get_meta(doctype)
    labels = [meta.get_field(field).label or field for field in dimensions]
    return {"doctype": doctype, "dimensions": labels, "count": root["count"], "truncated": False,
            "group_count": len(root["groups"]), "children": _structure_children(root, dimensions)}
