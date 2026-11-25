# siraj_research.api.entity_profile — whitelisted entity profile endpoint.
#
# Returns a complete read-only snapshot of any record the caller has permission
# to read: header, all readable fields (respecting permlevels), child tables,
# connections (authored Relationships + structural outbound/inbound links),
# location block, and an activity summary. Designed for the details drawer on
# every map surface. No raw SQL; all reads go through frappe.get_list/get_doc.

import json

import frappe
from frappe import _
from frappe.model.meta import get_meta

from siraj_research.profile_presentation import compute_quality_scores, organise_profile

# Layout-only fieldtypes we never render as values. "Table" is deliberately
# absent here: it is skipped by the scalar loop below but collected as a child
# table, so it can never leak into a <dd> as "[object Object]".
SKIP_FIELDTYPES = {
    "Section Break", "Column Break", "Tab Break", "HTML", "Button", "Table MultiSelect",
}
VALUE_FIELDTYPES = {
    "Data", "Int", "Float", "Currency", "Percent", "Check", "Date", "Datetime", "Time",
    "Text", "Small Text", "Long Text", "Text Editor", "Code", "Link", "Dynamic Link",
    "Select", "Rating", "Attach", "Attach Image", "Image", "Barcode", "Duration",
    "Phone", "Email", "Geolocation",
}
PASSWORD_PLACEHOLDER = "••••••"
INBOUND_LINKS_CAP = 200


def _inbound_numeric_count(item):
    c = item.get("count")
    if isinstance(c, int):
        return c
    if isinstance(c, str) and c.endswith("+") and c[:-1].isdigit():
        return int(c[:-1])
    return 0


def _field_label(f):
    return (f.label or f.fieldname).strip()


def _fmt_value(doc, f):
    fn = f.fieldname
    ft = f.fieldtype
    val = doc.get(fn)
    if val in (None, "", []):
        return None
    if ft == "Password":
        return PASSWORD_PLACEHOLDER
    if ft in ("Check",):
        # Keep the raw boolean: the client translates "Yes"/"No" once, in the
        # language it is actually rendering, and can show the source value too.
        return bool(val)
    if ft in ("Attach", "Attach Image", "Image"):
        return {"type": "attach", "url": val}
    if ft == "Link":
        # Resolve title of the linked doc if permitted.
        try:
            if frappe.has_permission(f.options, "read", doc=val):
                title = frappe.db.get_value(f.options, val, frappe.get_meta(f.options).get_title_field() or "name") or val
                return {"type": "link", "doctype": f.options, "name": val, "title": title}
        except Exception:
            pass
        return {"type": "link", "doctype": f.options, "name": val, "title": val}
    if ft == "Dynamic Link":
        target_doctype = doc.get(f.options)
        if not target_doctype:
            return val
        try:
            if frappe.has_permission(target_doctype, "read", doc=val):
                title = frappe.db.get_value(target_doctype, val, frappe.get_meta(target_doctype).get_title_field() or "name") or val
                return {"type": "link", "doctype": target_doctype, "name": val, "title": title}
        except Exception:
            pass
        return {"type": "link", "doctype": target_doctype, "name": val, "title": val}
    if ft == "Select":
        # Do not translate here. The profile keeps the recorded value and the
        # client translates controlled vocabulary through __(); see
        # profile_presentation.normalise_field for the translatable_value flag.
        return val
    return val


