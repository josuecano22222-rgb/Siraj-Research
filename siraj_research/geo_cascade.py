"""Parent/child cascading for the six-level administrative hierarchy.

The pure helpers in this module are deliberately Frappe-free so the cascade
contract can be tested without a bench. The Frappe wrapper is a thin adapter
that reads the same hierarchy DocTypes the Link fields point at. It never
creates records and never calls an external service: everything comes from
the local bench, which is what "offline" means for Desk forms.

Two flows are supported:

* **Downward** — a Country is chosen, so the Governorate dropdown (and every
  deeper dropdown) is restricted to children of that Country.
* **Upward** — a Community/Village/Municipality is chosen, so Country,
  Governorate, District and Municipality/Village are read from that record's
  own Link fields and returned for auto-population.

Missing levels stay missing. A record with no Governorate never gets a made-up
one just to make the form look complete.
"""
from __future__ import annotations

from typing import Any

try:  # pragma: no cover - exercised inside a bench
    import frappe
except Exception:  # pragma: no cover - pure-Python tests
    frappe = None  # type: ignore[assignment]

from siraj_research.geo_hierarchy import LEVELS, field_to_level, level_spec
from siraj_research.geo_levels import (
    ancestor_filters as configured_ancestor_filters,
)
from siraj_research.geo_levels import (
    config_payload,
    country_config,
    effective_levels,
    label_for,
)

FIELDS = tuple(str(spec["field"]) for spec in LEVELS)


def option_from_row(field: str, row: dict[str, Any]) -> dict[str, Any]:
    """Normalise a Frappe row (or offline polygon) into a Link option."""
    row = dict(row or {})
    name = str(row.get("name") or row.get("value") or row.get("pcode") or "").strip()
    label_en = str(row.get("label_en") or row.get("name_en") or "").strip()
    label_ar = str(row.get("label_ar") or row.get("name_ar") or "").strip()
    if field == "country":
        label_en = label_en or str(row.get("country_name") or "").strip()
    label = label_en or label_ar or name
    return {
        "value": name,
        "label": label,
        "label_ar": label_ar or label_en,
        "label_en": label_en or label,
        "code": str(row.get("code") or "").strip(),
        "pcode": str(row.get("pcode") or "").strip(),
        "doctype": str(level_spec(field_to_level(field))["doctype"]),
    }


def ancestor_filters(field: str, values: dict[str, Any]) -> dict[str, Any]:
    """Return the Link-query filters for ``field`` from ancestor values."""
    index = field_to_level(field)
    if index <= 0:
        return {}
    filters: dict[str, Any] = {}
    for spec in LEVELS[1:index + 1]:
        parent = str(spec["parent"])
        value = values.get(parent)
        if value not in (None, "", False):
            filters[parent] = value
    return filters


def chain_from_record(field: str, name: Any, record: dict[str, Any]) -> dict[str, dict]:
    """Build the complete ancestor chain from a selected row's own fields.

    ``record`` may be a Frappe document serialised as a dict. Values already
    present on the record win; ``parent_pcode`` is *not* invented as a Link
    value, it is only kept as provenance/code information.
    """
    record = dict(record or {})
    index = field_to_level(field)
    chain: dict[str, dict] = {}
    if index < 0:
        return chain
    chain[field] = {
        **option_from_row(field, {**record, "name": name or record.get("name")}),
        "value": name or record.get("name") or "",
    }
    for spec in reversed(LEVELS[:index]):
        parent_field = str(spec["field"])
        value = record.get(parent_field)
        row = {"name": value} if value else {}
        chain[parent_field] = option_from_row(parent_field, row)
        chain[parent_field]["value"] = value or ""
    return chain


def merge_chain(*chains: dict[str, dict]) -> dict[str, dict]:
    """Prefer the most specific chain entry for each level."""
    merged: dict[str, dict] = {}
    for chain in chains:
        for field, value in (chain or {}).items():
            if value and value.get("value"):
                merged[field] = dict(value)
            elif field not in merged:
                merged[field] = dict(value or {})
    return merged


