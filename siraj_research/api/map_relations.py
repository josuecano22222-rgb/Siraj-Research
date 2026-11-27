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
# Baseline set of DocTypes that can participate in relationships. At runtime we
# also read whatever Relationship.subject_type/object_type Select options have
# been extended to (so adding new doctypes to the Select doesn't require code
# changes). Only DocTypes that actually exist + are readable by the current
# user are used — unknown/permission-denied endpoints are returned as
# restricted nodes instead of crashing with "Relationships are not defined
# for {doctype}".
_BASE_RELATABLE: tuple[str, ...] = ("Person", "Institution", "Place", "Siraj Event", "Source",
									"Military Unit", "Operational Deployment")

def _relatable_doctypes() -> set[str]:
	types: set[str] = set(_BASE_RELATABLE)
	try:
		meta = frappe.get_meta("Relationship")
		for fn in ("subject_type", "object_type"):
			df = meta.get_field(fn)
			if df and df.options:
				for opt in (df.options or "").splitlines():
					opt = opt.strip()
					if opt:
						types.add(opt)
	except Exception:
		pass
	# Prune DocTypes that don't actually exist on this site.
	existing: set[str] = set()
	for dt in types:
		try:
			if frappe.db.exists("DocType", dt):
				existing.add(dt)
		except Exception:
			pass
	return existing or set(_BASE_RELATABLE)

# Where to look for an entity's location if it has no direct latitude/longitude
# of its own. Keys are fieldnames that actually exist on the DocType (verified
# against the DocType JSON); values are the Link target doctype.
INFERENCE_CHAINS: dict[str, tuple[tuple[str, str], ...]] = {
	"Person":                 (("birthplace",   "Place"),),  # Place of birth is the only Place link on Person; used as a coarse fallback when no direct coords.
	"Institution":            (("place",        "Place"),),  # Institution.place Link → Place.
	"Siraj Event":            (("place",        "Place"),),  # Siraj Event.place Link → Place.
	"Military Unit":          (("linked_place", "Place"),),  # HQ Place (garrison / command area / base).
	"Operational Deployment": (),                              # Deployments carry their own lat/lon; no fallback link.
	"Mission":                (("unit", "Military Unit"),),  # Missions inherit via unit → linked_place.
	"Training Exercise":      (("unit", "Military Unit"),),  # Exercises inherit via unit → linked_place.
}

