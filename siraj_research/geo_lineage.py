"""Hierarchy integrity: denormalised ancestry and server-side chain validation.

The five app-owned hierarchy DocTypes (``Governorate`` … ``Community``) are
ordinary Frappe documents, so anything that can call ``doc.save()`` or
``frappe.client.insert`` can otherwise persist nonsense such as a Village
whose District belongs to a different Governorate. This module is the single
gatekeeper:

* ``validate_hierarchy_document(doc)`` — called from every level controller's
  ``validate()``. It reconciles stale ancestors, rejects structural holes,
  keeps ``is_active``/``disabled`` in sync and writes the denormalised
  ``ancestry_path`` / ``ancestry_labels`` / ``hierarchy_level`` fields.
* Pure helpers (``build_ancestry``, ``ancestor_chain``, ``reconcile_plan``)
  are importable without Frappe and covered by the pure-Python test suite.

Ancestry format
---------------

``ancestry_path``  ``"Iraq/IQ-BG/IQ-BG-KR"`` (stored Link values, ``/``-separated)
``ancestry_labels`` ``"Iraq > Baghdad > Karkh"`` (English labels)

Only segments that are actually set are stored; a skipped or unknown level
leaves no empty ``//`` segment. Reading a full chain therefore needs one row,
not five joins.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

try:  # pragma: no cover - exercised inside a bench
    import frappe
except Exception:  # pragma: no cover - pure-Python tests
    frappe = None  # type: ignore[assignment]

from siraj_research.geo_levels import (
    LEVEL_FIELDS,
    effective_levels,
    level_spec,
)

#: DocType → level number for the editable hierarchy.
LEVEL_DOCTYPES: dict[str, int] = {
    str(spec["doctype"]): int(spec["level"])
    for spec in (level_spec(i) for i in range(1, 6))
    if spec
}

PATH_SEPARATOR = "/"
LABEL_SEPARATOR = " › "
MAX_PATH_LENGTH = 500


def level_of_doctype(doctype: str | None) -> int | None:
    """Level number of a hierarchy DocType, or ``None`` for anything else."""
    return LEVEL_DOCTYPES.get(str(doctype or ""))


def own_field(doctype: str | None) -> str | None:
    spec = level_spec(level_of_doctype(doctype) or -1) if doctype else None
    return str(spec["field"]) if spec else None


def field_values(values: Mapping[str, Any] | Any) -> dict[str, Any]:
    """Extract the six hierarchy values from a mapping or a document."""
    if values is None:
        return {}
    if isinstance(values, Mapping):
        source = values
    else:
        source = {field: getattr(values, field, None) for field in LEVEL_FIELDS}
    return {field: source.get(field) for field in LEVEL_FIELDS}


def ancestor_chain(level: int, values: Mapping[str, Any]) -> list[tuple[int, str, Any]]:
    """Active-less view of the populated ancestors, country-first.

    Returns ``(level, field, value)`` tuples for every *populated* ancestor of
    ``level``. Missing levels are simply absent; this is what makes skipped
    levels and incomplete records representable.
    """
    out: list[tuple[int, str, Any]] = []
    for spec_level in range(0, int(level)):
        spec = level_spec(spec_level)
        if not spec:
            continue
        field = str(spec["field"])
        value = values.get(field)
        if value not in (None, "", False):
            out.append((spec_level, field, value))
    return out


def build_ancestry(
    doctype: str | None,
    values: Mapping[str, Any] | Any,
    levels: list[dict[str, Any]] | None = None,
    *,
    labels: Mapping[str, Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    """Build the denormalised ancestry for a record.

    ``levels`` is the effective per-country configuration (see
    :func:`siraj_research.geo_levels.effective_levels`). It only affects which
    labels are shown and whether an inactive field is reported as ``stale``;
    the path itself always follows what is stored on the record.
    """
    level = level_of_doctype(doctype)
    if level is None:
        return {"path": "", "labels": "", "level": None, "segments": [], "stale": []}
    values = field_values(values)
    levels = list(levels or effective_levels())
    by_field = {str(lv["field"]): lv for lv in levels}
    segments: list[dict[str, Any]] = []
    stale: list[str] = []
    own = str(level_spec(level)["field"])
    for spec_level in range(0, level + 1):
        spec = level_spec(spec_level)
        if not spec:
            continue
        field = str(spec["field"])
        value = values.get(field)
        if value in (None, "", False):
            continue
        configured = by_field.get(field, {})
        if configured and not configured.get("is_active", True):
            stale.append(field)
        label_override = (labels or {}).get(field, {})
        # ``labels`` carries human place names; the fallback is the record key
        # (a code), never the level label ("Governorate"), which would read as
        # "Iraq > Baghdad > Governorate" instead of the place.
        label = str(label_override.get("en") or value)
        segments.append(
            {
                "level": spec_level,
                "field": field,
                "key": value,
                "label": label,
                "label_ar": str(label_override.get("ar") or label_override.get("en") or value),
                "active": bool(configured.get("is_active", True)),
                "own": field == own,
            }
        )
    path = PATH_SEPARATOR.join(str(seg["key"]) for seg in segments)[:MAX_PATH_LENGTH]
    label_text = LABEL_SEPARATOR.join(str(seg["label"]) for seg in segments)[:MAX_PATH_LENGTH]
    return {
        "path": path,
        "labels": label_text,
        "level": level,
        "segments": segments,
        "stale": stale,
    }


def reconcile_plan(
    level: int,
    values: Mapping[str, Any],
    changed_fields: set[str] | None = None,
    levels: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Pure part of ancestor reconciliation (no database access).

    Returns which ancestor fields to clear when a shallower ancestor changed.
    The database-dependent part (reading a parent's own chain) lives in
    :func:`_parent_chain`.
    """
    levels = list(levels or effective_levels())
    active = {str(lv["field"]): lv for lv in levels if lv["is_active"]}
    changed = {str(field) for field in (changed_fields or set()) if str(field) in LEVEL_FIELDS}
    changed_ancestors = sorted(
        (int(active[field]["level"]), field)
        for field in changed
        if field in active and int(active[field]["level"]) < int(level)
    )
    if not changed_ancestors:
        return {"clear": [], "anchor": None, "reason": "no_ancestor_change"}
    source_level, source_field = changed_ancestors[0]
    clear = [
        str(lv["field"])
        for lv in levels
        if lv["is_active"] and source_level < int(lv["level"]) < int(level)
        and values.get(str(lv["field"])) not in (None, "", False)
    ]
    return {
        "clear": clear,
        "anchor": source_field,
        "reason": "ancestor_changed",
    }


