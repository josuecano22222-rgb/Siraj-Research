"""Permission-isolation unit tests for api/entity_profile.py and api/relationship_profile.py (C-02)."""

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def _field_ns(**kwargs):
	defaults = {
		"fieldname": "",
		"fieldtype": "Data",
		"label": "",
		"options": "",
		"hidden": 0,
		"permlevel": 0,
	}
	defaults.update(kwargs)
	ns = types.SimpleNamespace(**defaults)
	# Mimic Frappe DocField.get(...) WITHOUT containing document runtime values
	ns.get = lambda key, default=None: getattr(ns, key, default)
	return ns


class _DocStub(dict):
	def __init__(self, doctype, name, meta, **values):
		super().__init__(values)
		self.doctype = doctype
		self.name = name
		self.meta = meta
		self.owner = "gd1@example.com"
		self.modified = "2026-11-24 00:00:00"
		self.docstatus = 0

	def get_title(self):
		tf = self.meta.get_title_field() or "name"
		return self.get(tf) or self.name

	def check_permission(self, ptype="read"):
		return True


class ProfilePrivacyTest(unittest.TestCase):
	def _build_env(self):
		denied_docs = {
			("Place", "PLC-GC"),
			("Institution", "INST-GC"),
			("Source", "SRC-GC"),
			("Military Unit", "UNIT-GC"),
			("File", "FILE-PRIVATE"),
		}
		titles = {
			("Place", "PLC-GC", "display_name"): "GC Secret Citadel",
			("Place", "PLC-GD", "display_name"): "GD Harbor",
			("Institution", "INST-GC", "display_name"): "GC Shadow Directorate",
			("Institution", "INST-GD", "display_name"): "GD Civic Bureau",
			("Source", "SRC-GC", "display_name"): "GC Eyes-Only Dossier",
			("Military Unit", "UNIT-GD", "unit_name"): "GD 10th Brigade",
			("Military Unit", "UNIT-GC", "unit_name"): "GC 99th Brigade",
		}

		person_meta_fields = [
			_field_ns(fieldname="display_name", fieldtype="Data", label="Display name"),
			_field_ns(fieldname="birthplace", fieldtype="Link", label="Place of birth", options="Place"),
			_field_ns(fieldname="evidence", fieldtype="Table", label="Evidence", options="Evidence"),
		]
		rel_meta_fields = [
			_field_ns(fieldname="display_name", fieldtype="Data", label="Display name"),
			_field_ns(fieldname="relationship_type", fieldtype="Link", label="Type", options="Relationship Type"),
			_field_ns(fieldname="subject_type", fieldtype="Link", label="Subject type", options="DocType"),
			_field_ns(fieldname="subject", fieldtype="Dynamic Link", label="Subject", options="subject_type"),
			_field_ns(fieldname="object_type", fieldtype="Link", label="Object type", options="DocType"),
			_field_ns(fieldname="object", fieldtype="Dynamic Link", label="Object", options="object_type"),
			_field_ns(fieldname="primary_source", fieldtype="Link", label="Primary source", options="Source"),
			_field_ns(fieldname="evidence", fieldtype="Table", label="Evidence", options="Evidence"),
		]
		evidence_meta_fields = [
			_field_ns(fieldname="source", fieldtype="Link", label="Source", options="Source"),
		]

		def make_meta(dt):
			if dt == "Person":
				fields = person_meta_fields
				tf = "display_name"
			elif dt == "Relationship":
				fields = rel_meta_fields
				tf = "display_name"
			elif dt == "Evidence":
				fields = evidence_meta_fields
				tf = "name"
			elif dt == "Military Unit":
				fields = []
				tf = "unit_name"
			elif dt in ("Place", "Institution", "Source"):
				fields = []
				tf = "display_name"
			else:
				fields = []
				tf = "name"
			return types.SimpleNamespace(
				fields=fields,
				get_title_field=lambda: tf,
				get_table_fields=lambda: [f for f in fields if f.fieldtype == "Table"],
				get_field=lambda fn: next((f for f in fields if f.fieldname == fn), None),
			)

		gd_person = _DocStub(
			"Person",
			"PER-GD",
			make_meta("Person"),
			display_name="GD Field Commander",
			birthplace="PLC-GC",
			evidence=[{"source": "SRC-GC"}],
		)
		gd_rel = _DocStub(
			"Relationship",
			"REL-GD",
			make_meta("Relationship"),
			display_name="REL-GD",
			relationship_type="ISO_AFFILIATED",
			subject_type="Person",
			subject="PER-GD",
			object_type="Institution",
			object="INST-GC",
			primary_source="SRC-GC",
			evidence=[{"source": "SRC-GC"}],
		)
		docs = {
			("Person", "PER-GD"): gd_person,
			("Relationship", "REL-GD"): gd_rel,
		}

		def has_permission(doctype, ptype="read", doc=None, **kwargs):
			doc_name = getattr(doc, "name", doc)
			if doc_name is not None and (doctype, doc_name) in denied_docs:
				return False
			return True

		def get_list(doctype, filters=None, or_filters=None, fields=None, limit=None, **kwargs):
			if doctype == "Relationship":
				if filters and filters.get("subject") == "PER-GD":
					return [
						{
							"name": "REL-GD",
							"subject": "PER-GD",
							"subject_type": "Person",
							"object": "INST-GC",
							"object_type": "Institution",
							"relationship_type": "ISO_AFFILIATED",
							"direction": "Directed",
							"workflow_state": "Draft",
							"docstatus": 0,
						}
					]
				return []
			if doctype == "Military Unit":
				# Only GD unit is returned by permission-scoped get_list (UNIT-GC is filtered out!)
				return [{"name": "UNIT-GD"}]
			if doctype == "File":
				return [
					{
						"name": "FILE-PUBLIC",
						"file_name": "gd-note.txt",
						"file_url": "/files/gd-note.txt",
						"file_type": "TXT",
						"creation": "2026-11-24",
					},
					{
						"name": "FILE-PRIVATE",
						"file_name": "gc-secret-attachment.pdf",
						"file_url": "/private/files/gc-secret-attachment.pdf",
						"file_type": "PDF",
						"creation": "2026-11-24",
					},
				]
			return []

		def get_all(doctype, *args, **kwargs):
			if doctype == "File":
				raise AssertionError("entity_profile must not use frappe.get_all for File attachments")
			return []

		def db_count(*args, **kwargs):
			raise AssertionError("entity_profile must not use unscoped frappe.db.count for inbound links")

		frappe_stub = types.ModuleType("frappe")
		frappe_stub._ = lambda s: s
		frappe_stub.whitelist = lambda *a, **k: (lambda fn: fn)
		frappe_stub.PermissionError = PermissionError
		frappe_stub.DoesNotExistError = LookupError
		frappe_stub.local = types.SimpleNamespace(lang="en")
		frappe_stub.has_permission = has_permission
		frappe_stub.get_meta = make_meta
		frappe_stub.get_doc = lambda dt, name: docs[(dt, name)]
		frappe_stub.get_list = get_list
		frappe_stub.get_all = get_all
		frappe_stub.throw = lambda msg, exc=Exception: (_ for _ in ()).throw(exc(msg))
		frappe_stub.db = types.SimpleNamespace(
			get_value=lambda dt, name, field: titles.get((dt, name, field)),
			count=db_count,
		)

		meta_mod = types.ModuleType("frappe.model.meta")
		meta_mod.get_meta = make_meta
		modules_mod = types.ModuleType("frappe.modules")
		modules_mod.scrub = lambda s: s.lower().replace(" ", "_")
		audit_mod = types.ModuleType("siraj_research.api.audit")
		audit_mod.collect_history = lambda *a, **k: {"history": []}

		injected = {
			"frappe": frappe_stub,
			"frappe.model": types.ModuleType("frappe.model"),
			"frappe.model.meta": meta_mod,
			"frappe.modules": modules_mod,
			"siraj_research.api.audit": audit_mod,
		}
		return injected

	def _load(self, rel_path, mod_name, injected):
		spec = importlib.util.spec_from_file_location(mod_name, ROOT / rel_path)
		mod = importlib.util.module_from_spec(spec)
		with patch.dict(sys.modules, injected):
			spec.loader.exec_module(mod)
		return mod

	def test_entity_profile_redacts_foreign_links_outbound_inbound_counts_and_files(self):
		injected = self._build_env()
		ep = self._load("siraj_research/api/entity_profile.py", "ep_under_test", injected)
		with patch.dict(sys.modules, injected):
			profile = ep.get_entity_profile("Person", "PER-GD")
		dumped = json.dumps(profile)

		# Foreign titles and private attachments must never appear anywhere in payload.
		self.assertNotIn("GC Secret Citadel", dumped)
		self.assertNotIn("GC Shadow Directorate", dumped)
		self.assertNotIn("GC Eyes-Only Dossier", dumped)
		self.assertNotIn("gc-secret-attachment.pdf", dumped)
		self.assertIn("gd-note.txt", dumped)

		# Outbound Link block actually ran (fixing f.get(f.fieldname) -> doc.get(f.fieldname))
		# and marked the unreadable Link as restricted.
		outbound = profile["connections"]["outbound_links"]
		self.assertTrue(
			any(o["field"] == "birthplace" and o["restricted"] is True and o["title"] == "Restricted" for o in outbound)
		)

		# Inbound counts come from permission-scoped reads (1 GD Military Unit, not db.count across GC).
		inbound_mu = next(i for i in profile["connections"]["inbound_links"] if i["doctype"] == "Military Unit")
		self.assertEqual(inbound_mu["count"], 1)
		self.assertEqual([s["title"] for s in inbound_mu["sample"]], ["GD 10th Brigade"])

	def test_relationship_profile_fmt_value_redacts_unreadable_links_and_leaves_resolve_endpoint_intact(self):
		injected = self._build_env()
		rp = self._load("siraj_research/api/relationship_profile.py", "rp_under_test", injected)
		rel_profile = rp.get_relationship_profile("REL-GD")
		dumped = json.dumps(rel_profile)

		self.assertNotIn("GC Eyes-Only Dossier", dumped)
		self.assertNotIn("GC Shadow Directorate", dumped)
		self.assertEqual(rel_profile["endpoints"]["object"]["readable"], False)
		self.assertEqual(rel_profile["endpoints"]["object"]["title"], "INST-GC")


if __name__ == "__main__":
	unittest.main()
