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
	def __init__(self, doctype, name, meta, allowed_permlevels=(0,), **values):
		super().__init__(values)
		self.doctype = doctype
		self.name = name
		self.meta = meta
		self._allowed_permlevels = set(allowed_permlevels)
		self.owner = "gd1@example.com"
		self.modified = "2026-11-24 00:00:00"
		self.docstatus = 0

	def get_title(self):
		tf = self.meta.get_title_field() or "name"
		return self.get(tf) or self.name

	def check_permission(self, ptype="read"):
		return True

	def get_permlevel_access(self, permission_type="read"):
		return sorted(self._allowed_permlevels)

	def has_permlevel_access_to(self, fieldname, df=None, permission_type="read"):
		if not df:
			df = self.meta.get_field(fieldname)
		return (df.permlevel or 0) in self.get_permlevel_access(permission_type)


class ProfilePrivacyTest(unittest.TestCase):
	def _build_env(self, allowed_permlevels=(0,)):
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
			_field_ns(fieldname="father_person", fieldtype="Link", label="Father", options="Person"),
			_field_ns(fieldname="data_group", fieldtype="Link", label="Data Group", options="Data Group"),
			_field_ns(fieldname="workflow_state", fieldtype="Link", label="Record status", options="Workflow State"),
			_field_ns(
				fieldname="documentation_level",
				fieldtype="Link",
				label="Documentation level",
				options="Documentation Level",
			),
			_field_ns(
				fieldname="authentication_level",
				fieldtype="Link",
				label="Authentication level",
				options="Authentication Level",
			),
			_field_ns(fieldname="name_original_lang", fieldtype="Link", label="Language", options="Language"),
			_field_ns(
				fieldname="future_vocab",
				fieldtype="Link",
				label="Future vocabulary",
				options="Brand New Vocabulary",
			),
			_field_ns(fieldname="dyn_target_type", fieldtype="Data", label="Dyn target type"),
			_field_ns(fieldname="dyn_target", fieldtype="Dynamic Link", label="Dyn target", options="dyn_target_type"),
			_field_ns(fieldname="dyn_entity_type", fieldtype="Data", label="Dyn entity type"),
			_field_ns(fieldname="dyn_entity", fieldtype="Dynamic Link", label="Dyn entity", options="dyn_entity_type"),
			_field_ns(
				fieldname="researcher_notes",
				fieldtype="Small Text",
				label="Researcher notes",
				permlevel=1,
			),
			_field_ns(fieldname="siblings", fieldtype="Table", label="Siblings", options="Person Sibling"),
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
			_field_ns(
				fieldname="researcher_notes",
				fieldtype="Small Text",
				label="Researcher notes",
				permlevel=1,
			),
			_field_ns(fieldname="evidence", fieldtype="Table", label="Evidence", options="Evidence"),
		]
		evidence_meta_fields = [
			_field_ns(fieldname="source", fieldtype="Link", label="Source", options="Source"),
		]
		sibling_meta_fields = [
			_field_ns(fieldname="sibling_name", fieldtype="Data", label="Sibling name"),
			_field_ns(
				fieldname="personal_id_number",
				fieldtype="Data",
				label="Personal ID",
				permlevel=1,
			),
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
			elif dt == "Person Sibling":
				fields = sibling_meta_fields
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
			allowed_permlevels=allowed_permlevels,
			display_name="GD Field Commander",
			birthplace="PLC-GC",
			father_person="PER-GD",
			data_group="GD",
			workflow_state="Draft",
			documentation_level="Fully documented",
			authentication_level="Corroborated",
			name_original_lang="ar",
			future_vocab="VOCAB-001",
			dyn_target_type="Brand New Vocabulary",
			dyn_target="VOCAB-001",
			dyn_entity_type="Institution",
			dyn_entity="INST-GD",
			researcher_notes="GD-INTERNAL-SENSITIVE-NOTE",
			siblings=[
				{
					"sibling_name": "GD Sibling Alpha",
					"personal_id_number": "GD-SIBLING-PERMLEVEL1-ID",
				}
			],
			evidence=[{"source": "SRC-GC"}],
		)
		gd_rel = _DocStub(
			"Relationship",
			"REL-GD",
			make_meta("Relationship"),
			allowed_permlevels=allowed_permlevels,
			display_name="REL-GD",
			relationship_type="ISO_AFFILIATED",
			subject_type="Person",
			subject="PER-GD",
			object_type="Institution",
			object="INST-GC",
			primary_source="SRC-GC",
			researcher_notes="GD-REL-REVIEWER-ONLY-NOTE",
			evidence=[{"source": "SRC-GC"}],
		)
		docs = {
			("Person", "PER-GD"): gd_person,
			("Relationship", "REL-GD"): gd_rel,
		}

		# Exact Frappe 15.128.0 signature: NO `permlevel` keyword argument!
		def has_permission(
			doctype=None,
			ptype="read",
			doc=None,
			user=None,
			throw=False,
			*,
			parent_doctype=None,
			debug=False,
			ignore_share_permissions=False,
		):
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
		logged_errors = []
		frappe_stub.log_error = lambda *a, **k: logged_errors.append((a, k))
		frappe_stub._logged_errors = logged_errors
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

		# Brand-new vocabulary types are NOT readable in this test so _fmt_value also redacts VOCAB-001 -> None;
		# verify PLC-GC, INST-GC, and SRC-GC never leak anywhere in entity_profile.
		self.assertNotIn("GC Secret Citadel", dumped)
		self.assertNotIn("GC Shadow Directorate", dumped)
		self.assertNotIn("GC Eyes-Only Dossier", dumped)
		self.assertNotIn("PLC-GC", dumped)
		self.assertNotIn("INST-GC", dumped)
		self.assertNotIn("SRC-GC", dumped)
		self.assertNotIn("gc-secret-attachment.pdf", dumped)
		self.assertIn("gd-note.txt", dumped)

		# Outbound Link block actually ran (fixing f.get(f.fieldname) -> doc.get(f.fieldname))
		# and redacted the unreadable Link with name=None, title="Restricted", restricted=True.
		outbound = profile["connections"]["outbound_links"]
		self.assertTrue(
			any(
				o["field"] == "birthplace"
				and o["restricted"] is True
				and o["name"] is None
				and o["title"] == "Restricted"
				for o in outbound
			)
		)
		# _fmt_value on birthplace (scalar section) and evidence.source (child row) also sets name=None:
		all_fields = {f["fieldname"]: f for s in profile["sections"] for f in s["fields"]}
		self.assertEqual(
			all_fields["birthplace"]["value"],
			{"type": "link", "doctype": "Place", "name": None, "title": "Restricted", "restricted": True},
		)
		ev_source = profile["children"]["evidence"]["rows"][0]["source"]["value"]
		self.assertEqual(
			ev_source,
			{"type": "link", "doctype": "Source", "name": None, "title": "Restricted", "restricted": True},
		)
		# _authored_relationships redacts counterpart_name=None when unreadable:
		rel_row = profile["connections"]["relationships"][0]
		self.assertIsNone(rel_row["counterpart_name"])
		self.assertEqual(rel_row["counterpart_title"], "Restricted")
		self.assertTrue(rel_row["counterpart_restricted"])

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
		self.assertNotIn("SRC-GC", dumped)
		# _fmt_value on Relationship.primary_source and Evidence.source redacts name=None:
		rel_fields = {f["fieldname"]: f for s in rel_profile["sections"] for f in s["fields"]}
		self.assertEqual(
			rel_fields["primary_source"]["value"],
			{"type": "link", "doctype": "Source", "name": None, "title": "Restricted", "restricted": True},
		)
		# _resolve_endpoint remains untouched per standing C-02 constraint:
		self.assertEqual(rel_profile["endpoints"]["object"]["readable"], False)
		self.assertEqual(rel_profile["endpoints"]["object"]["title"], "INST-GC")

	def test_relationship_profile_permlevel_1_stripped_for_permlevel_0_and_present_for_reviewer(self):
		viewer_env = self._build_env(allowed_permlevels=(0,))
		rp = self._load("siraj_research/api/relationship_profile.py", "rp_pl0", viewer_env)
		with patch.dict(sys.modules, viewer_env):
			rel_pl0 = json.dumps(rp.get_relationship_profile("REL-GD"))
		self.assertNotIn("GD-REL-REVIEWER-ONLY-NOTE", rel_pl0)

		rev_env = self._build_env(allowed_permlevels=(0, 1))
		rp_rev = self._load("siraj_research/api/relationship_profile.py", "rp_pl1", rev_env)
		with patch.dict(sys.modules, rev_env):
			rel_pl1 = json.dumps(rp_rev.get_relationship_profile("REL-GD"))
		self.assertIn("GD-REL-REVIEWER-ONLY-NOTE", rel_pl1)

	def test_entity_profile_permlevel_1_parent_and_child_stripped_for_permlevel_0_and_present_for_reviewer(self):
		viewer_env = self._build_env(allowed_permlevels=(0,))
		ep = self._load("siraj_research/api/entity_profile.py", "ep_pl0", viewer_env)
		with patch.dict(sys.modules, viewer_env):
			ent_pl0 = json.dumps(ep.get_entity_profile("Person", "PER-GD"))
		self.assertNotIn("GD-INTERNAL-SENSITIVE-NOTE", ent_pl0)
		self.assertNotIn("GD-SIBLING-PERMLEVEL1-ID", ent_pl0)

		rev_env = self._build_env(allowed_permlevels=(0, 1))
		ep_rev = self._load("siraj_research/api/entity_profile.py", "ep_pl1", rev_env)
		with patch.dict(sys.modules, rev_env):
			ent_pl1 = json.dumps(ep_rev.get_entity_profile("Person", "PER-GD"))
		self.assertIn("GD-INTERNAL-SENSITIVE-NOTE", ent_pl1)
		self.assertIn("GD-SIBLING-PERMLEVEL1-ID", ent_pl1)

	def test_inbound_links_avoids_per_row_has_permission_caps_with_n_plus_and_logs_errors(self):
		env = self._build_env()
		frappe_stub = env["frappe"]
		orig_has_perm = frappe_stub.has_permission
		doc_checks = []

		def tracked_has_perm(doctype=None, ptype="read", doc=None, **kw):
			if doctype == "Military Unit" and doc is not None:
				doc_checks.append((doctype, doc))
			return orig_has_perm(doctype=doctype, ptype=ptype, doc=doc, **kw)

		def capped_get_list(doctype, filters=None, or_filters=None, fields=None, limit=None, **kw):
			if doctype == "Military Unit":
				rows = [{"name": f"UNIT-GD-{i:04d}"} for i in range(250)]
				return rows[:limit] if limit else rows
			if doctype == "Command Appointment":
				raise RuntimeError("simulated query failure")
			return []

		frappe_stub.has_permission = tracked_has_perm
		frappe_stub.get_list = capped_get_list
		ep = self._load("siraj_research/api/entity_profile.py", "ep_cap", env)
		with patch.dict(sys.modules, env):
			profile = ep.get_entity_profile("Person", "PER-GD")

		# Zero per-row doc= has_permission / get_doc calls on inbound Military Unit rows!
		self.assertEqual(doc_checks, [])
		inbound_mu = next(
			i for i in profile["connections"]["inbound_links"] if i["doctype"] == "Military Unit"
		)
		self.assertEqual(inbound_mu["count"], "200+")
		self.assertEqual(inbound_mu["capped"], True)
		self.assertEqual(len(inbound_mu["sample"]), 5)
		self.assertEqual(profile["network_summary"]["inbound_count"], "200+")
		# Simulated Command Appointment failure was logged via frappe.log_error, not swallowed silently.
		self.assertTrue(len(frappe_stub._logged_errors) >= 1)

	def test_authored_relationships_checks_type_level_perm_excludes_cancelled_and_logs_errors(self):
		# 1) Type-level Relationship read denied -> skips query without calling get_list("Relationship").
		env_no_rel = self._build_env()
		orig_hp = env_no_rel["frappe"].has_permission
		rel_list_calls = []
		orig_gl = env_no_rel["frappe"].get_list

		def deny_rel_type(doctype=None, ptype="read", doc=None, **kw):
			if doctype == "Relationship" and doc is None:
				return False
			return orig_hp(doctype=doctype, ptype=ptype, doc=doc, **kw)

		def track_gl(doctype, *a, **kw):
			if doctype == "Relationship":
				rel_list_calls.append(kw)
			return orig_gl(doctype, *a, **kw)

		env_no_rel["frappe"].has_permission = deny_rel_type
		env_no_rel["frappe"].get_list = track_gl
		ep_no_rel = self._load("siraj_research/api/entity_profile.py", "ep_no_rel", env_no_rel)
		with patch.dict(sys.modules, env_no_rel):
			prof_no_rel = ep_no_rel.get_entity_profile("Person", "PER-GD")
		self.assertEqual(prof_no_rel["connections"]["relationships"], [])
		self.assertEqual(rel_list_calls, [])

		# 2) Query filters include docstatus < 2 and fields include 'name'; query errors are logged.
		env_err = self._build_env()
		seen_filters = []

		def fail_rel_gl(doctype, filters=None, fields=None, **kw):
			if doctype == "Relationship":
				seen_filters.append((filters, fields))
				raise RuntimeError("simulated Relationship query error")
			return []

		env_err["frappe"].get_list = fail_rel_gl
		ep_err = self._load("siraj_research/api/entity_profile.py", "ep_rel_err", env_err)
		with patch.dict(sys.modules, env_err):
			prof_err = ep_err.get_entity_profile("Person", "PER-GD")
		self.assertEqual(prof_err["connections"]["relationships"], [])
		self.assertTrue(len(seen_filters) >= 1)
		self.assertEqual(seen_filters[0][0].get("docstatus"), ("<", 2))
		self.assertIn("name", seen_filters[0][1])
		self.assertTrue(len(env_err["frappe"]._logged_errors) >= 1)

	def test_outbound_links_uses_entity_allowlist_for_links_and_dynamic_links(self):
		env = self._build_env()
		ep = self._load("siraj_research/api/entity_profile.py", "ep_outbound_sys", env)
		with patch.dict(sys.modules, env):
			profile = ep.get_entity_profile("Person", "PER-GD")
		outbound = profile["connections"]["outbound_links"]
		outbound_fields = {item["field"] for item in outbound}
		# Place, Person, and Dynamic Link -> Institution DO appear:
		self.assertIn("birthplace", outbound_fields)
		self.assertIn("father_person", outbound_fields)
		self.assertIn("dyn_entity", outbound_fields)
		# Brand-new vocabulary Link/Dynamic Link and system/workflow/tenant fields do NOT appear:
		for excluded in (
			"future_vocab",
			"dyn_target",
			"data_group",
			"workflow_state",
			"documentation_level",
			"authentication_level",
			"name_original_lang",
		):
			self.assertNotIn(excluded, outbound_fields)

	def test_inbound_links_skips_unpermitted_target_doctype_silently_with_zero_error_logs(self):
		env = self._build_env()
		frappe_stub = env["frappe"]
		orig_hp = frappe_stub.has_permission
		orig_gl = frappe_stub.get_list

		def deny_military_unit_type(doctype=None, ptype="read", doc=None, **kw):
			if doctype == "Military Unit" and doc is None:
				return False
			return orig_hp(doctype=doctype, ptype=ptype, doc=doc, **kw)

		def guard_gl(doctype, *a, **kw):
			if doctype == "Military Unit":
				raise AssertionError("get_list must not be called when target_dt read is denied")
			if doctype == "Command Appointment":
				raise frappe_stub.PermissionError("not permitted")
			return orig_gl(doctype, *a, **kw)

		frappe_stub.has_permission = deny_military_unit_type
		frappe_stub.get_list = guard_gl
		ep = self._load("siraj_research/api/entity_profile.py", "ep_f1", env)
		with patch.dict(sys.modules, env):
			profile = ep.get_entity_profile("Person", "PER-GD")

		inbound_dts = [item["doctype"] for item in profile["connections"]["inbound_links"]]
		self.assertNotIn("Military Unit", inbound_dts)
		self.assertNotIn("Command Appointment", inbound_dts)
		self.assertEqual(frappe_stub._logged_errors, [])


if __name__ == "__main__":
	unittest.main()
