"""Regression: the curated Boundary Dataset satisfies all mandatory fields."""

import json
import sys
import types
from pathlib import Path

DOCTYPES = Path(__file__).resolve().parents[1] / "siraj_research" / "siraj_research" / "doctype"


class FakeDoc:
    def __init__(self, values):
        self.values = dict(values)
        self.inserted = False

    def __setattr__(self, key, value):
        if key in {"values", "inserted"}:
            object.__setattr__(self, key, value)
        else:
            self.values[key] = value

    def __getattr__(self, key):
        return self.values.get(key)

    def insert(self, **kwargs):
        self.inserted = True


class FakeDB:
    def exists(self, *args, **kwargs):
        return False


def test_reference_dataset_sets_every_mandatory_field(monkeypatch):
    fake = types.ModuleType("frappe")
    fake.db = FakeDB()
    created = {}

    def new_doc(doctype):
        doc = FakeDoc({"doctype": doctype})
        created[doctype] = doc
        return doc

    fake.new_doc = new_doc
    monkeypatch.setitem(sys.modules, "frappe", fake)

    import importlib

    import siraj_research.setup.master_data as md

    importlib.reload(md)
    assert md._ensure_reference_dataset() == "SIRAJ-REFERENCE"

    doc = created["Boundary Dataset"]
    assert doc.inserted is True
    values = doc.values
    schema = json.loads((DOCTYPES / "boundary_dataset" / "boundary_dataset.json").read_text())
    mandatory = [f["fieldname"] for f in schema["fields"] if f.get("reqd")]
    missing = [field for field in mandatory if values.get(field) in (None, "")]
    assert missing == []
    assert values["level"] == 0
    assert values["import_status"] == "Complete"
