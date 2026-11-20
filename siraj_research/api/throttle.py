"""Per-user rate limiting for public/whitelisted geo endpoints.

Frappe protects the site globally (login, request rate), but a form that calls
``hierarchy_for_point`` on every map drag — or a script that hammers
``resolve_batch`` — deserves a per-endpoint budget. This module uses Frappe's
shared cache (Redis) with fixed windows and an atomic ``incrby``; it is a
no-op outside a bench, so pure tests and migrations are unaffected.

Budget is read from ``Geo Settings.endpoint_rate_limit_per_min`` (default 240,
``0`` disables it). Raise ``frappe.TooManyRequestsError`` (HTTP 429) so clients
can back off instead of retrying blindly.
"""

from __future__ import annotations

import time

try:  # pragma: no cover - exercised inside a bench
    import frappe
except Exception:  # pragma: no cover - pure-Python tests
    frappe = None  # type: ignore[assignment]

DEFAULT_LIMIT = 240
BUCKET_PREFIX = "siraj:geo-throttle:"


def configured_limit() -> int:
    if frappe is None:
        return 0
    try:
        value = frappe.db.get_single_value("Geo Settings", "endpoint_rate_limit_per_min")
    except Exception:  # pragma: no cover - before migrate
        return DEFAULT_LIMIT
    if value in (None, ""):
        return DEFAULT_LIMIT
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return DEFAULT_LIMIT


def guard(bucket: str, limit: int | None = None, seconds: int = 60) -> None:
    """Consume one unit from ``bucket`` for the current user.

    Raises ``frappe.TooManyRequestsError`` when the budget is exhausted.
    """
    if frappe is None:
        return
    # Tests and migrations must not compete for the production budget.
    if getattr(frappe.flags, "in_test", False) or getattr(frappe.flags, "in_install", False):
        return
    budget = configured_limit() if limit is None else int(limit)
    if budget <= 0:
        return
    try:
        user = str(getattr(frappe.session, "user", None) or "Guest")
    except Exception:  # pragma: no cover
        user = "Guest"
    window = int(time.time() // max(1, seconds))
    key = f"{BUCKET_PREFIX}{bucket}:{user}:{window}"
    try:
        counter = frappe.cache.incrby(key, 1)
        if int(counter or 0) == 1:
            frappe.cache.expire(key, max(2, seconds * 2))
        if int(counter or 0) > budget:
            frappe.throw(
                f"Too many {bucket} requests ({budget}/min). Retry in a moment.",
                frappe.TooManyRequestsError,
            )
    except Exception as exc:
        # Re-raise the rate-limit error; swallow cache-backend hiccups so a
        # Redis outage degrades to "unlimited" rather than "endpoint down".
        if exc.__class__.__name__ in ("TooManyRequestsError", "RateLimitExceededError"):
            raise
        return


def reset(bucket: str | None = None) -> None:
    """Clear counters (operator/bench use only)."""
    if frappe is None:
        return
    try:
        prefix = f"{BUCKET_PREFIX}{bucket}:" if bucket else BUCKET_PREFIX
        frappe.cache.delete_keys(prefix)
    except Exception:  # pragma: no cover
        pass
