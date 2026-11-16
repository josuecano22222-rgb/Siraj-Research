"""Whitelisted ego-network endpoint for the map.

Returns the graph of relationships reachable from a given entity within N
hops, with coordinates for each endpoint (direct or inferred) so the map
overlay can draw edges without a second round-trip. All access goes
through frappe.get_list / frappe.get_doc so DocType permissions apply;
no raw SQL; capped responses; never returns coordinates for records the
user cannot read.
"""
from __future__ import annotations

import frappe
from frappe import _

# Entity DocTypes that can be endpoints of a Relationship. Must match the
# Select options on Relationship.subject_type / object_type.
RELATABLE_DOCTYPES: tuple[str, ...] = ("Person", "Institution", "Place", "Research Event", "Source")

# Where to look for an entity's location if it has no direct latitude/longitude
# of its own. Order matters: Place wins over a Unit or Deployment because it
# is the entity's own declared location link.
INFERENCE_CHAINS: dict[str, tuple[tuple[str, str], ...]] = {
	"Person": (("linked_place", "Place"),),
	"Institution": (("linked_place", "Place"),),
	# We intentionally do not cross into Military Unit / Deployment because
	# those DocTypes are not currently relatable endpoints on the Relationship
	# DocType; see RELATABLE_DOCTYPES.
}

DEFAULT_NODES_CAP = 500
DEFAULT_EDGES_CAP = 1000


@frappe.whitelist()
def get_entity_network(doctype: str, name: str, depth: int = 1, types: str | None = None,
					   limit_nodes: int = DEFAULT_NODES_CAP, limit_edges: int = DEFAULT_EDGES_CAP):
	"""Return {nodes, edges, unmapped, truncated, total} for the ego network.

	Permission model: uses frappe.get_list for Relationship traversal, which
	respects DocType read permissions. For each reached endpoint we call
	frappe.has_permission and frappe.get_cached_value; if the user cannot read
	the target DocType, the endpoint is returned as ``restricted: true`` with
	no name or label (so edges exist without leaking).
	"""
	depth = max(0, min(int(depth or 1), 3))
	if doctype not in RELATABLE_DOCTYPES:
		frappe.throw(_("Relationships are not defined for {0}", doctype))
	if not frappe.has_permission(doctype, "read", name):
		frappe.throw(_("You do not have permission to read {0}", doctype), frappe.PermissionError)

	allowed_types = None
	if types:
		allowed_types = {t.strip() for t in types.split(",") if t.strip()}

	start_id = (doctype, name)
	visited_nodes: dict[tuple[str, str], dict] = {}
	visited_edges: dict[str, dict] = {}
	unmapped: list[dict] = []
	frontier = {start_id: 0}
	truncated = False
	restricted_names: set[tuple[str, str]] = set()

	# Seed the center.
	seed = _node_record(doctype, name, restricted_names, unmapped, hops=0)
	if seed is None:
		frappe.throw(_("Record not found or not readable: {0} {1}", doctype, name))
	visited_nodes[start_id] = seed

	for d in range(depth + 1):
		if not frontier:
			break
		next_frontier: dict[tuple[str, str], int] = {}
		# Pull all edges from the frontier in one OR query per direction.
		subject_filters = {"subject_type": ("in", []), "subject": ("in", [])}
		object_filters = {"object_type": ("in", []), "object": ("in", [])}
		# We'll build OR filters using nested conditions.
		or_groups = []
		# Batch edges per DocType for efficient queries.
		by_subject: dict[str, list[str]] = {}
		by_object: dict[str, list[str]] = {}
		for (dt, nm) in frontier:
			by_subject.setdefault(dt, []).append(nm)
			by_object.setdefault(dt, []).append(nm)
		for sdt, names in by_subject.items():
			if sdt not in RELATABLE_DOCTYPES:
				continue
			or_groups.append([["subject_type", "=", sdt], ["subject", "in", names]])
		for odt, names in by_object.items():
			if odt not in RELATABLE_DOCTYPES:
				continue
			or_groups.append([["object_type", "=", odt], ["object", "in", names]])
		if not or_groups:
			break
		filters = {"parenttype": "Relationship"}  # we query Relationship via frappe.get_list directly
		edge_filters = []
		for grp in or_groups:
			f = grp[:]
			if allowed_types is not None:
				f.append(["relationship_type", "in", list(allowed_types)])
			edge_filters.append(f)
		if not edge_filters:
			break
		try:
			edges = frappe.get_list(
				"Relationship",
				filters=edge_filters,
				fields=["name", "subject_type", "subject", "object_type", "object",
						"relationship_type", "direction", "start_date", "end_date",
						"description", "display_name"],
				limit=limit_edges + 1,
			)
		except Exception as exc:  # pragma: no cover - defensive
			frappe.log_error(
				title="siraj map_relations.get_entity_network query failed",
				message=frappe.get_traceback(),
			)
			raise

		if len(edges) > limit_edges:
			edges = edges[:limit_edges]
			truncated = True

		for edge in edges:
			e_key = edge["name"]
			if e_key in visited_edges:
				continue
			if len(visited_edges) >= limit_edges:
				truncated = True
				break
			visited_edges[e_key] = {
				"name": e_key,
				"source": [edge["subject_type"], edge["subject"]],
				"target": [edge["object_type"],  edge["object"]],
				"type": edge["relationship_type"],
				"direction": edge["direction"],
				"start_date": edge["start_date"],
				"end_date": edge["end_date"],
				"description": edge["description"],
				"display_name": edge["display_name"],
			}
			# Add both endpoints if permitted and within node cap.
			for endpoint_dt, endpoint_nm, role in (
				(edge["subject_type"], edge["subject"], "source"),
				(edge["object_type"],  edge["object"],  "target"),
			):
				key = (endpoint_dt, endpoint_nm)
				if key in visited_nodes or key in restricted_names:
					continue
				if len(visited_nodes) >= limit_nodes:
					truncated = True
					continue
				if endpoint_dt not in RELATABLE_DOCTYPES:
					continue
				if not frappe.has_permission(endpoint_dt, "read", endpoint_nm):
					restricted_names.add(key)
					visited_nodes[key] = {
						"doctype": endpoint_dt, "name": endpoint_nm, "label": _("Restricted"),
						"restricted": True, "location_source": None, "hops": d + 1,
					}
					continue
				rec = _node_record(endpoint_dt, endpoint_nm, restricted_names, unmapped, hops=d + 1)
				if rec is not None:
					visited_nodes[key] = rec
					if d + 1 < depth:
						next_frontier[key] = d + 1
		frontier = next_frontier

	# Collect type metadata for the legend.
	types = {}
	for e in visited_edges.values():
		t = e["type"] or _("Unspecified")
		meta = types.setdefault(t, {"count": 0, "color": "#536b78", "is_symmetric": True})
		meta["count"] += 1
		if frappe.db.exists("Relationship Type", t):
			color = frappe.db.get_value("Relationship Type", t, "color")
			is_sym = frappe.db.get_value("Relationship Type", t, "is_symmetric")
			if color: meta["color"] = color
			if is_sym is not None: meta["is_symmetric"] = bool(is_sym)

	return {
		"center": list(start_id),
		"nodes": list(visited_nodes.values()),
		"edges": list(visited_edges.values()),
		"unmapped": unmapped,
		"truncated": truncated,
		"total": len(visited_edges),
		"types": types,
	}


