# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
"""Reusable administrative-place handle (see siraj_research.geo_admin)."""

from __future__ import annotations

import frappe
from frappe.model.document import Document

from siraj_research.geo_admin import prepare_document


class GeographicAdministration(Document):
    def validate(self):
        prepare_document(self)

    @frappe.whitelist()
    def refresh_from_hierarchy(self):
        """Recompute names, ancestry and centroid from the linked records."""
        prepare_document(self)
        self.save()
        return {
            "title": self.title,
            "ancestry_path": self.ancestry_path,
            "hierarchy_level": self.hierarchy_level,
        }