def _parent_chain(doctype: str, name: str) -> dict[str, Any]:
    """Read a parent record's own ancestor values (one small query)."""
    if frappe is None:
        return {}
    level = level_of_doctype(doctype)
    if level is None:
        return {}
    fields = [str(level_spec(i)["field"]) for i in range(0, level)]
    if not fields:
        return {}
    try:
        row = frappe.db.get_value(doctype, name, fields, as_dict=True)
    except Exception:  # pragma: no cover - stale link / deleted row
        return {}
    return {field: (row or {}).get(field) for field in fields}


def reconcile_ancestors(doc, levels: list[dict[str, Any]]) -> dict[str, Any]:
    """Make a document's ancestor links mutually consistent before validating.

    * When an ancestor changed, every deeper ancestor is cleared (the spec's
      "changing an ancestor clears dependent descendants" rule).
    * Empty higher ancestors are completed from the deepest populated
      ancestor's own chain (useful for imports and API writes).
    * A populated ancestor that contradicts its parent record is *rejected*,
      never silently rewritten, unless it was cleared in the first step.
    """
    doctype = getattr(doc, "doctype", "")
    level = level_of_doctype(doctype)
    if level is None or level == 0:
        return {"cleared": [], "filled": []}
    values = field_values(doc)
    changed = {field for field in LEVEL_FIELDS if _has_changed(doc, field)}
    plan = reconcile_plan(level, values, changed, levels)
    cleared: list[str] = []
    for field in plan["clear"]:
        doc.set(field, None)
        values[field] = None
        cleared.append(field)

    filled = _complete_upwards(doc, level, values, levels)
    errors = _inconsistent_links(doc, level, field_values(doc))
    if errors and frappe is not None:
        frappe.throw(
            "\n".join(err["message"] for err in errors),
            frappe.ValidationError,
            title="Hierarchy mismatch",
        )
    return {"cleared": cleared, "filled": filled}


