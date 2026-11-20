# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
"""Global catalogue of administrative levels (level 0…5)."""

from __future__ import annotations

import frappe
from frappe.model.document import Document

from siraj_research.geo_levels import clear_cache, level_spec


class AdminLevel(Document):
    def validate(self):
        if self.level is None:
            frappe.throw("Level is required (0 = Country … 5 = Community).")
        if int(self.level) < 0 or int(self.level) > 5:
            frappe.throw("Level must be between 0 and 5.")
        if int(self.level) == 0:
            self.parent_level = None
        elif self.parent_level in (None, ""):
            self.parent_level = int(self.level) - 1
        self.level_key = (self.level_key or str(level_spec(int(self.level))["key"])).strip().lower()
        if not self.sort_order:
            self.sort_order = int(self.level) * 10

    def on_update(self):
        clear_cache()

    def on_trash(self):
        clear_cache()

    def after_insert(self):
        clear_cache()