@frappe.whitelist()
def get_entity_profile(doctype, name, **kwargs):
    """Return the full profile dict for a record.

    Keys: header, fields (grouped by section), children, connections
    (relationships, outbound_links, inbound_links), location, activity,
    network_summary, permissions.
    """
    if not frappe.has_permission(doctype, "read", name):
        frappe.throw(_("Not permitted to read {0} {1}").format(doctype, name),
                     frappe.PermissionError)

    try:
        doc = frappe.get_doc(doctype, name)
    except frappe.DoesNotExistError:
        frappe.throw(_("{0} {1} not found").format(doctype, name))

    meta = get_meta(doctype)

    # ---- Header ----
    header = {
        "doctype": doctype,
        "name": doc.name,
        "title": doc.get_title() if hasattr(doc, "get_title") else doc.name,
        "status": (doc.get("status") or doc.get("workflow_state") or ""),
        "owner": doc.owner,
        "modified": doc.modified,
        "docstatus": doc.docstatus,
    }

    # ---- Fields grouped by section ----
    sections = []
    cur_section = {"heading": doctype, "fields": []}
    sections.append(cur_section)
    field_map = {}
    for f in meta.fields:
        if f.fieldtype in SKIP_FIELDTYPES:
            # A Tab Break is a new top-level group. Treating it as a mere
            # separator used to append its fields to the previous section
            # (e.g. "Completeness (%)" under "External identifiers").
            if f.fieldtype in ("Section Break", "Tab Break"):
                cur_section = {"heading": _field_label(f) or _("Details"), "fields": []}
                sections.append(cur_section)
            continue
        if f.fieldtype == "Table":
            # Child tables are collected below; they are never scalar values.
            continue
        if f.hidden:
            continue
        if (f.permlevel or 0) > 0 and not doc.has_permlevel_access_to(f.fieldname, f, "read"):
            continue
        val = _fmt_value(doc, f)
        entry = {
            "fieldname": f.fieldname,
            "label": _field_label(f),
            "fieldtype": f.fieldtype,
            "options": f.options,
            "value": val,
        }
        if val is not None:
            cur_section["fields"].append(entry)
            field_map[f.fieldname] = entry

    # Drop empty sections (aside from their heading).
    sections = [s for s in sections if s["fields"]]

    # ---- Child tables ----
    allowed_permlevels = set(doc.get_permlevel_access("read"))
    children = {}
    for f in meta.fields:
        if f.fieldtype == "Table" and f.options:
            if (f.permlevel or 0) > 0 and not doc.has_permlevel_access_to(f.fieldname, f, "read"):
                continue
            rows = []
            rmeta = get_meta(f.options)
            readable_child_fields = [
                rf for rf in rmeta.fields
                if rf.fieldtype not in SKIP_FIELDTYPES
                and not rf.hidden
                and ((rf.permlevel or 0) == 0 or (rf.permlevel or 0) in allowed_permlevels)
            ]
            column_order = [rf.fieldname for rf in readable_child_fields]
            for r in (doc.get(f.fieldname) or [])[:50]:
                row = {}
                for rf in readable_child_fields:
                    v = _fmt_value(r, rf)
                    if v is not None:
                        row[rf.fieldname] = {
                            "label": _field_label(rf),
                            "fieldtype": rf.fieldtype,
                            "options": rf.options,
                            "value": v,
                        }
                rows.append(row)
            children[f.fieldname] = {"label": _field_label(f), "options": f.options, "rows": rows,
                                     "column_order": column_order,
                                     "truncated": len(doc.get(f.fieldname) or []) > 50,
                                     "total": len(doc.get(f.fieldname) or [])}

    # ---- Connections: authored Relationships ----
    relationships = _authored_relationships(doctype, name)

    # ---- Connections: structural outbound (Link / Dynamic Link fields on this doc) ----
    outbound = []
    for f in meta.fields:
        if (f.permlevel or 0) > 0 and not doc.has_permlevel_access_to(f.fieldname, f, "read"):
            continue
        if f.fieldtype == "Link" and f.options and doc.get(f.fieldname):
            val = doc.get(f.fieldname)
            if val:
                target_dt = f.options
                try:
                    can_read = bool(frappe.has_permission(target_dt, "read", doc=val))
                except Exception:
                    can_read = False
                title = val
                if can_read:
                    try:
                        title = frappe.db.get_value(target_dt, val, frappe.get_meta(target_dt).get_title_field() or "name") or val
                    except Exception:
                        pass
                outbound.append({
                    "field": f.fieldname, "label": _field_label(f), "doctype": target_dt, "name": val,
                    "title": title if can_read else _("Restricted"),
                    "restricted": not can_read,
                })
        elif f.fieldtype == "Dynamic Link" and doc.get(f.options):
            target_dt = doc.get(f.options)
            val = doc.get(f.fieldname)
            if val and target_dt:
                try:
                    can_read = bool(frappe.has_permission(target_dt, "read", doc=val))
                except Exception:
                    can_read = False
                title = val
                if can_read:
                    try:
                        title = frappe.db.get_value(target_dt, val, frappe.get_meta(target_dt).get_title_field() or "name") or val
                    except Exception:
                        pass
                outbound.append({
                    "field": f.fieldname, "label": _field_label(f), "doctype": target_dt, "name": val,
                    "title": title if can_read else _("Restricted"),
                    "restricted": not can_read,
                })

    # ---- Connections: structural inbound (other docs linking here) ----
    inbound = _inbound_links(doctype, name)

    connections = {
        "relationships": relationships,
        "outbound_links": outbound,
        "inbound_links": inbound,
    }

    # ---- Location block ----
    location = None
    if "latitude" in field_map or "longitude" in field_map:
        location = {
            "latitude": doc.get("latitude"),
            "longitude": doc.get("longitude"),
            "precision": doc.get("geo_precision"),
            "method": doc.get("geocoding_method"),
            "uncertainty_m": doc.get("geo_uncertainty_m"),
            "source": doc.get("geometry_source"),
            "location_source": doc.get("location_source"),
        }

    # ---- Activity (latest 5 comments + 5 versions, if permitted) ----
    activity = {"comments": [], "versions": [], "attachments": []}
    try:
        if frappe.has_permission("Comment", "read"):
            activity["comments"] = frappe.get_all(
                "Comment",
                filters={"reference_doctype": doctype, "reference_name": name, "comment_type": ("!=", "Private")},
                fields=["name", "comment_email", "comment_by", "content", "creation"],
                order_by="creation desc", limit=5,
            )
    except Exception:
        pass
    try:
        # Audit history: the Version storage is System-Manager-only, but the
        # governing permission is the record the caller already may read —
        # collect_history() re-checks record + field level and formats the
        # entries (same helper as the audit dialog).
        from siraj_research.api.audit import collect_history

        activity["versions"] = collect_history(doctype, name, limit=5)["history"]
    except Exception:
        pass
    try:
        if frappe.has_permission("File", "read"):
            raw_files = frappe.get_list(
                "File",
                filters={"attached_to_doctype": doctype, "attached_to_name": name},
                fields=["name", "file_name", "file_url", "file_type", "creation"],
                order_by="creation desc",
                limit=10,
            )
            activity["attachments"] = [
                row for row in raw_files if frappe.has_permission("File", "read", doc=row["name"])
            ]
    except Exception:
        pass

    # ---- Network summary ----
    rel_by_type = {}
    for r in relationships:
        rel_by_type[r.get("relationship_type")] = rel_by_type.get(r.get("relationship_type"), 0) + 1
    has_capped_inbound = any(x.get("capped") for x in inbound)
    total_inbound = sum(_inbound_numeric_count(x) for x in inbound)
    network_summary = {
        "relationship_count": len(relationships),
        "by_type": rel_by_type,
        "outbound_count": len(outbound),
        "inbound_count": f"{total_inbound}+" if has_capped_inbound else total_inbound,
    }

    # ---- Permissions for actions ----
    perms = {
        "can_write": frappe.has_permission(doctype, "write", name),
        "can_create": frappe.has_permission("Relationship", "create"),
    }

    # ---- Quality scores (presentation-time, deterministic) ----
    # compute_quality_scores lives in the pure presentation layer; the
    # section/field entries below reuse the existing Quality group so the
    # drawer renders the scores with no parallel structure.
    scores = compute_quality_scores({"sections": sections, "children": children})
    quality_section = next(
        (s for s in sections if s.get("heading") == "Quality"), None
    )
    if quality_section is None:
        quality_section = {"heading": "Quality", "fields": []}
        sections.append(quality_section)
    existing_quality = {
        f.get("fieldname"): f for f in quality_section["fields"]
    }
    for fieldname, label, fieldtype in (
        ("completeness_score", "Completeness (%)", "Int"),
        ("quality_score", "Quality score", "Int"),
        ("confidence", "Confidence", "Select"),
    ):
        entry = existing_quality.get(fieldname)
        if entry is None:
            entry = {
                "fieldname": fieldname,
                "label": label,
                "fieldtype": fieldtype,
                "options": "",
                "value": None,
            }
            quality_section["fields"].append(entry)
        entry["value"] = scores[fieldname]
        if fieldname == "confidence":
            # Carry the derived/recorded distinction to the shared renderer
            # (desk profile AND Explorer both read this payload).
            entry["derived"] = bool(scores.get("confidence_derived"))

    profile = {
        "header": header,
        "sections": sections,
        "children": children,
        "connections": connections,
        "location": location,
        "activity": activity,
        "network_summary": network_summary,
        "permissions": perms,
    }
    # Source labels/values stay untouched; the client translates them once.
    return organise_profile(profile, doctype=doctype, lang=getattr(frappe.local, "lang", None) or "en")