def _node_record(doctype: str, name: str, restricted: set, unmapped: list, hops: int) -> dict | None:
	"""Return a node dict with coordinates when possible, or add to unmapped."""
	try:
		doc = frappe.get_cached_value(
			doctype, name,
			["name", "display_name", "label", "title", "latitude", "longitude",
			 "linked_place", "geo_precision", "geocoding_method", "geo_uncertainty_m"],
			as_dict=True,
		)
	except Exception:
		return None
	if not doc:
		return None
	label = doc.get("display_name") or doc.get("label") or doc.get("title") or name
	lat = doc.get("latitude")
	lon = doc.get("longitude")
	location_source = "direct" if (lat is not None and lon is not None) else None

	# Inferred-location chains: only follow links that exist on this DocType.
	if location_source is None:
		for field, link_doctype in INFERENCE_CHAINS.get(doctype, ()):
			link_name = doc.get(field)
			if not link_name:
				continue
			if not frappe.has_permission(link_doctype, "read", link_name):
				continue
			link = frappe.get_cached_value(
				link_doctype, link_name,
				["latitude", "longitude"], as_dict=True,
			)
			if link and link.latitude is not None and link.longitude is not None:
				lat, lon = link.latitude, link.longitude
				location_source = f"inferred:{link_doctype}"
				break

	node = {
		"doctype": doctype,
		"name": name,
		"label": label,
		"latitude": lat,
		"longitude": lon,
		"location_source": location_source,
		"geo_precision": doc.get("geo_precision"),
		"geocoding_method": doc.get("geocoding_method"),
		"geo_uncertainty_m": doc.get("geo_uncertainty_m"),
		"hops": hops,
		"restricted": False,
	}
	if location_source is None:
		unmapped.append({"doctype": doctype, "name": name, "label": label})
	return node
