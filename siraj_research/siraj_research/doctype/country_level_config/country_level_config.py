# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
"""Per-country administrative levels: active flags, ordering and labels.

Saving a configuration flushes the resolved-configuration cache, so forms and
APIs see the new labels/skips immediately without a restart.
"""

from __future__ import annotations

import frappe
from frappe.model.document import Document

from siraj_research.geo_levels import (
    DEFAULT_LEVELS,
    clear_cache,
    default_rows,
    level_spec,
    validate_config_rows,
)


class CountryLevelConfig(Document):
    def validate(self):
        self._ensure_all_levels()
        self._sync_level_keys()
        problems = validate_config_rows([row.as_dict() for row in self.levels or []])
        hard = [
            problem
            for problem in problems
            if problem.get("reason") in (
                "duplicate_level",
                "invalid_level",
                "level_out_of_range",
                "missing_label_en",
            )
        ]
        if hard:
            frappe.throw(
                "Invalid level configuration: "
                + "; ".join(str(problem) for problem in hard),
                frappe.ValidationError,
            )
        if self.hierarchy_depth not in (None, ""):
            depth = int(self.hierarchy_depth)
            if depth < 0 or depth > 5:
                frappe.throw("Hierarchy depth must be between 0 and 5.")

    def _ensure_all_levels(self):
        """Every configuration carries all six rows, even skipped ones.

        Keeping inactive rows present makes labels and skips explicit (and
        reversible) instead of relying on "row missing means active".
        """
        present = {int(row.level) for row in self.levels or [] if row.level not in (None, "")}
        depth = int(self.hierarchy_depth) if self.hierarchy_depth not in (None, "") else 5
        for row in default_rows():
            if row["level"] in present:
                continue
            payload = dict(row)
            if row["level"] > depth:
                payload["is_active"] = 0
            self.append("levels", payload)
        self.levels.sort(key=lambda row: int(row.level or 0))

    def _sync_level_keys(self):
        for row in self.levels or []:
            spec = level_spec(int(row.level)) if row.level not in (None, "") else None
            if spec:
                row.level_key = str(spec["key"])
            if not row.sort_order:
                row.sort_order = int(row.level or 0) * 10

    def on_update(self):
        clear_cache(self.country)

    def on_trash(self):
        clear_cache(self.country)

    def after_insert(self):
        clear_cache(self.country)

    @frappe.whitelist()
    def reset_to_defaults(self):
        """Replace the rows with the catalogue defaults (keeps the country)."""
        self.levels = []
        for row in default_rows():
            self.append("levels", row)
        self.hierarchy_depth = 5
        self.save()
        return {"levels": len(self.levels), "hierarchy_depth": self.hierarchy_depth}

    @frappe.whitelist()
    def activate_all_levels(self):
        """Make every catalogue level active with default labels."""
        self.hierarchy_depth = 5
        for row in self.levels or []:
            row.is_active = 1
        self.save()
        return {"active": [row.level for row in self.levels if row.is_active]}

    def level_labels(self) -> dict[str, dict[str, str]]:
        """Convenience accessor used by reports and the Explorer."""
        return {
            str(level_spec(int(row.level))["field"]): {
                "en": row.label_en or str(level_spec(int(row.level))["label_en"]),
                "ar": row.label_ar or row.label_en,
            }
            for row in self.levels or []
            if row.level not in (None, "")
        }


# Keep the catalogue importable for migrations that need the canonical list.
__all__ = ["DEFAULT_LEVELS", "CountryLevelConfig"]