def _authored_relationships(doctype, name):
    out = []
    for side, other_type_field, other_field, dir_label in [
        ("subject", "object_type", "object", "outbound"),
        ("object", "subject_type", "subject", "inbound"),
    ]:
        try:
            rows = frappe.get_list(
                "Relationship",
                filters={side: name, side + "_type": doctype},
                fields=["name", "subject", "subject_type", "object", "object_type",
                        "relationship_type", "direction", "start_date", "end_date",
                        "description", "workflow_state", "docstatus"],
                limit=100,
            )
        except Exception:
            continue
        for r in rows:
            if not frappe.has_permission("Relationship", "read", doc=r["name"]):
                continue
            other_dt = r.get(other_type_field)
            other_name = r.get(other_field)
            try:
                can_read = bool(other_dt and other_name and frappe.has_permission(other_dt, "read", doc=other_name))
            except Exception:
                can_read = False
            title = other_name
            if can_read and other_dt:
                try:
                    title = frappe.db.get_value(other_dt, other_name, frappe.get_meta(other_dt).get_title_field() or "name") or other_name
                except Exception:
                    pass
            out.append({
                "name": r["name"],
                "direction_relative": dir_label,
                "direction": r.get("direction"),
                "relationship_type": r.get("relationship_type"),
                "counterpart_doctype": other_dt,
                "counterpart_name": other_name,
                "counterpart_title": title if can_read else _("Restricted"),
                "counterpart_restricted": not can_read,
                "start_date": r.get("start_date"),
                "end_date": r.get("end_date"),
                "description": r.get("description"),
                "workflow_state": r.get("workflow_state"),
                "docstatus": r.get("docstatus"),
            })
    return out