def chain_from_filters(values: dict[str, Any]) -> dict[str, dict]:
    """Build display entries from ancestor values already on a form."""
    return {
        field: {"value": values.get(field) or "", **option_from_row(field, {"name": values.get(field)})}
        for field in FIELDS
    }


def visible_chain(chain: dict[str, dict]) -> list[dict]:
    """Return the chain in Country → Community order, omitting empty gaps."""
    rows = []
    for field in FIELDS:
        row = dict(chain.get(field) or {})
        if row.get("value"):
            rows.append({"field": field, **row})
    return rows


def _fetch_options(field: str, filters: dict[str, Any]) -> list[dict]:
    if frappe is None:  # pragma: no cover - pure tests never call this
        return []
    spec = level_spec(field_to_level(field))
    doctype = str(spec["doctype"])
    fields = ["name", "code", "pcode", "label_en", "label_ar", "country_name"]
    fields = [name for name in fields if frappe.get_meta(doctype).has_field(name)]
    try:
        rows = frappe.get_all(doctype, filters=filters or None, fields=fields,
                              order_by=f"`tab{doctype}`.`name` asc",
                              limit_page_length=0)
    except Exception:
        # An unsaved/new parent has no valid children yet; report an empty
        # list rather than breaking the form.
        return []
    return [option_from_row(field, row) for row in rows]


def cascade(field: str, value: Any = None, **values: Any) -> dict:
    """Return ancestor chain plus child options for one selected Link field.

    ``value`` is the value of ``field`` itself. ``values`` may carry any of
    the other five levels (e.g. ``country="IL"``). The returned ``filters``
    are suitable for ``frm.set_query`` and the ``options`` are *valid Link
    targets* from the local bench.
    """
    if frappe is not None and not frappe.has_permission("Place", "read"):
        frappe.throw("Not permitted to read hierarchy data.", frappe.PermissionError)
    if frappe is not None:
        from siraj_research.api.throttle import guard

        # Forms call this on load and on every ancestor change; the budget is
        # generous but still bounds a runaway client.
        guard("cascade", limit=1200)
    field = str(field or "")
    if field not in FIELDS:
        return {"error": f"Unknown hierarchy field: {field}", "chain": {}, "options": []}
    values = {key: val for key, val in values.items() if key in FIELDS}
    chain = chain_from_filters(values)
    if value not in (None, "", False):
        spec = level_spec(field_to_level(field))
        doctype = str(spec["doctype"])
        if frappe is not None:
            try:
                doc = frappe.get_doc(doctype, value)
                record = doc.as_dict() if hasattr(doc, "as_dict") else dict(doc)
            except Exception:
                record = {"name": value}
        else:  # pragma: no cover - pure tests use chain_from_record directly
            record = {"name": value}
        chain = merge_chain(chain, chain_from_record(field, value, record))
    populated = {key: row.get("value") for key, row in chain.items()}
    # Per-country configuration (active levels, skipped tiers, labels). The
    # country may itself come from the selected record (upward flow).
    country = populated.get("country") or values.get("country")
    if country and frappe is not None:
        config = country_config(str(country))
    else:
        config = config_payload(effective_levels(), country=None)
    levels = list(config["levels"])
    active_filters = configured_ancestor_filters(field, populated, levels)
    # Legacy rows can carry a value at an inactive level; keep the stricter
    # filter only for active ancestors so a skipped tier cannot break the
    # dropdown.
    filters = active_filters or ancestor_filters(field, populated)
    return {
        "field": field,
        "value": value or "",
        "label": label_for(levels, field),
        "chain": chain,
        "chain_list": visible_chain(chain),
        "filters": filters,
        "options": _fetch_options(field, filters),
        "level_config": config,
        "source": "local-bench",
    }


if frappe is not None:  # pragma: no cover - bench only
    # The Desk client calls this exact path, so the primary function must be
    # whitelisted (an alias would not make the undecorated name callable).
    cascade = frappe.whitelist()(cascade)

    @frappe.whitelist()
    def cascade_endpoint(field, value=None, **values):
        """Backwards-compatible alias for newer clients."""
        if not frappe.has_permission("Place", "read"):
            frappe.throw("Not permitted to read hierarchy data.", frappe.PermissionError)
        return cascade(field, value, **values)
