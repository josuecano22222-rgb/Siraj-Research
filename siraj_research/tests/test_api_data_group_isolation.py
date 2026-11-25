# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
"""Adversarial bench isolation suite across all @frappe.whitelist endpoints and Link guards (C-25).

Run on a live bench with:
    bench --site frappe.com run-tests --module siraj_research.tests.test_api_data_group_isolation

Pre-fix Phase 2 defects are decorated with ``@unittest.expectedFailure`` and citing
their exact Phase 2 work item (`C-01`..`C-12`) so they flip to ``unexpected success``
immediately if fixed and are promoted to strict assertions in Phase 2.
"""

from __future__ import annotations

import base64
import json
import unittest
from pathlib import Path
from typing import ClassVar

import frappe
from frappe.tests.utils import FrappeTestCase

from siraj_research import (
	geo_cascade,
	geo_hierarchy,
	geo_hierarchy_ui,
	geo_quality,
	local_maps,
	offline_bootstrap,
	tile_cache,
	treeview,
	visualization,
)
from siraj_research.api import (
	audit,
	boundary_import,
	diagnostics,
	entity_profile,
	geo_package,
	geo_resolve,
	map_relations,
	map_search,
	relationship_profile,
)
from siraj_research.tests._isolation_fixtures import (
	ALL_WHITELISTED_ENDPOINTS,
	GC_ADMIN_USER,
	GD_ADMIN_USER,
	NO_SIRAJ_USER,
	OFFICIAL_USER,
	RESEARCHER_GD_USER,
	REVIEWER_GD_USER,
	ROLE_ONLY_RESEARCHER_GD_USER,
	ROLE_ONLY_VIEWER_GD_USER,
	SAMPLE_POLYGON_GEOJSON,
	UNASSIGNED_USER,
	VIEWER_GD_USER,
	build_isolation_world,
	cleanup_isolation_caches,
)