DEFAULT_NODES_CAP = 500
DEFAULT_EDGES_CAP = 1000
MAX_NODES_HARD = 1000
MAX_EDGES_HARD = 2000


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
	# HTTP query args arrive as strings; coerce numerics defensively so defaults
	# and arithmetic always see ints (not str+int TypeErrors).
	try:
		depth = max(0, min(int(depth or 1), 3))
	except (TypeError, ValueError):
		depth = 1
	try:
		limit_nodes = int(limit_nodes or DEFAULT_NODES_CAP)
	except (TypeError, ValueError):
		limit_nodes = DEFAULT_NODES_CAP
	try:
		limit_edges = int(limit_edges or DEFAULT_EDGES_CAP)
	except (TypeError, ValueError):
		limit_edges = DEFAULT_EDGES_CAP
	limit_nodes = max(1, min(limit_nodes, MAX_NODES_HARD))
	limit_edges = max(1, min(limit_edges, MAX_EDGES_HARD))
	RELATABLE_DOCTYPES = _relatable_doctypes()
	# If the seed DocType isn't relatable, the target record does not exist, OR
	# the user can't read it, return an empty network instead of throwing —
	# Explorer handles an empty result gracefully and throwing DoesNotExistError
	# vs PermissionError would leak record existence on predictable IDs.
	if (
		doctype not in RELATABLE_DOCTYPES
		or not frappe.db.exists(doctype, name)
		or not frappe.has_permission(doctype, "read", name)
	):
		return {
			"center": [doctype, name],
			"nodes": [],
			"edges": [],
			"unmapped": [],
			"truncated": False,
			"total": 0,
			"types": {},
			"notice": _("No relationships defined for {0}").format(doctype) if doctype not in RELATABLE_DOCTYPES else None,
		}

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
		frappe.throw(_("Record not found or not readable: {0} {1}").format(doctype, name))
	visited_nodes[start_id] = seed

	for d in range(depth + 1):
		if not frontier:
			break
		next_frontier: dict[tuple[str, str], int] = {}
		# Batch edges per DocType per direction and issue separate get_list calls
		# with simple dict filters (AND semantics). This avoids Frappe's OR-list
		# format pitfall where a nested list of 3-tuples is mis-interpreted as a
		# single 4-tuple filter, producing "Filter must have 4 values".
		by_subject: dict[str, list[str]] = {}
		by_object: dict[str, list[str]] = {}
		for (dt, nm) in frontier:
			by_subject.setdefault(dt, []).append(nm)
			by_object.setdefault(dt, []).append(nm)

		edges: list[dict] = []
		def _query(direction_field: str, dt_field: str, name_field: str, batches: dict[str, list[str]]):
			nonlocal edges
			for dt, names in batches.items():
				if dt not in RELATABLE_DOCTYPES:
					continue
				if len(visited_edges) >= limit_edges:
					break
				filt = {dt_field: dt, name_field: ("in", names)}
				if allowed_types is not None:
					filt["relationship_type"] = ("in", list(allowed_types))
				remaining = limit_edges - len(visited_edges) + 1  # +1 to detect truncation
				try:
					batch = frappe.get_list(
						"Relationship",
						filters=filt,
						fields=["name", "subject_type", "subject", "object_type", "object",
								"relationship_type", "direction", "start_date", "end_date",
								"description", "display_name"],
						limit=remaining,
					)
				except Exception:  # pragma: no cover - defensive
					frappe.log_error(
						title="siraj map_relations.get_entity_network query failed",
						message=frappe.get_traceback(),
					)
					raise
				edges.extend(batch)

		_query("subject", "subject_type", "subject", by_subject)
		_query("object",  "object_type",  "object",  by_object)

		if not edges:
			frontier = next_frontier
			continue

		# Truncation detection: if any batch hit limit we may have over-counted;
		# simply flag truncated when we ended with more than limit_edges.
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
			for endpoint_dt, endpoint_nm, _role in (
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
			if color:
				meta["color"] = color
			if is_sym is not None:
				meta["is_symmetric"] = bool(is_sym)

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
	# Build a field list that only includes columns this DocType actually has,
	# so get_cached_value doesn't raise on fields missing from the DocType.
	want = ["name", "latitude", "longitude", "geo_precision", "geocoding_method", "geo_uncertainty_m"]
	label_fields = ["display_name", "label", "title", "unit_name", "deployment_name"]
	# Per-doctype Link-to-Place fields (used by INFERENCE_CHAINS).
	link_fields = ["linked_place", "birthplace", "place"]
	available = {f.fieldname for f in frappe.get_meta(doctype).fields}
	present_want = [f for f in want if f == "name" or f in available]
	present_label = [f for f in label_fields if f in available]
	present_links = [f for f in link_fields if f in available]
	fetch_fields = list(dict.fromkeys(present_want + present_label + present_links))
	try:
		if "name" not in fetch_fields:
			fetch_fields.insert(0, "name")
		doc = frappe.get_cached_value(doctype, name, fetch_fields, as_dict=True)
	except Exception:
		return None
	if not doc:
		return None
	label = name
	for lf in label_fields:
		if doc.get(lf):
			label = doc.get(lf)
			break
	lat = doc.get("latitude")
	lon = doc.get("longitude")
	location_source = "direct" if (lat is not None and lon is not None) else None

	# Inferred-location chains: follow Links transitively (e.g. Mission →
	# Military Unit → Place). Cap at 4 hops to avoid cycles; only walk fields
	# that actually exist on each intermediate DocType.
	if location_source is None:
		def _resolve(chain_doctype: str, chain_name: str, depth: int, seen: set[str]):
			if depth > 4 or (chain_doctype, chain_name) in seen:
				return None
			seen.add((chain_doctype, chain_name))
			try:
				link_meta = frappe.get_meta(chain_doctype)
				link_fields_available = {df.fieldname for df in (link_meta.fields or [])}
				link_doc = frappe.get_cached_value(
					chain_doctype, chain_name,
					[
						"latitude",
						"longitude",
						*sorted(
							{f for f, _dt in INFERENCE_CHAINS.get(chain_doctype, ()) if f in link_fields_available}
						),
					],
					as_dict=True,
				) if frappe.has_permission(chain_doctype, "read", chain_name) else None
			except Exception:
				link_doc = None
			if not link_doc:
				return None
			if link_doc.latitude is not None and link_doc.longitude is not None:
				return (link_doc.latitude, link_doc.longitude, chain_doctype)
			for field, link_doctype in INFERENCE_CHAINS.get(chain_doctype, ()):
				if not field or field not in link_doc:
					continue
				next_name = link_doc.get(field)
				if not next_name:
					continue
				found = _resolve(link_doctype, next_name, depth + 1, seen)
				if found:
					return found
			return None

		for field, link_doctype in INFERENCE_CHAINS.get(doctype, ()):
			if field not in available:
				continue
			link_name = doc.get(field)
			if not link_name:
				continue
			found = _resolve(link_doctype, link_name, 1, {(doctype, name)})
			if found:
				lat, lon, via = found
				location_source = f"inferred:{via}"
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
