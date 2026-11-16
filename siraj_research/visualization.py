"""Permission-aware data for the SIRAJ visual explorer.

Only explicit, permission-level-zero fields are returned. get_list applies Frappe's
user and document permissions; neither SQL nor get_all bypasses them here.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

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
    "Mission": "mission_name",
    "Training Exercise": "exercise_name",
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
    "Operational Deployment": ("deployment_type", "status", "location", "workflow_state"),
    "Mission": ("mission_type", "status", "area", "workflow_state"),
    "Training Exercise": ("training_type", "assessment", "location", "workflow_state"),
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


_COORDINATE_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫", "01234567890123456789.")
_DECIMAL_COORDINATE = re.compile(r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)$")


def _coordinate(value, limit):
    """Convert text to a map number, without changing the stored text."""
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().translate(_COORDINATE_DIGITS)
    # Python may stringify tiny legacy numeric values with an exponent.
    if isinstance(value, str) and not _DECIMAL_COORDINATE.fullmatch(text):
        return None
    try:
        number = Decimal(text)
        if not number.is_finite() or number.copy_abs() > limit:
            return None
        return float(number)
    except (InvalidOperation, ValueError, OverflowError):
        return None


def _valid_point(lat, lon):
    lat, lon = _coordinate(lat, 90), _coordinate(lon, 180)
    # Historic Frappe Float fields can store unset coordinates as (0, 0).
    # Keep excluding the ambiguous pair until existing records are reviewed.
    return lat is not None and lon is not None and (lat != 0 or lon != 0)


@frappe.whitelist()
def geographic_data():
    """Only record-owned coordinates are shown; linked Place coordinates are never copied.

    Coordinate strings stay untouched in the record. Map positions are binary
    floating-point approximations for compatibility with browser map libraries.
    """
    nodes, truncated = _entity_rows(GEO_TYPES, ("latitude", "longitude", "geo_precision", "geocoding_method", "geo_uncertainty_m", "geometry_source"))
    points = [{**node, "latitude": _coordinate(node["latitude"], 90), "longitude": _coordinate(node["longitude"], 180)}
              for node in nodes if _valid_point(node["latitude"], node["longitude"])]
    return {"points": points, "truncated": truncated}


@frappe.whitelist()
def relationship_data(include_evidence=0):
    """Only expose edges whose relationship and both endpoint records are visible.

    Evidence is optional because checking the parent's child table requires an
    additional document load. An inaccessible evidence field yields None.
    """
    nodes, truncated = _entity_rows(GRAPH_TYPES, include_details=True)
    visible = {(node["doctype"], node["name"]) for node in nodes}
    rows, cut = _records("Relationship", ["relationship_type", "subject_type", "subject", "object_type", "object", "direction", "description", "workflow_state", "is_current", "end_date", "authentication_level", "primary_source"])
    if cut:
        truncated.append("Relationship")
    edges = []
    with_evidence = str(include_evidence).lower() in ("1", "true")
    for row in rows:
        source = (row.get("subject_type"), row.get("subject"))
        target = (row.get("object_type"), row.get("object"))
        if source in visible and target in visible:
            edges.append({"name": row["name"], "source": list(source), "target": list(target),
                          "type": row.get("relationship_type") or "", "direction": row.get("direction") or "",
                          "description": row.get("description") or "", "state": row.get("workflow_state") or "",
                          "is_current": row.get("is_current"), "end_date": row.get("end_date"),
                          "authentication_level": row.get("authentication_level") or "", "primary_source": row.get("primary_source") or ""})
            if with_evidence:
                doc = frappe.get_doc("Relationship", row["name"])
                doc.check_permission("read")
                field = doc.meta.get_field("evidence")
                can_read = bool(field) and (not getattr(field, "permlevel", 0) or frappe.session.user == "Administrator" or doc.has_permlevel_access_to("evidence", field, "read"))
                if can_read:
                    doc.apply_fieldlevel_read_permissions()
                    edges[-1]["evidence_count"] = len(doc.get("evidence") or [])
                else:
                    edges[-1]["evidence_count"] = None
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


def _hierarchy_rows(doctype, title, fields):
    """Load structural fields through Frappe's list and document permissions."""
    rows = list(readable_rows(doctype, (title, *fields)))
    if any(any(field not in row for field in fields) for row in rows):
        frappe.throw(_("A structure grouping field is not readable."), frappe.PermissionError)
    return rows