class TestApiDataGroupIsolation(FrappeTestCase):
	"""Real FrappeTestCase adversarial isolation suite for GD / GC / unassigned / SIRAJ Official."""

	_upload_paths: ClassVar[list[str]] = []

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._upload_paths = []
		cls.world = build_isolation_world()

	@classmethod
	def tearDownClass(cls):
		cleanup_isolation_caches(cls._upload_paths)
		super().tearDownClass()

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_01_all_39_whitelisted_callables_registered_in_frappe_whitelisted(self):
		"""Every endpoint in ALL_WHITELISTED_ENDPOINTS is registered in frappe.whitelisted."""
		geo_meta = frappe.get_meta("Geo Settings")
		for fn in (
			"sb_offline_bootstrap",
			"bootstrap_running",
			"bootstrap_last_status",
			"cb_offline_bootstrap",
			"stop_bootstrap",
			"bootstrap_stop_requested",
			"sb_online_setup",
			"online_setup_enabled",
			"cb_online_setup",
			"run_online_setup",
		):
			self.assertIsNotNone(geo_meta.get_field(fn), f"Geo Settings missing field {fn}")

		self.assertEqual(len(ALL_WHITELISTED_ENDPOINTS), 39)
		for mod_name, fn_qualname in ALL_WHITELISTED_ENDPOINTS:
			mod = frappe.get_module(mod_name)
			if "." in fn_qualname:
				cls_name, attr_name = fn_qualname.split(".", 1)
				fn = getattr(getattr(mod, cls_name), attr_name)
			else:
				fn = getattr(mod, fn_qualname)
			self.assertIn(fn, frappe.whitelisted, f"{mod_name}.{fn_qualname} missing from frappe.whitelisted")

	def test_02_predictable_id_guessing_blocked_across_record_endpoints(self):
		"""Predictable IDs (PER-0001, PLC-0001, EVT-0001) and GC IDs cannot be read by GD or unassigned."""
		gc = self.world["gc"]
		gd = self.world["gd"]
		event_dt = "Research Event" if gc["research_event"] else "Siraj Event"
		event_id = gc["research_event"] or gc["siraj_event"]

		# Also explicitly probe canonical predictable naming-series IDs (PER-0001, PLC-0001, EVT-0001)
		# whether or not prior tests already incremented the series counter.
		predictable_targets = {
			("Person", gc["person"]),
			("Person", "PER-0001"),
			("Place", gc["place"]),
			("Place", "PLC-0001"),
			(event_dt, event_id),
			(event_dt, "EVT-0001"),
		}
		for caller in (GD_ADMIN_USER, VIEWER_GD_USER, UNASSIGNED_USER):
			frappe.set_user(caller)
			for dt, docname in predictable_targets:
				if not frappe.db.exists(dt, docname):
					# Even non-existent guessed IDs must never return foreign payloads.
					net = map_relations.get_entity_network(dt, docname)
					self.assertEqual(net["nodes"], [])
					continue
				if frappe.db.get_value(dt, docname, "data_group") != "GC":
					continue
				with self.assertRaises(frappe.PermissionError):
					audit.document_history(dt, docname)
				with self.assertRaises(frappe.PermissionError):
					entity_profile.get_entity_profile(dt, docname)
				with self.assertRaises(frappe.PermissionError):
					visualization.record_detail(dt, docname)
				net = map_relations.get_entity_network(dt, docname)
				self.assertEqual(net["nodes"], [])
				self.assertEqual(net["edges"], [])

			with self.assertRaises(frappe.PermissionError):
				relationship_profile.get_relationship_profile(gc["rel"])

		# Positive control: SIRAJ Official and GC1 can read GC predictable IDs; GD1 can read GD IDs.
		for allowed in (GC_ADMIN_USER, OFFICIAL_USER):
			frappe.set_user(allowed)
			hist = audit.document_history("Person", gc["person"])
			self.assertEqual(hist["name"], gc["person"])
			prof = entity_profile.get_entity_profile("Person", gc["person"])
			self.assertEqual(prof["header"]["name"], gc["person"])
			rel_prof = relationship_profile.get_relationship_profile(gc["rel"])
			self.assertEqual(rel_prof["header"]["name"], gc["rel"])

		frappe.set_user(GD_ADMIN_USER)
		self.assertEqual(visualization.record_detail("Person", gd["person"])["name"], gd["person"])

	def test_03_visualization_and_map_search_isolate_gc_rows(self):
		"""geographic_data, relationship_data, structure_data, search, and search_bbox hide GC from GD/unassigned."""
		gc = self.world["gc"]
		gd = self.world["gd"]

		frappe.set_user(GD_ADMIN_USER)
		geo = visualization.geographic_data()
		geo_names = {(p["doctype"], p["name"]) for p in geo["points"]}
		self.assertIn(("Person", gd["person"]), geo_names)
		self.assertNotIn(("Person", gc["person"]), geo_names)
		self.assertNotIn(("Place", gc["place"]), geo_names)

		rel = visualization.relationship_data(include_evidence=1)
		edge_names = {e["name"] for e in rel["edges"]}
		self.assertIn(gd["rel"], edge_names)
		self.assertNotIn(gc["rel"], edge_names)

		struct = visualization.structure_data("people")
		self.assertNotIn("GC Classified Commander", json.dumps(struct))

		search_hit = map_search.search("Classified", scope="records")
		self.assertEqual([r for r in search_hit["records"] if r["name"] == gc["person"]], [])
		coord_hit = map_search.search("31.5130, 34.4570", radius=5000)
		nearby_names = {item.get("name") for item in coord_hit["coordinate"]["nearby"]}
		self.assertNotIn(gc["person"], nearby_names)
		self.assertNotIn(gc["place"], nearby_names)

		bbox_hit = map_search.search_bbox(31.50, 34.44, 31.55, 34.49)
		bbox_names = {r["name"] for r in bbox_hit["records"]}
		self.assertIn(gd["person"], bbox_names)
		self.assertNotIn(gc["person"], bbox_names)
		self.assertEqual(map_search.region_children(0)["error"] if "error" in map_search.region_children(0) else None, None)

		# Unassigned user sees zero scoped rows across visualization & map_search.
		frappe.set_user(UNASSIGNED_USER)
		self.assertEqual(visualization.geographic_data()["points"], [])
		self.assertEqual(visualization.relationship_data()["nodes"], [])
		self.assertEqual(visualization.structure_data("people")["count"], 0)
		self.assertEqual(map_search.search_bbox(31.50, 34.44, 31.55, 34.49)["records"], [])

		# SIRAJ Official sees both GD and GC rows.
		frappe.set_user(OFFICIAL_USER)
		official_names = {(p["doctype"], p["name"]) for p in visualization.geographic_data()["points"]}
		self.assertIn(("Person", gc["person"]), official_names)
		self.assertIn(("Person", gd["person"]), official_names)

	def test_04_treeview_and_military_unit_descendants_isolate_gc(self):
		"""treeview.get_children and MilitaryUnit.get_descendants enforce row-level GD/GC isolation."""
		gc = self.world["gc"]
		gd = self.world["gd"]

		frappe.set_user(GD_ADMIN_USER)
		root_units = {row["value"] for row in treeview.get_children("Military Unit")}
		self.assertIn(gd["unit"], root_units)
		self.assertNotIn(gc["unit"], root_units)
		with self.assertRaises(frappe.PermissionError):
			treeview.get_children("Military Unit", parent=gc["unit"])

		gc_unit_doc = frappe.get_doc("Military Unit", gc["unit"])
		with self.assertRaises(frappe.PermissionError):
			gc_unit_doc.get_descendants()

		frappe.set_user(UNASSIGNED_USER)
		self.assertEqual(treeview.get_children("Place"), [])

		frappe.set_user(GC_ADMIN_USER)
		self.assertIn(gc["child_unit"], frappe.get_doc("Military Unit", gc["unit"]).get_descendants())

	def test_05_geo_quality_report_isolates_gc_rows_c01(self):
		"""C-01: geo_quality.quality_report must not leak GC names/coordinates via frappe.get_all."""
		gc_person = self.world["gc"]["person"]
		gd_person = self.world["gd"]["person"]
		# Set both GD and GC persons to Null Island (0.0, 0.0) so readable rows appear in samples
		# (Frappe MariaDB Float columns are NOT NULL DEFAULT 0).
		frappe.set_user("Administrator")
		frappe.db.set_value("Person", gc_person, {"latitude": 0.0, "longitude": 0.0}, update_modified=False)
		frappe.db.set_value("Person", gd_person, {"latitude": 0.0, "longitude": 0.0}, update_modified=False)
		try:
			frappe.set_user(GD_ADMIN_USER)
			report = geo_quality.quality_report("Person")
			sample_names = [row["name"] for row in report["samples"].get("Person", [])]
			self.assertIn(gd_person, sample_names)
			self.assertNotIn(gc_person, sample_names)

			# Unassigned user sees 0 rows; user with no SIRAJ roles sees empty report.
			frappe.set_user(UNASSIGNED_USER)
			unassigned_report = geo_quality.quality_report("Person")
			self.assertEqual(unassigned_report["totals"]["Person"]["total"], 0)
			self.assertEqual(unassigned_report["samples"]["Person"], [])

			frappe.set_user(NO_SIRAJ_USER)
			self.assertEqual(geo_quality.quality_report(), {"totals": {}, "samples": {}})
		finally:
			frappe.set_user("Administrator")
			frappe.db.set_value(
				"Person", gc_person, {"latitude": 31.5130, "longitude": 34.4570}, update_modified=False
			)
			frappe.db.set_value(
				"Person", gd_person, {"latitude": 31.5230, "longitude": 34.4670}, update_modified=False
			)

	def test_06_profile_endpoints_redact_unreadable_foreign_link_titles_c02(self):
		"""C-02: entity_profile and relationship_profile must pass doc=name, scope inbound counts, and fix outbound."""
		gc = self.world["gc"]
		gd = self.world["gd"]
		frappe.set_user("Administrator")
		# Simulate:
		# 1) GD Relationship with Dynamic Link to GC Institution + Link primary_source to GC Source
		# 2) GC Military Unit pointing its commander Link at GD Person (inbound count must stay 1, not 2)
		frappe.db.set_value(
			"Relationship",
			gd["rel"],
			{"object": gc["inst"], "primary_source": gc["source"]},
			update_modified=False,
		)
		frappe.db.set_value("Military Unit", gc["unit"], "commander", gd["person"], update_modified=False)
		try:
			frappe.set_user(VIEWER_GD_USER)
			prof = entity_profile.get_entity_profile("Person", gd["person"])
			dumped_prof = json.dumps(prof, default=str)
			self.assertNotIn("GC Shadow Directorate", dumped_prof)
			self.assertNotIn(gc["inst"], dumped_prof)

			# Authored Relationship to unreadable GC Institution returns counterpart_name=None (F3):
			rel_conn = next(r for r in prof["connections"]["relationships"] if r["name"] == gd["rel"])
			self.assertIsNone(rel_conn["counterpart_name"])
			self.assertTrue(rel_conn["counterpart_restricted"])

			# Outbound Link block on Person (fixing f.get(f.fieldname) -> doc.get(f.fieldname)) populates birthplace;
			# also verify an unreadable outbound Link returns name=None (F3).
			outbound_fields = {o["field"] for o in prof["connections"]["outbound_links"]}
			self.assertIn("birthplace", outbound_fields)

			frappe.set_user("Administrator")
			frappe.db.set_value("Person", gd["person"], "marriage_place", gc["place"], update_modified=False)
			frappe.set_user(GD_ADMIN_USER)
			prof_unreadable_link = entity_profile.get_entity_profile("Person", gd["person"])
			mp_outbound = next(
				o for o in prof_unreadable_link["connections"]["outbound_links"] if o["field"] == "marriage_place"
			)
			self.assertIsNone(mp_outbound["name"])
			self.assertTrue(mp_outbound["restricted"])
			mp_scalar = next(
				f
				for s in prof_unreadable_link["sections"]
				for f in s["fields"]
				if f["fieldname"] == "marriage_place"
			)
			self.assertIsNone(mp_scalar["value"]["name"])
			self.assertTrue(mp_scalar["value"]["restricted"])
			frappe.set_user("Administrator")
			frappe.db.set_value("Person", gd["person"], "marriage_place", None, update_modified=False)
			frappe.set_user(VIEWER_GD_USER)

			# Inbound Military Unit count on GD Person must count ONLY the readable GD unit (1), not the GC unit!
			inbound_mu = next(
				i for i in prof["connections"]["inbound_links"] if i["doctype"] == "Military Unit"
			)
			self.assertEqual(inbound_mu["count"], 1)
			self.assertNotIn("GC 99th Special Brigade", json.dumps(inbound_mu, default=str))

			# Relationship profile: test Dynamic Link redaction for VIEWER_GD_USER (who has Link User Perm on GD)
			# by clearing the direct Link primary_source first, and test Link primary_source redaction for GD_ADMIN_USER
			# (whose custom has_permission hook blocks GC Source without Frappe Link User Permission blocking Relationship read).
			frappe.set_user("Administrator")
			frappe.db.set_value("Relationship", gd["rel"], "primary_source", None, update_modified=False)

			frappe.set_user(VIEWER_GD_USER)
			rel_prof_viewer = relationship_profile.get_relationship_profile(gd["rel"])
			self.assertNotIn("GC Shadow Directorate", json.dumps(rel_prof_viewer, default=str))

			frappe.set_user("Administrator")
			frappe.db.set_value("Relationship", gd["rel"], "primary_source", gc["source"], update_modified=False)

			frappe.set_user(GD_ADMIN_USER)
			rel_prof_admin = relationship_profile.get_relationship_profile(gd["rel"])
			dumped_rel_admin = json.dumps(rel_prof_admin, default=str)
			self.assertNotIn("GC Shadow Directorate", dumped_rel_admin)
			self.assertNotIn("GC Eyes-Only Dossier", dumped_rel_admin)
			ps_scalar = next(
				f
				for s in rel_prof_admin["sections"]
				for f in s["fields"]
				if f["fieldname"] == "primary_source"
			)
			self.assertIsNone(ps_scalar["value"]["name"])
			self.assertTrue(ps_scalar["value"]["restricted"])
		finally:
			frappe.set_user("Administrator")
			frappe.db.set_value(
				"Relationship",
				gd["rel"],
				{"object": gd["inst"], "primary_source": None},
				update_modified=False,
			)
			frappe.db.set_value("Military Unit", gc["unit"], "commander", gc["person"], update_modified=False)

	def test_07_cross_group_links_rejected_even_for_official_and_dynamic_links_c03a(self):
		"""C-03a (HD-4): Cross-group Link, Dynamic Link, child-row, and blank-group links raise PermissionError."""
		gc = self.world["gc"]
		gd = self.world["gd"]
		vocab = self.world["vocab"]

		# 1) GD user creating a Link (Person.birthplace -> GC Place) and Dynamic Link (Relationship -> GC Person),
		#    verifying the error message contains NO target name or title.
		frappe.set_user(GD_ADMIN_USER)
		with self.assertRaises(frappe.PermissionError) as link_ctx:
			frappe.get_doc(
				{
					"doctype": "Person",
					"name_ar": "اختراق موقع",
					"name_en": "GD Cross Link Probe",
					"birthplace": gc["place"],
				}
			).insert()
		link_err = str(link_ctx.exception)
		self.assertNotIn(gc["place"], link_err)
		self.assertNotIn("GC Secret Citadel", link_err)

		with self.assertRaises(frappe.PermissionError) as dyn_ctx:
			frappe.get_doc(
				{
					"doctype": "Relationship",
					"relationship_type": vocab["rel_type"],
					"subject_type": "Person",
					"subject": gd["person"],
					"object_type": "Person",
					"object": gc["person"],
				}
			).insert()
		dyn_err = str(dyn_ctx.exception)
		self.assertNotIn(gc["person"], dyn_err)
		self.assertNotIn("GC Classified Commander", dyn_err)

		# 2) Child-table row link: GD Person linking evidence.source -> GC Source or siblings.person -> GC Person.
		with self.assertRaises(frappe.PermissionError) as child_ctx:
			frappe.get_doc(
				{
					"doctype": "Person",
					"name_ar": "اختراق جدول فرعي",
					"name_en": "GD Child Row Probe",
					"evidence": [
						{
							"source": gc["source"],
							"support_type": "supports",
							"supported_claim": "Cross-group child evidence probe",
						}
					],
				}
			).insert()
		child_err = str(child_ctx.exception)
		self.assertNotIn(gc["source"], child_err)
		self.assertNotIn("GC Confidential Dispatch", child_err)

		# 3) SIRAJ Official creating cross-group links across Person, Military Unit,
		#    Operational Deployment, Command Appointment, and Siraj Event Person.
		frappe.set_user(OFFICIAL_USER)
		for payload in (
			{
				"doctype": "Person",
				"name_ar": "اختراق",
				"name_en": "Cross Group Person",
				"birthplace": gc["place"],
				"data_group": "GD",
			},
			{
				"doctype": "Military Unit",
				"unit_name": "Cross Group Unit",
				"echelon": "Battalion",
				"parent_unit": gc["unit"],
				"commander": gc["person"],
				"data_group": "GD",
			},
			{
				"doctype": "Operational Deployment",
				"deployment_name": "Cross Group Deployment",
				"unit": gc["unit"],
				"deployment_type": vocab["dep_type"],
				"status": "Planned",
				"start_date": "2026-02-01",
				"data_group": "GD",
			},
			{
				"doctype": "Command Appointment",
				"unit": gc["unit"],
				"commander": gd["person"],
				"role": "Deputy Commander",
				"assigned_date": "2026-02-01",
				"data_group": "GD",
			},
			{
				"doctype": "Siraj Event Person",
				"event": gd["siraj_event"],
				"person": gc["person"],
				"data_group": "GD",
			},
		):
			with self.assertRaises(frappe.PermissionError):
				frappe.get_doc(payload).insert()

		# 4) Administrator is ALSO blocked from creating cross-group links (HD-4: every role).
		frappe.set_user("Administrator")
		with self.assertRaises(frappe.PermissionError) as admin_ctx:
			frappe.get_doc(
				{
					"doctype": "Person",
					"name_ar": "اختراق مسؤول",
					"name_en": "Admin Cross Group Person",
					"birthplace": gc["place"],
					"data_group": "GD",
				}
			).insert()
		self.assertNotIn(gc["place"], str(admin_ctx.exception))
		self.assertNotIn("GC Secret Citadel", str(admin_ctx.exception))

		# 5) Blank-group target from a grouped source is rejected (fail-closed).
		orphan_place = frappe.get_doc(
			{
				"doctype": "Place",
				"name_ar": "موقع بلا مجموعة",
				"name_en": "Orphan Legacy Place",
				"place_type": vocab["place_type"],
				"data_group": "GD",
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Place", orphan_place.name, "data_group", None, update_modified=False)
		try:
			for actor in (GD_ADMIN_USER, OFFICIAL_USER, "Administrator"):
				frappe.set_user(actor)
				with self.assertRaises(frappe.PermissionError) as blank_ctx:
					frappe.get_doc(
						{
							"doctype": "Person",
							"name_ar": "ربط بموقع يتيم",
							"name_en": f"Link To Orphan ({actor})",
							"birthplace": orphan_place.name,
							"data_group": "GD",
						}
					).insert()
				self.assertNotIn(orphan_place.name, str(blank_ctx.exception))
				self.assertNotIn("Orphan Legacy Place", str(blank_ctx.exception))
		finally:
			frappe.set_user("Administrator")
			frappe.delete_doc("Place", orphan_place.name, force=True, ignore_permissions=True)

		# 6) Unscoped targets (User, Data Group, Country, Place Type) remain allowed alongside same-group targets.
		frappe.set_user(GD_ADMIN_USER)
		allowed_person = frappe.get_doc(
			{
				"doctype": "Person",
				"name_ar": "مسموح",
				"name_en": "GD Same Group And Unscoped Allowed",
				"birthplace": gd["place"],
				"data_group": "GD",
				"evidence": [
					{
						"source": gd["source"],
						"reviewer": GD_ADMIN_USER,
						"support_type": "supports",
						"supported_claim": "Same-group source + unscoped User reviewer",
					}
				],
			}
		).insert()
		try:
			self.assertEqual(allowed_person.data_group, "GD")
			self.assertEqual(allowed_person.evidence[0].reviewer, GD_ADMIN_USER)
		finally:
			frappe.set_user("Administrator")
			frappe.delete_doc("Person", allowed_person.name, force=True, ignore_permissions=True)

	def test_08_military_controllers_do_not_leak_or_crash_across_groups_c03b(self):
		"""C-03b: OperationalDeployment lifecycle, CommandAppointment overlap role/scoping, and Person.siblings guard."""
		gc = self.world["gc"]
		gd = self.world["gd"]
		vocab = self.world["vocab"]

		# 1) CommandAppointment.validate_overlap selects 'role' via permission-scoped get_list and formats it cleanly.
		frappe.set_user(GC_ADMIN_USER)
		with self.assertRaisesRegex(frappe.ValidationError, "Commanding Officer"):
			frappe.get_doc(
				{
					"doctype": "Command Appointment",
					"unit": gc["unit"],
					"commander": gc["person"],
					"role": "Commanding Officer",
					"assigned_date": "2026-02-01",
				}
			).insert()

		# 2) Person.validate_family permission-checks row.person before auto-filling sibling_name.
		frappe.set_user(VIEWER_GD_USER)
		probe = frappe.get_doc(
			{
				"doctype": "Person",
				"name_ar": "شقيق",
				"name_en": "GD Sibling Probe",
				"siblings": [{"person": gc["person"]}],
				"data_group": "GD",
			}
		)
		probe.validate_family()
		self.assertNotEqual(probe.siblings[0].sibling_name, "GC Classified Commander")
		self.assertFalse(probe.siblings[0].sibling_name)

		# 3) OperationalDeployment: failed save leaves NO partial write on Military Unit;
		#    on_update sets current_deployment, reassignment clears the old unit, and on_trash clears current_deployment.
		frappe.set_user(GD_ADMIN_USER)
		failed_dep = frappe.get_doc(
			{
				"doctype": "Operational Deployment",
				"deployment_name": "GD Failed Validation Probe",
				"unit": gd["unit"],
				"deployment_type": vocab["dep_type"],
				"status": "Completed",
				"is_current": 1,
				"start_date": "2026-03-01",
				# Missing mandatory end_date for Completed status -> fails in validate_end_date!
				"data_group": "GD",
			}
		)
		with self.assertRaises(frappe.ValidationError):
			failed_dep.insert()
		self.assertIsNone(frappe.db.get_value("Military Unit", gd["unit"], "current_deployment"))

		alt_unit = frappe.get_doc(
			{
				"doctype": "Military Unit",
				"unit_name": "GD 12th Coastal Battalion",
				"echelon": "Battalion",
				"data_group": "GD",
			}
		).insert()
		saved_dep = frappe.get_doc(
			{
				"doctype": "Operational Deployment",
				"deployment_name": "GD Active Reassignable Probe",
				"unit": gd["unit"],
				"deployment_type": vocab["dep_type"],
				"status": "Active",
				"is_current": 1,
				"start_date": "2026-03-01",
				"data_group": "GD",
			}
		).insert()
		try:
			self.assertEqual(
				frappe.db.get_value("Military Unit", gd["unit"], "current_deployment"),
				saved_dep.name,
			)
			# Reassigning unit clears current_deployment on the old unit and sets it on the new unit.
			saved_dep.unit = alt_unit.name
			saved_dep.save()
			self.assertIsNone(frappe.db.get_value("Military Unit", gd["unit"], "current_deployment"))
			self.assertEqual(
				frappe.db.get_value("Military Unit", alt_unit.name, "current_deployment"),
				saved_dep.name,
			)

			# Unsetting is_current on save clears current_deployment on the unit.
			saved_dep.is_current = 0
			saved_dep.save()
			self.assertIsNone(frappe.db.get_value("Military Unit", alt_unit.name, "current_deployment"))

			# Re-marking is_current=1 sets it again, and deleting the deployment clears it via on_trash.
			saved_dep.is_current = 1
			saved_dep.save()
			self.assertEqual(
				frappe.db.get_value("Military Unit", alt_unit.name, "current_deployment"),
				saved_dep.name,
			)
		finally:
			frappe.set_user("Administrator")
			if frappe.db.exists("Operational Deployment", saved_dep.name):
				frappe.delete_doc("Operational Deployment", saved_dep.name, force=True, ignore_permissions=True)
			self.assertIsNone(frappe.db.get_value("Military Unit", gd["unit"], "current_deployment"))
			self.assertIsNone(frappe.db.get_value("Military Unit", alt_unit.name, "current_deployment"))
			if frappe.db.exists("Military Unit", alt_unit.name):
				frappe.delete_doc("Military Unit", alt_unit.name, force=True, ignore_permissions=True)

	def test_09_non_admin_blocked_from_offline_bootstrap_mutations_c04(self):
		"""C-04 (HD-2): Non-admins denied; max_zoom clamped 0..14; long-queue enqueue with job_id; concurrent run refused."""
		from unittest.mock import patch

		for non_admin in (VIEWER_GD_USER, RESEARCHER_GD_USER, REVIEWER_GD_USER, NO_SIRAJ_USER):
			frappe.set_user(non_admin)
			with self.assertRaises(frappe.PermissionError):
				offline_bootstrap.request_stop()
			with self.assertRaises(frappe.PermissionError):
				offline_bootstrap.clear_stop()
			with self.assertRaises(frappe.PermissionError):
				offline_bootstrap.run_online_setup(dataset="ISO-TEST-BND", max_zoom=5)

		# Admin path: max_zoom=20 is clamped to 14, max_zoom=-5 is clamped to 0,
		# enqueued on queue='long' with job_id='siraj_offline_bootstrap',
		# and a second concurrent run while active is refused.
		frappe.set_user(GD_ADMIN_USER)
		enqueued_calls = []

		def fake_enqueue(method, **kwargs):
			enqueued_calls.append((method, kwargs))

		try:
			frappe.db.set_value(
				"Geo Settings",
				"Geo Settings",
				{"bootstrap_running": 0, "bootstrap_stop_requested": 0, "bootstrap_last_status": ""},
				update_modified=False,
			)
			with (
				patch.object(frappe, "enqueue", side_effect=fake_enqueue),
				patch("frappe.utils.background_jobs.is_job_enqueued", return_value=False),
			):
				res = offline_bootstrap.run_online_setup(dataset="ISO-TEST-BND", max_zoom=20)
				self.assertTrue(res["queued"])
				self.assertEqual(res["max_zoom"], 14)
				self.assertEqual(res["job_id"], offline_bootstrap.BOOTSTRAP_JOB_ID)
				self.assertEqual(len(enqueued_calls), 1)
				_, eq_kwargs = enqueued_calls[0]
				self.assertEqual(eq_kwargs["queue"], "long")
				self.assertEqual(eq_kwargs["job_id"], offline_bootstrap.BOOTSTRAP_JOB_ID)
				self.assertEqual(eq_kwargs["max_zoom"], 14)

				# Second concurrent run while bootstrap_running=1 (set when queued) is refused!
				with self.assertRaises(frappe.ValidationError):
					offline_bootstrap.run_online_setup(dataset="ISO-TEST-BND", max_zoom=8)

			# Also refused when bootstrap_running=0 in DB if RQ reports the job_id is still queued/started.
			frappe.db.set_value("Geo Settings", "Geo Settings", "bootstrap_running", 0, update_modified=False)
			with (
				patch.object(frappe, "enqueue", side_effect=fake_enqueue),
				patch("frappe.utils.background_jobs.is_job_enqueued", return_value=True),
			):
				with self.assertRaises(frappe.ValidationError):
					offline_bootstrap.run_online_setup(dataset="ISO-TEST-BND", max_zoom=8)

			# Negative zoom clamped to 0.
			with (
				patch.object(frappe, "enqueue", side_effect=fake_enqueue),
				patch("frappe.utils.background_jobs.is_job_enqueued", return_value=False),
			):
				res_neg = offline_bootstrap.run_online_setup(dataset="ISO-TEST-BND", max_zoom=-3)
				self.assertEqual(res_neg["max_zoom"], 0)
		finally:
			frappe.set_user("Administrator")
			frappe.db.set_value(
				"Geo Settings",
				"Geo Settings",
				{"bootstrap_running": 0, "bootstrap_stop_requested": 0, "bootstrap_last_status": ""},
				update_modified=False,
			)

	def test_10_boundary_import_dependencies_and_path_confinement_c05(self):
		"""C-05: dependencies() requires admin; start_import() confines paths (incl. symlinks); zip/upload caps enforced."""
		from unittest.mock import patch

		frappe.set_user(VIEWER_GD_USER)
		with self.assertRaises(frappe.PermissionError):
			boundary_import.dependencies()

		frappe.set_user(GD_ADMIN_USER)
		dep = boundary_import.dependencies()
		self.assertIn("ok", dep)

		with self.assertRaises(frappe.PermissionError):
			boundary_import.start_import("ISO-TEST-BND", "/etc/hosts")

		# Symlink inside private/siraj_boundary_uploads pointing outside -> PermissionError.
		upload_root = Path(frappe.get_site_path("private")) / boundary_import.UPLOAD_SUBDIR
		upload_root.mkdir(parents=True, exist_ok=True)
		symlink_probe = upload_root / "iso_c05_symlink_escape.geojson"
		try:
			if symlink_probe.exists() or symlink_probe.is_symlink():
				symlink_probe.unlink()
			symlink_probe.symlink_to("/etc/hosts")
			with self.assertRaises(frappe.PermissionError):
				boundary_import.start_import("ISO-TEST-BND", str(symlink_probe))
		finally:
			if symlink_probe.exists() or symlink_probe.is_symlink():
				symlink_probe.unlink()

		# Oversized upload rejected under patched MAX_UPLOAD_BYTES.
		with patch.object(boundary_import, "MAX_UPLOAD_BYTES", 32):
			with self.assertRaises(frappe.ValidationError):
				boundary_import.upload_file(
					"oversized.geojson", base64.b64encode(b"x" * 64).decode("ascii")
				)

	def test_11_boundary_import_upload_and_status_admin_gated(self):
		"""upload_file, start_import, and status already block non-admin viewers; admins can check status."""
		frappe.set_user(VIEWER_GD_USER)
		with self.assertRaises(frappe.PermissionError):
			boundary_import.upload_file("probe.geojson", base64.b64encode(b"{}").decode("ascii"))
		with self.assertRaises(frappe.PermissionError):
			boundary_import.start_import("ISO-TEST-BND", "/tmp/nonexistent.geojson")
		with self.assertRaises(frappe.PermissionError):
			boundary_import.status("ISO-TEST-BND")

		frappe.set_user(GD_ADMIN_USER)
		st = boundary_import.status("ISO-TEST-BND")
		self.assertIn("import_status", st)
		uploaded = boundary_import.upload_file("probe.geojson", base64.b64encode(b"{}").decode("ascii"))
		self._upload_paths.append(uploaded.get("path", ""))
		# File inside private/siraj_boundary_uploads that was not uploaded raises ValidationError (not found), not PermissionError.
		missing_inside = Path(frappe.get_site_path("private")) / boundary_import.UPLOAD_SUBDIR / "missing_probe.geojson"
		with self.assertRaises(frappe.ValidationError):
			boundary_import.start_import("ISO-TEST-BND", str(missing_inside))

	def test_12_geo_resolve_sweep_points_enforces_place_read_and_string_json_c07(self):
		"""C-07: sweep_points must enforce Place read permission, parse JSON string inputs, and cap at 500."""
		frappe.set_user(NO_SIRAJ_USER)
		with self.assertRaises(frappe.PermissionError):
			geo_resolve.sweep_points([["Probe", 31.5, 34.45]])

		frappe.set_user(VIEWER_GD_USER)
		rows = geo_resolve.sweep_points(json.dumps([["Probe", 31.5, 34.45]]))
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["point"], "Probe")

		capped = geo_resolve.sweep_points([[f"P{i}", 31.5, 34.45] for i in range(510)])
		self.assertEqual(len(capped), 500)

	def test_13_remaining_geo_tiles_cascade_and_diagnostics_gates(self):
		"""Exercise remaining geo_resolve, geo_package, cascade, hierarchy, local_maps, tile_cache, diagnostics."""
		# Plain Desk user with no Place read permission is denied on Place/admin-gated geo endpoints.
		frappe.set_user(NO_SIRAJ_USER)
		for fn, args in (
			(geo_package.current, ()),
			(geo_resolve.resolve_point, (31.5, 34.45)),
			(geo_resolve.resolve_area, (SAMPLE_POLYGON_GEOJSON,)),
			(geo_resolve.resolve_batch, ([[31.5, 34.45]],)),
			(geo_resolve.invalidate_cache, ()),
			(geo_cascade.cascade, ("country", "PS")),
			(geo_cascade.cascade_endpoint, ("country", "PS")),
			(geo_hierarchy.resolve_and_link_point, (31.5, 34.45, 0, 0)),
			(geo_hierarchy_ui.hierarchy_for_point, (31.5, 34.45, 0, 0)),
			(local_maps.available_packs, ()),
			(local_maps.tile, ("standard", "1", "0", "0")),
			(tile_cache.active_layer, ()),
			(tile_cache.cache_stats, ()),
			(tile_cache.cache_purge, ()),
			(tile_cache.tile, ("standard", "1", "0", "0")),
		):
			with self.assertRaises(frappe.PermissionError):
				fn(*args)

		# Viewer has Place read (allowed on read-only resolvers/tiles) but NO write on Geo Settings / Boundary Dataset.
		frappe.set_user(VIEWER_GD_USER)
		self.assertIn("etag", geo_package.current())
		self.assertIn("admin_chain", geo_resolve.resolve_point(31.5, 34.45, use_online=0))
		self.assertEqual(len(geo_resolve.resolve_batch(json.dumps([[31.5, 34.45]]), use_online=0)), 1)
		if geo_resolve.shapely is not None:
			self.assertIn("area_intersecting", geo_resolve.resolve_area(SAMPLE_POLYGON_GEOJSON))
		self.assertEqual(geo_cascade.cascade("country")["field"], "country")
		self.assertEqual(geo_cascade.cascade_endpoint("country")["field"], "country")
		self.assertIn("hierarchy", geo_hierarchy.resolve_and_link_point(31.5, 34.45, create_missing=0, use_online=0))
		self.assertIn("levels", geo_hierarchy_ui.hierarchy_for_point(31.5, 34.45, create_missing=0, use_online=0))
		self.assertEqual(local_maps.available_packs().status_code, 200)
		self.assertIn(local_maps.tile("standard", "1", "0", "0").status_code, (200, 404))
		self.assertIn("layer", tile_cache.active_layer())
		self.assertIn(tile_cache.tile("standard", "1", "0", "0").status_code, (200, 503))

		for admin_fn in (geo_resolve.invalidate_cache, tile_cache.cache_stats, tile_cache.cache_purge):
			with self.assertRaises(frappe.PermissionError):
				admin_fn()

		# Diagnostics endpoints return non-sensitive build metadata without leaking any record payloads.
		info = diagnostics.build_info()
		hashes = diagnostics.asset_hashes()
		self.assertIn("siraj_build", info)
		self.assertNotIn("GC Secret Citadel", json.dumps(info))
		self.assertIsInstance(hashes, dict)

	@unittest.expectedFailure
	def test_14_visualization_structure_data_raises_on_unreadable_permlevel_c08(self):
		"""C-08 (HD-5): structure_data must raise PermissionError when a grouping dimension is unreadable."""
		orig = visualization.STRUCTURES["people"]
		visualization.STRUCTURES["people"] = ("Person", ("researcher_notes",))
		try:
			frappe.set_user(VIEWER_GD_USER)
			with self.assertRaises(frappe.PermissionError):
				visualization.structure_data("people")
		finally:
			visualization.STRUCTURES["people"] = orig

	@unittest.expectedFailure
	def test_15_shared_record_accessible_to_standard_siraj_roles_within_group_c12(self):
		"""C-12 (HD-3): Standard SIRAJ roles (Viewer read-only, Researcher read/write) work on Shared Record."""
		gc = self.world["gc"]
		gd = self.world["gd"]

		# Users holding standard SIRAJ Viewer / SIRAJ Researcher roles (without Group Member's
		# blanket write/delete grant) must still have proper role-differentiated access in GD.
		frappe.set_user(ROLE_ONLY_VIEWER_GD_USER)
		visible = frappe.get_list("Shared Record", pluck="name")
		self.assertIn(gd["shared"], visible)
		self.assertNotIn(gc["shared"], visible)
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc(
				{"doctype": "Shared Record", "title": "Viewer Must Not Create", "details": "Denied"}
			).insert()

		frappe.set_user(ROLE_ONLY_RESEARCHER_GD_USER)
		created = frappe.get_doc(
			{"doctype": "Shared Record", "title": "GD Researcher Note", "details": "Scoped"}
		).insert()
		self.assertEqual(created.data_group, "GD")

	def test_16_relationship_profile_strips_permlevel_1_for_viewer_and_researcher(self):
		"""C-02: relationship_profile strips permlevel-1 researcher_notes for Viewer/Researcher, shows Reviewer."""
		gd_rel = self.world["gd"]["rel"]
		for caller in (VIEWER_GD_USER, RESEARCHER_GD_USER):
			frappe.set_user(caller)
			payload = json.dumps(relationship_profile.get_relationship_profile(gd_rel), default=str)
			self.assertNotIn("GD-REL-REVIEWER-ONLY-NOTE", payload, f"{caller} leaked Relationship researcher_notes")

		frappe.set_user(REVIEWER_GD_USER)
		reviewer_payload = json.dumps(relationship_profile.get_relationship_profile(gd_rel), default=str)
		self.assertIn("GD-REL-REVIEWER-ONLY-NOTE", reviewer_payload)

	def test_17_entity_profile_strips_permlevel_1_parent_and_child_fields_for_viewer_and_researcher(self):
		"""C-02: entity_profile strips permlevel-1 parent & child fields for Viewer/Researcher, shows Reviewer."""
		gd_person = self.world["gd"]["person"]
		for caller in (VIEWER_GD_USER, RESEARCHER_GD_USER):
			frappe.set_user(caller)
			payload = json.dumps(entity_profile.get_entity_profile("Person", gd_person), default=str)
			self.assertNotIn("GD-INTERNAL-SENSITIVE-NOTE", payload, f"{caller} leaked Person researcher_notes")
			self.assertNotIn("GD-SIBLING-PERMLEVEL1-ID", payload, f"{caller} leaked Person Sibling personal_id_number")

		frappe.set_user(REVIEWER_GD_USER)
		reviewer_payload = json.dumps(entity_profile.get_entity_profile("Person", gd_person), default=str)
		self.assertIn("GD-INTERNAL-SENSITIVE-NOTE", reviewer_payload)
		self.assertIn("GD-SIBLING-PERMLEVEL1-ID", reviewer_payload)

	def test_18_entity_profile_inbound_links_excludes_gc_and_formats_cap_as_n_plus(self):
		"""C-02: _inbound_links uses get_list SQL scoping (no per-row get_doc) and returns 'N+' when capped."""
		gc = self.world["gc"]
		gd = self.world["gd"]
		frappe.set_user("Administrator")
		frappe.db.set_value("Military Unit", gc["unit"], "commander", gd["person"], update_modified=False)
		extra_unit = frappe.get_doc(
			{
				"doctype": "Military Unit",
				"unit_name": "GD 11th Reserve Battalion",
				"echelon": "Battalion",
				"commander": gd["person"],
				"data_group": "GD",
			}
		).insert(ignore_permissions=True)
		orig_cap = getattr(entity_profile, "INBOUND_LINKS_CAP", 200)
		try:
			# 1) Uncapped: GD user sees exactly the 2 GD units (excluding GC unit -> count == 2, not 3).
			frappe.set_user(VIEWER_GD_USER)
			prof = entity_profile.get_entity_profile("Person", gd["person"])
			inbound_mu = next(
				i for i in prof["connections"]["inbound_links"] if i["doctype"] == "Military Unit"
			)
			self.assertEqual(inbound_mu["count"], 2)
			self.assertNotIn("GC 99th Special Brigade", json.dumps(inbound_mu, default=str))

			# 2) Capped at 1: 2 readable GD units exceed cap=1 -> count == '1+'.
			entity_profile.INBOUND_LINKS_CAP = 1
			capped_prof = entity_profile.get_entity_profile("Person", gd["person"])
			capped_mu = next(
				i for i in capped_prof["connections"]["inbound_links"] if i["doctype"] == "Military Unit"
			)
			self.assertEqual(capped_mu["count"], "1+")
		finally:
			entity_profile.INBOUND_LINKS_CAP = orig_cap
			frappe.set_user("Administrator")
			frappe.db.set_value("Military Unit", gc["unit"], "commander", gc["person"], update_modified=False)
			frappe.delete_doc("Military Unit", extra_unit.name, force=True, ignore_permissions=True)

	def test_19_entity_profile_authored_relationships_excludes_foreign_group_and_cancelled(self):
		"""C-02: _authored_relationships uses permission-scoped get_list and excludes foreign-group Relationship rows."""
		gc = self.world["gc"]
		gd = self.world["gd"]
		rel_type = self.world["vocab"]["rel_type"]
		frappe.set_user("Administrator")
		# Simulate a legacy/corrupt cross-group Relationship (data_group = GC) whose object is GD Person;
		# normal save is now blocked by validate_same_data_group_links (C-03a), so insert within GC then
		# point object to gd['person'] via db.set_value to test _authored_relationships read-time defense-in-depth.
		gc_to_gd_rel = frappe.get_doc(
			{
				"doctype": "Relationship",
				"subject_type": "Person",
				"subject": gc["person"],
				"relationship_type": rel_type,
				"object_type": "Person",
				"object": gc["person"],
				"primary_source": gc["source"],
				"data_group": "GC",
				"researcher_notes": "GC-SECRET-REL-NOTE",
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Relationship", gc_to_gd_rel.name, "object", gd["person"], update_modified=False)
		try:
			# Primary Data Group on Relationship comes from primary_source -> GC.
			# VIEWER_GD_USER (restricted to Data Group = GD) must NOT see gc_to_gd_rel in gd_person's authored relationships.
			frappe.set_user(VIEWER_GD_USER)
			prof = entity_profile.get_entity_profile("Person", gd["person"])
			rel_names = [r["name"] for r in prof["connections"]["relationships"]]
			self.assertIn(gd["rel"], rel_names)
			self.assertNotIn(gc_to_gd_rel.name, rel_names)
		finally:
			frappe.set_user("Administrator")
			frappe.delete_doc("Relationship", gc_to_gd_rel.name, force=True, ignore_permissions=True)

	def test_20_person_entity_profile_outbound_links_excludes_system_and_workflow_fields(self):
		"""F2: outbound_links uses relatable entity allowlist (Place/Person/Institution appear; vocabulary/system do not)."""
		gd = self.world["gd"]
		frappe.set_user("Administrator")
		cat_name = "ISO-PROBE-CATEGORY"
		if not frappe.db.exists("Person Category", cat_name):
			frappe.get_doc(
				{"doctype": "Person Category", "code": "iso_probe_category", "label_en": cat_name, "label_ar": cat_name}
			).insert(ignore_permissions=True)
		frappe.db.set_value("Person", gd["person"], "category", cat_name, update_modified=False)
		try:
			frappe.set_user(VIEWER_GD_USER)
			prof = entity_profile.get_entity_profile("Person", gd["person"])
			outbound = prof["connections"]["outbound_links"]
			outbound_fields = {item["field"] for item in outbound}
			self.assertIn("birthplace", outbound_fields)
			for excluded in (
				"category",
				"data_group",
				"workflow_state",
				"documentation_level",
				"authentication_level",
				"name_original_lang",
				"amended_from",
			):
				self.assertNotIn(excluded, outbound_fields)

			inst_prof = entity_profile.get_entity_profile("Institution", gd["inst"])
			inst_outbound = {item["field"] for item in inst_prof["connections"]["outbound_links"]}
			self.assertIn("place", inst_outbound)
			self.assertNotIn("institution_type", inst_outbound)
			self.assertNotIn("data_group", inst_outbound)
		finally:
			frappe.set_user("Administrator")
			frappe.db.set_value("Person", gd["person"], "category", None, update_modified=False)

	def test_21_geo_quality_report_non_located_doctype_returns_empty(self):
		"""C-01: quality_report('<non-located doctype>') returns empty totals and samples."""
		frappe.set_user(VIEWER_GD_USER)
		self.assertEqual(geo_quality.quality_report("Source"), {"totals": {}, "samples": {}})
		self.assertEqual(geo_quality.quality_report("Shared Record"), {"totals": {}, "samples": {}})

	def test_22_inbound_links_skips_unpermitted_target_doctype_with_zero_error_logs(self):
		"""F1: Viewer without read on a target DocType skips it silently and creates zero Error Log rows."""
		gd = self.world["gd"]
		frappe.set_user("Administrator")
		before_errors = frappe.db.count("Error Log")
		# Temporarily revoke SIRAJ Viewer read on Military Unit via Custom DocPerm / DocPerm or mock:
		viewer_perms = frappe.get_all(
			"DocPerm",
			filters={"parent": "Military Unit", "role": "SIRAJ Viewer", "permlevel": 0},
			fields=["name", "read"],
		)
		try:
			for p in viewer_perms:
				frappe.db.set_value("DocPerm", p["name"], "read", 0, update_modified=False)
			frappe.clear_cache(doctype="Military Unit")
			frappe.set_user(ROLE_ONLY_VIEWER_GD_USER)
			self.assertFalse(frappe.has_permission("Military Unit", "read"))
			prof = entity_profile.get_entity_profile("Person", gd["person"])
			inbound_dts = [item["doctype"] for item in prof["connections"]["inbound_links"]]
			self.assertNotIn("Military Unit", inbound_dts)
			frappe.set_user("Administrator")
			after_errors = frappe.db.count("Error Log")
			self.assertEqual(after_errors, before_errors)
		finally:
			frappe.set_user("Administrator")
			for p in viewer_perms:
				frappe.db.set_value("DocPerm", p["name"], "read", p["read"], update_modified=False)
			frappe.clear_cache(doctype="Military Unit")

	def test_23_same_data_group_link_bypass_behaviors_and_test_data_seeding_c03a(self):
		"""C-03a: Documented validation bypasses (ignore_validate, db_set, db.set_value) and test_data single-group seeding."""
		from unittest.mock import patch

		from siraj_research.setup import test_data

		gc = self.world["gc"]
		frappe.set_user("Administrator")

		# 1) flags.ignore_validate = True skips run_before_save_methods() validate hooks (documented bypass),
		#    but a subsequent normal .save() runs validate_same_data_group_links and rejects the row.
		bypassed = frappe.get_doc(
			{
				"doctype": "Person",
				"name_ar": "تجاوز التحقق",
				"name_en": "Bypassed Ignore Validate Probe",
				"birthplace": gc["place"],
				"data_group": "GD",
			}
		)
		bypassed.flags.ignore_validate = True
		bypassed.insert(ignore_permissions=True)
		try:
			bypassed.flags.ignore_validate = False
			bypassed.name_variants = "Attempt normal save"
			with self.assertRaises(frappe.PermissionError):
				bypassed.save(ignore_permissions=True)
		finally:
			frappe.delete_doc("Person", bypassed.name, force=True, ignore_permissions=True)

		# 2) db_set and db.set_value write directly without validate hooks (documented bypass),
		#    and a subsequent normal .save() catches the resulting cross-group link.
		clean_probe = frappe.get_doc(
			{
				"doctype": "Person",
				"name_ar": "نظيف",
				"name_en": "Clean Probe Before db_set",
				"data_group": "GD",
			}
		).insert(ignore_permissions=True)
		try:
			clean_probe.db_set("birthplace", gc["place"], update_modified=False)
			reloaded = frappe.get_doc("Person", clean_probe.name)
			with self.assertRaises(frappe.PermissionError):
				reloaded.save(ignore_permissions=True)
			frappe.db.set_value("Person", clean_probe.name, "birthplace", None, update_modified=False)
			frappe.db.set_value("Person", clean_probe.name, "marriage_place", gc["place"], update_modified=False)
			reloaded2 = frappe.get_doc("Person", clean_probe.name)
			with self.assertRaises(frappe.PermissionError):
				reloaded2.save(ignore_permissions=True)
		finally:
			frappe.delete_doc("Person", clean_probe.name, force=True, ignore_permissions=True)

		# 3) Verify setup/test_data.py links every scoped sample record within TEST_DATA_GROUP ('GD')
		#    under live validate_same_data_group_links enforcement, then roll back via savepoint.
		frappe.db.savepoint("c03a_test_data_seed")
		try:
			with patch.object(test_data, "_assert_event_safe", lambda: None):
				seeded = test_data.seed_test_data()
			self.assertGreater(seeded["created"]["Person"], 0)
			for dt, names in seeded["created_names"].items():
				if dt in ("Person", "Institution", "Place", "Source", "Military Unit", "Relationship"):
					for n in names:
						self.assertEqual(
							frappe.db.get_value(dt, n, "data_group"),
							test_data.TEST_DATA_GROUP,
						)
		finally:
			frappe.db.rollback(save_point="c03a_test_data_seed")

		# 4) Live Data Import (validation on) carrying a cross-group link is rejected by Importer.process_doc.
		from frappe.core.doctype.data_import.importer import Importer

		csv_content = (
			"name_ar,name_en,birthplace,data_group\n"
			f"استيراد عابر,Cross Group CSV Import,{gc['place']},GD\n"
		)
		csv_file = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "c03a_cross_group_import.csv",
				"content": csv_content,
				"is_private": 1,
			}
		).insert(ignore_permissions=True)
		data_import = frappe.get_doc(
			{
				"doctype": "Data Import",
				"reference_doctype": "Person",
				"import_type": "Insert New Records",
				"import_file": csv_file.file_url,
			}
		).insert(ignore_permissions=True)
		try:
			importer = Importer("Person", data_import=data_import)
			payloads = importer.import_file.get_payloads_for_import()
			self.assertEqual(len(payloads), 1)
			with self.assertRaises(frappe.PermissionError) as di_ctx:
				importer.process_doc(payloads[0].doc)
			self.assertNotIn(gc["place"], str(di_ctx.exception))
			self.assertNotIn("GC Secret Citadel", str(di_ctx.exception))
			self.assertFalse(
				frappe.db.exists("Person", {"name_en": "Cross Group CSV Import"}),
				"Data Import must not persist a cross-group linked record",
			)
		finally:
			frappe.delete_doc("Data Import", data_import.name, force=True, ignore_permissions=True)
			frappe.delete_doc("File", csv_file.name, force=True, ignore_permissions=True)
