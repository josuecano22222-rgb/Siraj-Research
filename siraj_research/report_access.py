"""Permission-aware report helpers, including custom per-document permission hooks."""
from __future__ import annotations

import frappe


def readable_rows(doctype, fields, filters=None, page_size=200):
    """Iterate permitted documents without an implicit 20-row limit.

    Frappe's list query enforces role, owner, user and query permissions. The
    additional document check enforces custom has_permission hooks as well.
    """
    if not frappe.has_permission(doctype, "read"):
        return
    start = 0
    fields = list(dict.fromkeys(["name", *fields]))
    while True:
        rows = frappe.get_list(doctype, fields=fields, filters=filters or {},
                               order_by="name asc", limit_start=start,
                               limit_page_length=page_size)
        for row in rows:
            if frappe.has_permission(doctype, "read", doc=row["name"], throw=False):
                yield row
        if len(rows) < page_size:
            break
        start += len(rows)


def can_read_link(doctype, name, allowed_types):
    """Don't expose a Dynamic Link to an inaccessible or deleted document."""
    if not name or doctype not in allowed_types:
        return False
    if not frappe.has_permission(doctype, "read") or not frappe.db.exists(doctype, name):
        return False
    return frappe.has_permission(doctype, "read", doc=name, throw=False)