def _forest(doctype, rows, title, parent_field, partition_field=None):
    """Produce an acyclic forest of readable records, optionally within partitions."""
    by_name = {row["name"]: row for row in rows}
    parents = {}
    for name, row in by_name.items():
        parent = row.get(parent_field) if parent_field else None
        if parent not in by_name or (partition_field and by_name[parent].get(partition_field) != row.get(partition_field)):
            parent = None
        parents[name] = parent
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
    nodes = {name: {"label": row.get(title) or name, "name": name, "target": True,
                    "target_doctype": doctype, "count": 1, "group_count": 0, "children": []}
             for name, row in by_name.items()}
    tops = []
    for name, node in nodes.items():
        parent = parents[name]
        (nodes[parent]["children"] if parent else tops).append(node)
    return nodes, tops, by_name


def _finalize_forest(root):
    """Count and fold bottom-up; a real record contributes one to its subtree."""
    stack = [(root, False, 0)]
    while stack:
        node, visited, depth = stack.pop()
        if not visited:
            stack.append((node, True, depth))
            stack.extend((child, False, depth + 1) for child in node["children"])
            continue
        children = sorted(node["children"], key=lambda child: (-child["count"], child["label"].casefold(), child.get("name", "")))
        node["count"] = int(bool(node.get("target"))) + sum(child["count"] for child in children)
        node["group_count"] = len(children)
        budget = min(60, STRUCTURE_MAX_CHILDREN * 2) if depth == 0 else max(5, STRUCTURE_MAX_CHILDREN // (depth + 1))
        tail = children[budget:]
        node["children"] = children[:budget]
        if tail:
            node["children"].append({"label": _("{0} smaller groups").format(len(tail)),
                                     "count": sum(child["count"] for child in tail),
                                     "folded_groups": len(tail), "group_count": 0, "children": []})
    return root


def _hierarchy(doctype, title_field, parent_field):
    """Build a permission-visible command tree; unreadable parents become roots."""
    if not frappe.has_permission(doctype, "read"):
        frappe.throw(_("Not permitted to read {0}").format(_(doctype)), frappe.PermissionError)
    rows = _hierarchy_rows(doctype, title_field, (parent_field,))
    nodes, tops, indexed = _forest(doctype, rows, title_field, parent_field)
    root = _finalize_forest({"count": 0, "children": tops})
    return {"doctype": doctype, "dimensions": [_('Command hierarchy')], "count": root["count"],
            "truncated": False, "group_count": root["group_count"], "children": root["children"]}


def _composite(source):
    """Count each readable record once, including records with no visible parent.

    Region/unit and unit/operation links are never shown when their parent is
    unreadable. Such children are placed in an anonymous unassigned branch.
    """
    regions = source == "regions-units"
    main = "Command Region" if regions else "Military Unit"
    main_title, main_parent = ("region_name", "parent_region") if regions else ("unit_name", "parent_unit")
    if not frappe.has_permission(main, "read"):
        frappe.throw(_("Not permitted to read {0}").format(_(main)), frappe.PermissionError)
    main_rows = _hierarchy_rows(main, main_title, (main_parent,))
    main_nodes, tops, indexed_main = _forest(main, main_rows, main_title, main_parent)
    unassigned = []
    unavailable = []
    if regions:
        if frappe.has_permission("Military Unit", "read"):
            rows = _hierarchy_rows("Military Unit", "unit_name", ("parent_unit", "region"))
            unit_nodes, unit_tops, indexed = _forest("Military Unit", rows, "unit_name", "parent_unit", "region")
            for node in unit_tops:
                region = indexed[node["name"]].get("region")
                (main_nodes[region]["children"] if region in main_nodes else unassigned).append(node)
        else:
            unavailable.append("Military Unit")
    else:
        for doctype, title in (("Operational Deployment", "deployment_name"), ("Mission", "mission_name"),
                               ("Training Exercise", "exercise_name")):
            if not frappe.has_permission(doctype, "read"):
                unavailable.append(doctype)
                continue
            rows = _hierarchy_rows(doctype, title, ("unit",))
            attached_nodes, attached, indexed = _forest(doctype, rows, title, None)
            for node in attached:
                unit = indexed[node["name"]].get("unit")
                (main_nodes[unit]["children"] if unit in main_nodes else unassigned).append(node)
    if unassigned:
        tops.append({"label": _("Unassigned or inaccessible parent"), "count": 0, "group_count": 0, "children": unassigned})
    root = _finalize_forest({"count": 0, "children": tops})
    return {"doctype": main, "label": _("Regions × Units") if regions else _("Units × Operations"),
            "dimensions": [_('Command hierarchy')], "count": root["count"], "truncated": False,
            "unavailable_types": unavailable, "group_count": root["group_count"], "children": root["children"]}


@frappe.whitelist()
def structure_data(source="people"):
    """Count every readable record; fold wide branches without losing counts.

    This synchronous scan can be expensive for large sites or custom permission
    hooks. Counts represent the current user's visible records, not global totals.
    """
    if source in ("regions-units", "units-ops"):
        return _composite(source)
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
