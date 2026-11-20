"""Per-country administrative-level configuration (variable depth + labels).

SIRAJ's hierarchy has a fixed *schema* — six DocTypes, one per level — but
countries do not all use six levels. A country may have no municipality tier,
may call its first-level unit a "Region" instead of a "Governorate", or may
stop at district level. Those differences are configuration, never schema
changes:

* ``Admin Level``            — the global catalogue (level 0…5, DocType, default
                               English/Arabic labels, prefix).
* ``Country Level Config``   — one row per country; ``hierarchy_depth`` plus a
                               ``Country Level Row`` child table that can mark a
                               level inactive (skipped) and override its labels.
* ``Country``               — the native Frappe DocType. Level 0 is always
                               active; it has no per-country override.

Everything in this module is pure Python until a function explicitly touches
``frappe``, so the resolution rules can be unit-tested without a bench.

Skip semantics
--------------

A level marked inactive is a *skipped* level: its Link field must stay empty,
and its children attach to the nearest active ancestor. For example, with
``municipality`` inactive, a ``Village`` row has ``country``, ``governorate``
and ``district`` set and ``municipality`` empty. Nothing is fabricated.

A record may be incomplete (a Village known only at district level) but it may
not contain a *hole*: if a deeper ancestor is set while the nearest active
ancestor is empty, validation reports ``missing_active_ancestor``. This keeps
imports flexible while still rejecting "Village → Governorate but no District"
when District is an active tier.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

try:  # pragma: no cover - exercised inside a bench
    import frappe
except Exception:  # pragma: no cover - pure-Python tests
    frappe = None  # type: ignore[assignment]

#: Canonical six-level contract. ``field`` is both the resolver chain key and
#: the Link field name on the level's own DocType (and on every deeper level).
DEFAULT_LEVELS: tuple[dict[str, Any], ...] = (
    {
        "level": 0,
        "key": "country",
        "field": "country",
        "doctype": "Country",
        "parent_field": None,
        "label_en": "Country",
        "label_ar": "الدولة",
        "prefix": "C",
    },
    {
        "level": 1,
        "key": "governorate",
        "field": "governorate",
        "doctype": "Governorate",
        "parent_field": "country",
        "label_en": "Governorate",
        "label_ar": "المحافظة",
        "prefix": "G",
    },
    {
        "level": 2,
        "key": "district",
        "field": "district",
        "doctype": "District",
        "parent_field": "governorate",
        "label_en": "District",
        "label_ar": "المنطقة",
        "prefix": "D",
    },
    {
        "level": 3,
        "key": "municipality",
        "field": "municipality",
        "doctype": "Municipality",
        "parent_field": "district",
        "label_en": "Municipality",
        "label_ar": "البلدية",
        "prefix": "M",
    },
    {
        "level": 4,
        "key": "village",
        "field": "village",
        "doctype": "Village",
        "parent_field": "municipality",
        "label_en": "Village",
        "label_ar": "القرية",
        "prefix": "V",
    },
    {
        "level": 5,
        "key": "community",
        "field": "community",
        "doctype": "Community",
        "parent_field": "village",
        "label_en": "Community",
        "label_ar": "المجتمع",
        "prefix": "Q",
    },
)

LEVEL_KEYS: tuple[str, ...] = tuple(str(spec["key"]) for spec in DEFAULT_LEVELS)
LEVEL_FIELDS: tuple[str, ...] = tuple(str(spec["field"]) for spec in DEFAULT_LEVELS)
MAX_LEVEL = DEFAULT_LEVELS[-1]["level"]
CACHE_PREFIX = "siraj:geo_levels:"
CACHE_TTL_SECONDS = 3600

_TRUE = {"1", "true", "yes", "y", "on", "active"}


# ---------------------------------------------------------------------------
# Catalogue helpers (pure)
# ---------------------------------------------------------------------------

def level_spec(level: int | str) -> dict[str, Any] | None:
    """Return the catalogue row for a level number or key/field name."""
    if isinstance(level, bool):
        return None
    if isinstance(level, int):
        for spec in DEFAULT_LEVELS:
            if spec["level"] == level:
                return dict(spec)
        return None
    text = str(level or "").strip().lower()
    if text.isdigit():
        return level_spec(int(text))
    for spec in DEFAULT_LEVELS:
        if text in (str(spec["key"]), str(spec["field"]), str(spec["doctype"]).lower()):
            return dict(spec)
    return None


def level_of(field: str) -> int:
    """Level number for a chain field/key, or ``-1`` when unknown."""
    spec = level_spec(field)
    return int(spec["level"]) if spec else -1


def default_rows() -> list[dict[str, Any]]:
    """Rows suitable for a fresh ``Country Level Config.levels`` child table."""
    return [
        {
            "level": spec["level"],
            "level_key": spec["key"],
            "is_active": 1,
            "label_en": spec["label_en"],
            "label_ar": spec["label_ar"],
            "sort_order": spec["level"] * 10,
            "skip_reason": "",
        }
        for spec in DEFAULT_LEVELS
    ]


def _as_bool(value: Any, default: bool = True) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return bool(value)
    return str(value).strip().lower() in _TRUE


def normalise_rows(rows: Iterable[Mapping[str, Any]] | None) -> dict[int, dict[str, Any]]:
    """Normalise child-table rows to ``{level: {...}}``.

    Unknown level numbers and duplicate rows are ignored (last row wins) so a
    malformed configuration can never crash resolution; callers that care
    about integrity should validate with :func:`validate_config_rows`.
    """
    result: dict[int, dict[str, Any]] = {}
    for row in rows or []:
        if not isinstance(row, Mapping):
            continue
        try:
            level = int(row.get("level"))
        except (TypeError, ValueError):
            spec = level_spec(row.get("level_key") or row.get("field"))
            if not spec:
                continue
            level = int(spec["level"])
        if level < 0 or level > MAX_LEVEL:
            continue
        spec = level_spec(level)
        result[level] = {
            "level": level,
            "level_key": str(row.get("level_key") or spec["key"]),
            "is_active": 1 if level == 0 else int(_as_bool(row.get("is_active"), True)),
            "label_en": str(row.get("label_en") or "").strip(),
            "label_ar": str(row.get("label_ar") or "").strip(),
            "sort_order": int(row.get("sort_order") or level * 10),
            "skip_reason": str(row.get("skip_reason") or "").strip(),
        }
    return result


def validate_config_rows(rows: Iterable[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    """Return structural problems in a per-country configuration."""
    problems: list[dict[str, Any]] = []
    seen: set[int] = set()
    for index, row in enumerate(rows or []):
        try:
            level = int(row.get("level"))
        except (TypeError, ValueError):
            problems.append({"index": index, "reason": "invalid_level"})
            continue
        if level < 1 or level > MAX_LEVEL:
            problems.append({"index": index, "reason": "level_out_of_range", "level": level})
        if level in seen:
            problems.append({"index": index, "reason": "duplicate_level", "level": level})
        seen.add(level)
        if not str(row.get("label_en") or "").strip():
            problems.append({"index": index, "reason": "missing_label_en", "level": level})
    missing = [level for level in range(1, MAX_LEVEL + 1) if level not in seen]
    if missing:
        problems.append({"reason": "missing_level_rows", "levels": missing})
    return problems


def effective_levels(
    overrides: Iterable[Mapping[str, Any]] | None = None,
    *,
    depth: int | None = None,
) -> list[dict[str, Any]]:
    """Merge catalogue defaults with per-country overrides.

    Returns level 0…5 in ascending order, each carrying:

    ``is_active``        whether the level exists for this country
    ``label_en/ar``      display label (override or catalogue default)
    ``parent_field``     Link field holding the nearest active ancestor
                         (``None`` for level 0 and for inactive levels)
    ``ancestor_fields``  every active ancestor field, country-first
    ``depth``            the highest active level number
    """
    rows = normalise_rows(overrides)
    levels: list[dict[str, Any]] = []
    for spec in DEFAULT_LEVELS:
        row = rows.get(int(spec["level"]), {})
        level = int(spec["level"])
        active = True if level == 0 else bool(row.get("is_active", 1))
        if depth is not None and level > int(depth):
            active = False
        levels.append(
            {
                **spec,
                "is_active": active,
                "label_en": row.get("label_en") or spec["label_en"],
                "label_ar": row.get("label_ar") or spec["label_ar"],
                "sort_order": row.get("sort_order") or level * 10,
                "skip_reason": row.get("skip_reason") or "",
            }
        )
    active_levels = [lv for lv in levels if lv["is_active"]]
    for lv in levels:
        if not lv["is_active"]:
            lv["parent_field"] = None
            lv["ancestor_fields"] = []
            lv["depth"] = max((x["level"] for x in active_levels), default=0)
            continue
        ancestors = [x for x in active_levels if x["level"] < lv["level"]]
        lv["ancestor_fields"] = [str(x["field"]) for x in ancestors]
        lv["parent_field"] = str(ancestors[-1]["field"]) if ancestors else None
        lv["depth"] = max((x["level"] for x in active_levels), default=0)
    return levels


def config_payload(
    levels: Iterable[Mapping[str, Any]],
    *,
    country: str | None = None,
    source: str = "default",
) -> dict[str, Any]:
    """JSON-safe configuration description used by the API and the UI."""
    levels = list(levels)
    by_field = {str(lv["field"]): lv for lv in levels}
    return {
        "country": country,
        "source": source,
        "depth": max((int(lv["level"]) for lv in levels if lv["is_active"]), default=0),
        "levels": [
            {
                "level": int(lv["level"]),
                "key": lv["key"],
                "field": lv["field"],
                "doctype": lv["doctype"],
                "is_active": bool(lv["is_active"]),
                "label_en": lv["label_en"],
                "label_ar": lv["label_ar"],
                "sort_order": lv["sort_order"],
                "parent_field": lv["parent_field"],
                "ancestor_fields": list(lv.get("ancestor_fields") or []),
                "skip_reason": lv.get("skip_reason") or "",
            }
            for lv in levels
        ],
        "labels_en": {field: lv["label_en"] for field, lv in by_field.items()},
        "labels_ar": {field: lv["label_ar"] for field, lv in by_field.items()},
        "active_fields": [str(lv["field"]) for lv in levels if lv["is_active"]],
        "inactive_fields": [str(lv["field"]) for lv in levels if not lv["is_active"]],
    }


def label_for(levels: Iterable[Mapping[str, Any]], field: str, language: str = "en") -> str:
    """Translated level label with a catalogue fallback."""
    key = "label_ar" if str(language).lower().startswith("ar") else "label_en"
    fallback_key = "label_en"
    for lv in levels:
        if str(lv["field"]) == str(field):
            return str(lv.get(key) or lv.get(fallback_key) or field)
    spec = level_spec(field)
    return str((spec or {}).get(key) or (spec or {}).get(fallback_key) or field)


# ---------------------------------------------------------------------------
# Chain rules (pure)
# ---------------------------------------------------------------------------

def nearest_active_ancestor(
    levels: Iterable[Mapping[str, Any]], field: str
) -> dict[str, Any] | None:
    """Nearest active level *above* ``field`` for this country."""
    spec = level_spec(field)
    if not spec:
        return None
    candidates = [
        lv
        for lv in levels
        if lv["is_active"] and int(lv["level"]) < int(spec["level"])
    ]
    return dict(candidates[-1]) if candidates else None


def ancestor_filters(
    field: str,
    values: Mapping[str, Any] | None,
    levels: Iterable[Mapping[str, Any]],
) -> dict[str, str]:
    """Link-query filters for ``field`` built from its active ancestors.

    Only populated values are used, so selecting a District without a Country
    filters the Village list by District alone. Inactive levels are never
    included, which is what makes ``Village`` filtered by ``District`` work
    when ``Municipality`` is skipped.
    """
    spec = level_spec(field)
    if not spec:
        return {}
    values = dict(values or {})
    filters: dict[str, str] = {}
    for lv in levels:
        if not lv["is_active"] or int(lv["level"]) >= int(spec["level"]):
            continue
        name = str(lv["field"])
        value = values.get(name)
        if value not in (None, "", False):
            filters[name] = str(value)
    return filters


def clear_descendants(
    field: str, levels: Iterable[Mapping[str, Any]]
) -> list[str]:
    """Active level fields that must be cleared when ``field`` changes.

    Used by the client (on ancestor change) and by the server controller so a
    stale grandchild can never survive a re-parenting.
    """
    spec = level_spec(field)
    if not spec:
        return []
    return [
        str(lv["field"])
        for lv in levels
        if lv["is_active"] and int(lv["level"]) > int(spec["level"])
    ]


def validate_chain(
    levels: Iterable[Mapping[str, Any]],
    values: Mapping[str, Any] | None,
    *,
    own_field: str | None = None,
    allow_inactive: bool = False,
    allow_partial: bool = False,
) -> list[dict[str, Any]]:
    """Validate one record's hierarchy values against a country configuration.

    Checks, in order:

    1. A level marked inactive for the country must not carry a value.
    2. A populated ancestor chain must not contain a hole: if any ancestor
       deeper than the nearest active ancestor is populated, the nearest active
       ancestor must be populated too.
    3. The record's own level must be active (unless ``allow_inactive``).
    """
    levels = list(levels)
    values = dict(values or {})
    errors: list[dict[str, Any]] = []
    active_by_field = {str(lv["field"]): lv for lv in levels if lv["is_active"]}

    for lv in levels:
        field = str(lv["field"])
        value = values.get(field)
        if not lv["is_active"] and value not in (None, "", False) and not allow_inactive:
            errors.append(
                {
                    "code": "inactive_level_populated",
                    "field": field,
                    "level": int(lv["level"]),
                    "message": (
                        f"{lv['label_en']} is not an active level for this country; "
                        "clear the field or activate the level in Country Level Config."
                    ),
                }
            )

    own_spec = level_spec(own_field) if own_field else None
    if own_spec is None:
        # Without an explicit level (imports, audits) the deepest populated
        # value defines the record's level.
        populated_levels = [
            int(lv["level"])
            for lv in levels
            if lv["is_active"] and values.get(str(lv["field"])) not in (None, "", False)
        ]
        if populated_levels:
            own_spec = level_spec(max(populated_levels))

    if own_spec and not allow_inactive:
        own_level = int(own_spec["level"])
        if own_level > 0 and str(own_spec["field"]) not in active_by_field:
            errors.append(
                {
                    "code": "inactive_own_level",
                    "field": str(own_spec["field"]),
                    "level": own_level,
                    "message": (
                        f"{own_spec['label_en']} is inactive for this country; "
                        "activate it in Country Level Config before creating records."
                    ),
                }
            )
        nearest = nearest_active_ancestor(levels, str(own_spec["field"]))
        if nearest and values.get(str(nearest["field"])) in (None, "", False):
            # A record attached to nothing but its country is *incomplete* and
            # allowed (imports attach a row to the country when a parent is
            # unknown). As soon as any deeper ancestor is set, the chain must
            # be complete up to the nearest active ancestor — otherwise a
            # Village could point at a District while the active Municipality
            # tier stays empty. ``allow_partial`` is used by bulk importers and
            # by the boundary synchroniser, which records the gap and leaves the
            # audit to report it.
            populated_deeper = [
                lv
                for lv in levels
                if lv["is_active"]
                and 0 < int(lv["level"]) < own_level
                and values.get(str(lv["field"])) not in (None, "", False)
            ]
            if populated_deeper and not allow_partial:
                errors.append(
                    {
                        "code": "missing_active_ancestor",
                        "field": str(nearest["field"]),
                        "level": int(nearest["level"]),
                        "message": (
                            f"{nearest['label_en']} is required when another active ancestor is set "
                            "(the level is active for this country)."
                        ),
                    }
                )
    return errors


# ---------------------------------------------------------------------------
# Frappe adapter (cached)
# ---------------------------------------------------------------------------

def _cache_key(country: str) -> str:
    return f"{CACHE_PREFIX}{country}"


def clear_cache(country: str | None = None) -> None:
    """Drop cached configurations (called by the DocType controllers)."""
    if frappe is None:
        return
    try:
        if country:
            frappe.cache.delete_value(_cache_key(str(country)))
        else:
            frappe.cache.delete_keys(CACHE_PREFIX)
    except Exception:  # pragma: no cover - cache backend hiccup must not block saves
        pass


def country_config(country: str | None) -> dict[str, Any]:
    """Resolved configuration for a Country document name (cached per site)."""
    if frappe is None or not country:
        return config_payload(effective_levels(), country=country)
    key = _cache_key(str(country))
    try:
        cached = frappe.cache.get_value(key)
        if cached:
            return cached
    except Exception:  # pragma: no cover
        cached = None
    overrides: list[dict[str, Any]] = []
    depth: int | None = None
    source = "default"
    try:
        if frappe.db.exists("Country Level Config", {"country": country}):
            doc = frappe.get_doc("Country Level Config", {"country": country})
            overrides = [row.as_dict() if hasattr(row, "as_dict") else dict(row) for row in doc.levels or []]
            depth = int(doc.hierarchy_depth) if doc.hierarchy_depth else None
            source = "override"
    except Exception:  # pragma: no cover - new site before migrate
        overrides = []
    payload = config_payload(effective_levels(overrides, depth=depth), country=country, source=source)
    try:
        frappe.cache.set_value(key, payload, expires_in_sec=CACHE_TTL_SECONDS)
    except Exception:  # pragma: no cover
        pass
    return payload


def levels_for_country(country: str | None) -> list[dict[str, Any]]:
    """Effective level rows (dicts) for a country."""
    return list(country_config(country)["levels"])


def labels_for_country(country: str | None) -> dict[str, dict[str, str]]:
    """``{field: {"en": ..., "ar": ...}}`` for forms and API payloads."""
    payload = country_config(country)
    return {
        field: {"en": payload["labels_en"].get(field, field), "ar": payload["labels_ar"].get(field, field)}
        for field in LEVEL_FIELDS
    }


def default_config_payload() -> dict[str, Any]:
    """Site-wide default configuration (used before any country is chosen)."""
    return config_payload(effective_levels(), country=None)


if frappe is not None:  # pragma: no cover - bench only

    @frappe.whitelist()
    def get_level_config(country=None):
        """Return the resolved level configuration for a country.

        Read-only and permission-checked (any user who may read Places may
        read the labels). Used by the cascade widget and the Desk form to
        render per-country labels such as "Region" vs "Governorate".
        """
        if not frappe.has_permission("Place", "read"):
            frappe.throw("Not permitted to read hierarchy configuration.", frappe.PermissionError)
        from siraj_research.api.throttle import guard

        guard("level_config", limit=600)
        payload = country_config(country) if country else default_config_payload()
        return payload
