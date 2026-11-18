"""Coverage reporting for the global administrative hierarchy.

The curated seed deliberately samples the lower levels; this module makes the
remaining work visible. ``coverage_report()`` is safe to run from
``bench execute`` and never writes data.
"""

from __future__ import annotations

from typing import Any

try:  # pragma: no cover - bench only
    import frappe
except Exception:  # pragma: no cover - pure-Python tests
    frappe = None  # type: ignore[assignment]


LEVEL_DOCTYPES = {
    0: "Country",
    1: "Governorate",
    2: "District",
    3: "Municipality",
    4: "Village",
    5: "Community",
}


def summarise_counts(rows_by_level: dict[int, list[dict]]) -> dict[str, Any]:
    """Pure aggregation used by ``coverage_report`` and its unit tests."""
    totals = {str(level): len(rows or []) for level, rows in rows_by_level.items()}
    per_country: dict[str, dict[str, int]] = {}
    for level, rows in rows_by_level.items():
        if level == 0:
            continue
        for row in rows or []:
            country = row.get("country")
            if not country:
                continue
            bucket = per_country.setdefault(str(country), {})
            key = str(level)
            bucket[key] = bucket.get(key, 0) + 1
    without_final = sorted(
        name for name, counts in per_country.items()
        if not counts.get("5") and not counts.get("4")
    )
    full_chains = sorted(
        name for name, counts in per_country.items()
        if all(str(level) in counts for level in (1, 2, 3, 4, 5))
    )
    return {
        "totals": totals,
        "per_country": per_country,
        "countries_without_village_or_community": without_final,
        "countries_with_full_chain": full_chains,
        "country_count": len(per_country),
    }


def _resolve_country(value: str) -> str | None:
    if frappe is None:
        return None
    for filters in ({"name": value}, {"code": str(value).upper()}, {"country_name": value}):
        found = frappe.db.exists("Country", filters)
        if found:
            return found if isinstance(found, str) else value
    return None


def coverage_report(country: str | None = None) -> dict:
    """Return row counts by level, globally or for one country.

    ``country`` may be a Country document name or an ISO-2 code.
    """
    if frappe is None:
        return {"error": "frappe unavailable", "levels": LEVEL_DOCTYPES}
    country_name = _resolve_country(country) if country else None
    if country and not country_name:
        return {"error": f"Country not found: {country}"}
    rows_by_level: dict[int, list[dict]] = {}
    for level, doctype in LEVEL_DOCTYPES.items():
        fields = ["name", "code"] if level == 0 else ["name", "code", "country"]
        filters: dict[str, Any] = {}
        if country_name and level == 0:
            filters = {"name": country_name}
        elif country_name:
            filters = {"country": country_name}
        rows_by_level[level] = frappe.get_all(
            doctype, fields=fields, filters=filters, limit_page_length=0)
    result = summarise_counts(rows_by_level)
    result["country"] = country_name
    result["levels"] = {str(k): v for k, v in LEVEL_DOCTYPES.items()}
    return result


def missing_final_levels(country: str | None = None) -> dict:
    """Short report of countries still lacking village/community coverage."""
    report = coverage_report(country)
    if "error" in report:
        return report
    missing = report["countries_without_village_or_community"]
    return {
        "country": report.get("country"),
        "missing_count": len(missing),
        "countries": missing[:200],
        "truncated": len(missing) > 200,
    }