def _has_changed(doc, field: str) -> bool:
    checker = getattr(doc, "has_value_changed", None)
    if not callable(checker) or getattr(doc, "is_new", lambda: True)():
        return False
    try:
        return bool(checker(field))
    except Exception:  # pragma: no cover - unsaved child rows
        return False


def _complete_upwards(doc, level: int, values: Mapping[str, Any],
                      levels: list[dict[str, Any]]) -> list[str]:
    """Fill empty higher ancestors from the deepest populated ancestor."""
    active = {str(lv["field"]): lv for lv in levels if lv["is_active"]}
    populated = [
        (int(spec_level), field, value)
        for spec_level, field, value in ancestor_chain(level, values)
        if field in active
    ]
    if not populated:
        return []
    deepest_level, deepest_field, deepest_value = populated[-1]
    parent_doctype = str(level_spec(deepest_field)["doctype"])
    parent_values = _parent_chain(parent_doctype, str(deepest_value))
    if not parent_values:
        return []
    filled: list[str] = []
    for spec_level in range(0, deepest_level):
        field = str(level_spec(spec_level)["field"])
        value = parent_values.get(field)
        if value in (None, "", False):
            continue
        if values.get(field) in (None, "", False):
            doc.set(field, value)
            filled.append(field)
    return filled


