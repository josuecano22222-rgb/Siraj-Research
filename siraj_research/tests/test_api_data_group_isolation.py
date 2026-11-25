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

	@unittest.expectedFailure
	def test_06_profile_endpoints_redact_unreadable_foreign_link_titles_c02(self):
		"""C-02: entity_profile and relationship_profile must pass doc=name before reading Link titles."""
		gc = self.world["gc"]
		gd = self.world["gd"]
		frappe.set_user("Administrator")
		# Simulate a GD Relationship (Dynamic Link) pointing at a GC Institution, and inspect both
		# relationship_profile AND entity_profile (via _authored_relationships on GD Person).
		# Dynamic Links bypass native Link User Permissions for VIEWER_GD_USER, exposing the exact
		# doc=name missing-argument leak in entity_profile._authored_relationships and relationship_profile!
		frappe.db.set_value("Relationship", gd["rel"], "object", gc["inst"], update_modified=False)
		try:
			frappe.set_user(VIEWER_GD_USER)
			prof = entity_profile.get_entity_profile("Person", gd["person"])
			rel_prof = relationship_profile.get_relationship_profile(gd["rel"])
			self.assertNotIn("GC Shadow Directorate", json.dumps(prof))
			self.assertNotIn("GC Shadow Directorate", json.dumps(rel_prof))
		finally:
			frappe.set_user("Administrator")
			frappe.db.set_value("Relationship", gd["rel"], "object", gd["inst"], update_modified=False)

	@unittest.expectedFailure
	def test_07_cross_group_links_rejected_even_for_official_and_dynamic_links_c03a(self):
		"""C-03a (HD-4): Cross-group Link and Dynamic Link saves must raise PermissionError for every role."""
		gc = self.world["gc"]
		gd = self.world["gd"]
		vocab = self.world["vocab"]

		# 1) GD user creating a Relationship (Dynamic Link) pointing to a GC Person.
		frappe.set_user(GD_ADMIN_USER)
		with self.assertRaises(frappe.PermissionError):
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

		# 2) SIRAJ Official creating cross-group links across Person, Military Unit,
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

	@unittest.expectedFailure
	def test_08_military_controllers_do_not_leak_or_crash_across_groups_c03b(self):
		"""C-03b: CommandAppointment.validate_overlap must select role cleanly; Person.siblings must not leak GC."""
		gc = self.world["gc"]
		frappe.set_user(GC_ADMIN_USER)
		# Currently CommandAppointment.validate_overlap omits 'role' from get_all fields, so
		# other.role evaluates to None ('... is already None of ...') instead of 'Commanding Officer'.
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

		# Also: Person.validate_family currently auto-fills sibling_name via frappe.db.get_value
		# without checking read permission / group match on row.person.
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

	@unittest.expectedFailure
	def test_09_non_admin_blocked_from_offline_bootstrap_mutations_c04(self):
		"""C-04 (HD-2): Non-admin viewer/researcher must be denied run_online_setup, request_stop, clear_stop."""
		frappe.set_user(VIEWER_GD_USER)
		with self.assertRaises(frappe.PermissionError):
			offline_bootstrap.request_stop()
		with self.assertRaises(frappe.PermissionError):
			offline_bootstrap.clear_stop()
		with self.assertRaises(frappe.PermissionError):
			offline_bootstrap.run_online_setup(dataset="ISO-TEST-BND", max_zoom=5)

	@unittest.expectedFailure
	def test_10_boundary_import_dependencies_and_path_confinement_c05(self):
		"""C-05: dependencies() requires admin; start_import() rejects paths outside boundary_uploads."""
		frappe.set_user(VIEWER_GD_USER)
		with self.assertRaises(frappe.PermissionError):
			boundary_import.dependencies()

		frappe.set_user(GD_ADMIN_USER)
		with self.assertRaises(frappe.PermissionError):
			boundary_import.start_import("ISO-TEST-BND", "/etc/hosts")

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

	@unittest.expectedFailure
	def test_12_geo_resolve_sweep_points_enforces_place_read_and_string_json_c07(self):
		"""C-07: sweep_points must enforce Place read permission and parse JSON string inputs."""
		frappe.set_user(NO_SIRAJ_USER)
		with self.assertRaises(frappe.PermissionError):
			geo_resolve.sweep_points([["Probe", 31.5, 34.45]])

		frappe.set_user(VIEWER_GD_USER)
		rows = geo_resolve.sweep_points(json.dumps([["Probe", 31.5, 34.45]]))
		self.assertEqual(len(rows), 1)

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
