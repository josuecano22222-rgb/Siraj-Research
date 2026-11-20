# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
"""Editable administrative level.

``validate()`` is the server-side half of the cascading-filter contract: it
reconciles stale ancestors, rejects inactive/skipped-level values, enforces
the per-country chain and stamps the denormalised ancestry fields.
"""

from frappe.model.document import Document

from siraj_research.geo_lineage import validate_hierarchy_document


class Governorate(Document):
    def validate(self):
        validate_hierarchy_document(self)