def _inconsistent_links(doc, level: int, values: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Reject a chain whose populated ancestors disagree with their parents."""
    if frappe is None:
        return []
    errors: list[dict[str, Any]] = []
    for spec_level, field, value in ancestor_chain(level, values):
        parent_doctype = str(level_spec(field)["doctype"])
        if parent_doctype == "Country":
            continue
        parent_values = _parent_chain(parent_doctype, str(value))
        for ancestor_level in range(0, spec_level):
            ancestor_field = str(level_spec(ancestor_level)["field"])
            expected = parent_values.get(ancestor_field)
            actual = values.get(ancestor_field)
            if expected and actual and str(expected) != str(actual):
                errors.append(
                    {
                        "code": "inconsistent_ancestor",
                        "field": ancestor_field,
                        "level": ancestor_level,
                        "message": (
                            f"{doc.doctype}: {field} {value} belongs to "
                            f"{ancestor_field} {expected}, not {actual}."
                        ),
                    }
                )
    return errors


def record_labels(
    doctype: str | None,
    values: Mapping[str, Any] | Any,
    own_labels: Mapping[str, str] | None = None,
) -> dict[str, dict[str, str]]:
    """Human labels for a record and its populated ancestors.

    One indexed lookup per ancestor (at most four) keeps a save cheap while
    producing a readable ``ancestry_labels`` string.
    """
    level = level_of_doctype(doctype)
    if level is None:
        return {}
    values = field_values(values)
    labels: dict[str, dict[str, str]] = {}
    own = own_field(doctype)
    if own and own_labels and own_labels.get("en"):
        labels[own] = {
            "en": str(own_labels.get("en")),
            "ar": str(own_labels.get("ar") or own_labels.get("en")),
        }
    for _spec_level, field, value in ancestor_chain(level, values):
        if field == "country":
            labels[field] = {"en": str(value), "ar": str(value)}
            continue
        if frappe is None:
            continue
        doctype = str(level_spec(field)["doctype"])
        try:
            row = frappe.db.get_value(doctype, value, ["label_en", "label_ar"], as_dict=True)
        except Exception:  # pragma: no cover - deleted parent / stale link
            row = None
        if row:
            labels[field] = {
                "en": row.get("label_en") or str(value),
                "ar": row.get("label_ar") or row.get("label_en") or str(value),
            }
    return labels


def sync_active_flag(doc) -> None:
    """Keep the canonical ``is_active`` and legacy ``disabled`` in sync."""
    fields = getattr(doc, "meta", None)
    has_active = bool(fields and fields.has_field("is_active"))
    has_disabled = bool(fields and fields.has_field("disabled"))
    if not has_active or not has_disabled:
        return
    if _has_changed(doc, "is_active") and not _has_changed(doc, "disabled"):
        doc.disabled = 0 if doc.get("is_active") else 1
    elif _has_changed(doc, "disabled") and not _has_changed(doc, "is_active"):
        doc.is_active = 0 if doc.get("disabled") else 1
    elif doc.get("is_active") in (None, ""):
        doc.is_active = 0 if doc.get("disabled") else 1


def validate_hierarchy_document(doc, method: str | None = None) -> dict[str, Any]:
    """Controller entry point: validate, reconcile and stamp ancestry.

    Raises ``frappe.ValidationError`` with every problem listed, so a direct
    REST/script save cannot persist an invalid combination. Returns a summary
    dict (also handy in tests and ``bench geo audit``).
    """
    from siraj_research.geo_levels import country_config, validate_chain

    doctype = getattr(doc, "doctype", "")
    level = level_of_doctype(doctype)
    if level is None or level == 0:
        return {"applied": False}

    country = doc.get("country")
    config = country_config(country)
    levels = list(config["levels"])

    sync_active_flag(doc)
    reconciled = reconcile_ancestors(doc, levels)

    values = field_values(doc)
    errors = validate_chain(
        levels,
        values,
        own_field=str(level_spec(level)["field"]),
        allow_partial=bool(getattr(getattr(doc, "flags", None), "siraj_allow_hierarchy_gaps", False)),
    )
    if errors:
        if frappe is None:
            raise ValueError("; ".join(err["message"] for err in errors))
        frappe.throw(
            "\n".join(err["message"] for err in errors),
            frappe.ValidationError,
            title="Hierarchy configuration",
        )

    # A country-level configuration can be introduced after rows exist. Note
    # (do not silently drop) records that now sit at an inactive level.
    ancestry = build_ancestry(
        doctype,
        values,
        levels,
        labels=record_labels(
            doctype,
            values,
            {"en": doc.get("label_en"), "ar": doc.get("label_ar")},
        ),
    )
    for field in ("ancestry_path", "ancestry_labels", "hierarchy_level"):
        if doc.meta.has_field(field):
            doc.set(field, ancestry["path"] if field == "ancestry_path"
                    else ancestry["labels"] if field == "ancestry_labels"
                    else ancestry["level"])
    if doc.meta.has_field("admin_level_type") and not doc.get("admin_level_type"):
        doc.admin_level_type = next(
            (
                lv["label_en"]
                for lv in levels
                if str(lv["field"]) == str(level_spec(level)["field"])
            ),
            None,
        )

    if ancestry["stale"] and frappe is not None:
        frappe.msgprint(
            "This record uses levels marked inactive for "
            f"{country or 'its country'}: {', '.join(ancestry['stale'])}. "
            "Activate them in Country Level Config or clear the values.",
            indicator="orange",
            alert=True,
        )

    return {
        "applied": True,
        "level": level,
        "values": values,
        "ancestry": ancestry,
        "reconciled": reconciled,
    }
