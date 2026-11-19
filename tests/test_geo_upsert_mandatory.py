"""Regression: imported rows satisfy mandatory bilingual label fields."""

import sys
import types

import pytest

from siraj_research import geo_hierarchy as gh


class FakeDoc:
    def __init__(self, values):
        self.values = dict(values)

    def get(self, field):
        return self.values.get(field)

    def set(self, field, value):
        self.values[field] = value

    @property
    def name(self):
        return self.values.get("name")

    def insert(self, **kwargs):
        self.values["name"] = self.values["code"]
        return self

    def save(self, **kwargs):
        return self


class FakeDB:
    def exists(self, *args, **kwargs):
        return None


def test_upsert_level_supplies_arabic_fallback(monkeypatch):
    created = []
    fake = types.ModuleType("frappe")
    fake.db = FakeDB()
    fake.has_permission = lambda *args, **kwargs: True
    fake.get_doc = lambda values: created.append(FakeDoc(values)) or created[-1]
    monkeypatch.setitem(sys.modules, "frappe", fake)
    monkeypatch.setattr(gh, "frappe", fake)

    result = gh.upsert_level({
        "doctype": "Governorate",
        "level": 1,
        "field": "governorate",
        "code": "IQ-18",
        "pcode": "IQ.18",
        "label_en": "Wasit",
        "parent_field": "country",
        "admin_level_type": "GeoNames level 1",
    }, "Iraq", dataset="GEONAMES-ADMIN")

    assert result["status"] == "created"
    values = created[0].values
    assert values["label_ar"] == "Wasit"
    assert values["admin_level_type"] == "GeoNames level 1"
    assert values["country"] == "Iraq"