def _inbound_links(doctype, name):
    """Find up to 5 other DocTypes that link TO this doctype via Link fields,
    returning counts and a sample."""
    out = []
    # Dynamic Links pointing to us can't be enumerated without a scan (their
    # options field holds the doctype at row time), so skip them here.
    # Walk all DocTypes registered in the app — cheap because we only inspect meta.
    import os
    doctype_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "siraj_research", "doctype")
    if not os.path.isdir(doctype_dir):
        return out
    seen = set()
    for dn in os.listdir(doctype_dir):
        jf = os.path.join(doctype_dir, dn, dn + ".json")
        if not os.path.isfile(jf):
            continue
        try:
            with open(jf, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            continue
        if data.get("istable") or data.get("issingle"):
            continue
        linking_fields = [f for f in data.get("fields", []) if f.get("fieldtype") == "Link" and f.get("options") == doctype]
        if not linking_fields:
            continue
        target_dt = data["name"]
        if target_dt in seen:
            continue
        seen.add(target_dt)
        if not frappe.has_permission(target_dt, "read"):
            out.append({"doctype": target_dt, "count": None, "sample": [], "restricted": True})
            continue
        or_filters = []
        for f in linking_fields:
            or_filters.append([f["fieldname"], "=", name])
        capped = False
        try:
            cap = max(1, int(INBOUND_LINKS_CAP))
            rows = (
                frappe.get_list(
                    target_dt,
                    filters={"docstatus": ("<", 2)},
                    or_filters=or_filters,
                    fields=["name"],
                    limit=cap + 1,
                )
                if or_filters
                else []
            )
            if len(rows) > cap:
                capped = True
                count = f"{cap}+"
                sample = rows[:5]
            else:
                count = len(rows)
                sample = rows[:5]
        except Exception:
            frappe.log_error(
                title=f"SIRAJ entity_profile inbound_links failed for {target_dt}",
            )
            count = 0
            sample = []
        title_field = frappe.get_meta(target_dt).get_title_field() or "name"
        sample_titles = []
        for s in sample:
            try:
                t = frappe.db.get_value(target_dt, s["name"], title_field) or s["name"]
                sample_titles.append({"name": s["name"], "title": t})
            except Exception:
                sample_titles.append({"name": s["name"], "title": s["name"]})
        out.append({
            "doctype": target_dt,
            "count": count,
            "capped": capped,
            "sample": sample_titles,
            "restricted": False,
        })
    return out[:20]
