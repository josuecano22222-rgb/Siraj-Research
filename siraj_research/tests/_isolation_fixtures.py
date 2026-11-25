# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
"""Shared fixture builder for adversarial API & Data Group isolation bench tests.

Provisions isolated users (`GD`, `GC`, unassigned, `SIRAJ Viewer`, `SIRAJ Researcher`,
and `SIRAJ Official`) plus realistic `GC` and `GD` records across core and military
DocTypes, including predictable naming-series IDs (`PER-0001`, `EVT-0001`, `PLC-0001`).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import frappe

from siraj_research.api import geo_resolve
from siraj_research.setup.install import ROLES, setup

UNASSIGNED_USER = "unassigned-siraj@example.com"
VIEWER_GD_USER = "viewer-gd@example.com"
RESEARCHER_GD_USER = "researcher-gd@example.com"
REVIEWER_GD_USER = "reviewer-gd@example.com"
ROLE_ONLY_VIEWER_GD_USER = "role-only-viewer-gd@example.com"
ROLE_ONLY_RESEARCHER_GD_USER = "role-only-researcher-gd@example.com"
OFFICIAL_USER = "official-siraj@example.com"
NO_SIRAJ_USER = "desk-only-no-siraj@example.com"
GD_ADMIN_USER = "gd1@example.com"
GC_ADMIN_USER = "gc1@example.com"

# Canonical registry of every @frappe.whitelist endpoint in siraj_research/.
# Verified against AST discovery by tests/test_whitelist_coverage.py.
ALL_WHITELISTED_ENDPOINTS: tuple[tuple[str, str], ...] = (
	("siraj_research.api.audit", "document_history"),
	("siraj_research.api.boundary_import", "dependencies"),
	("siraj_research.api.boundary_import", "upload_file"),
	("siraj_research.api.boundary_import", "start_import"),
	("siraj_research.api.boundary_import", "status"),
	("siraj_research.api.diagnostics", "build_info"),
	("siraj_research.api.diagnostics", "asset_hashes"),
	("siraj_research.api.entity_profile", "get_entity_profile"),
	("siraj_research.api.geo_package", "current"),
	("siraj_research.api.geo_resolve", "sweep_points"),
	("siraj_research.api.geo_resolve", "resolve_point"),
	("siraj_research.api.geo_resolve", "resolve_area"),
	("siraj_research.api.geo_resolve", "resolve_batch"),
	("siraj_research.api.geo_resolve", "invalidate_cache"),
	("siraj_research.api.map_relations", "get_entity_network"),
	("siraj_research.api.map_search", "search"),
	("siraj_research.api.map_search", "search_bbox"),
	("siraj_research.api.map_search", "region_children"),
	("siraj_research.api.relationship_profile", "get_relationship_profile"),
	("siraj_research.geo_cascade", "cascade"),
	("siraj_research.geo_cascade", "cascade_endpoint"),
	("siraj_research.geo_hierarchy", "resolve_and_link_point"),
	("siraj_research.geo_hierarchy_ui", "hierarchy_for_point"),
	("siraj_research.geo_quality", "quality_report"),
	("siraj_research.local_maps", "available_packs"),
	("siraj_research.local_maps", "tile"),
	("siraj_research.offline_bootstrap", "request_stop"),
	("siraj_research.offline_bootstrap", "clear_stop"),
	("siraj_research.offline_bootstrap", "run_online_setup"),
	("siraj_research.siraj_research.doctype.military_unit.military_unit", "MilitaryUnit.get_descendants"),
	("siraj_research.tile_cache", "active_layer"),
	("siraj_research.tile_cache", "cache_stats"),
	("siraj_research.tile_cache", "cache_purge"),
	("siraj_research.tile_cache", "tile"),
	("siraj_research.treeview", "get_children"),
	("siraj_research.visualization", "geographic_data"),
	("siraj_research.visualization", "relationship_data"),
	("siraj_research.visualization", "record_detail"),
	("siraj_research.visualization", "structure_data"),
)

SAMPLE_POLYGON_GEOJSON = json.dumps(
	{
		"type": "Polygon",
		"coordinates": [
			[
				[34.44, 31.50],
				[34.48, 31.50],
				[34.48, 31.54],
				[34.44, 31.54],
				[34.44, 31.50],
			]
		],
	}
)


def _ensure_role(role_name: str) -> None:
	if not frappe.db.exists("Role", role_name):
		frappe.get_doc({"doctype": "Role", "role_name": role_name, "desk_access": 1}).insert(
			ignore_permissions=True
		)


def _ensure_user(email: str, first_name: str, roles: tuple[str, ...], data_group: str | None = None) -> str:
	for role in roles:
		_ensure_role(role)
	if frappe.db.exists("User", email):
		frappe.delete_doc("User", email, force=True, ignore_permissions=True)
	for up_name in frappe.get_all("User Permission", filters={"user": email}, pluck="name"):
		frappe.delete_doc("User Permission", up_name, force=True, ignore_permissions=True)

	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": first_name,
			"enabled": 1,
			"user_type": "System User",
			"send_welcome_email": 0,
			"roles": [{"role": role} for role in roles],
		}
	).insert(ignore_permissions=True)

	if data_group:
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": user.name,
				"allow": "Data Group",
				"for_value": data_group,
				"apply_to_all_doctypes": 1,
			}
		).insert(ignore_permissions=True)
	return user.name


def _ensure_vocab(doctype: str, code: str, extra: dict | None = None) -> str:
	label_en = f"Test {code}"
	if frappe.db.exists(doctype, label_en):
		return label_en
	if frappe.db.exists(doctype, code):
		return code
	payload = {
		"doctype": doctype,
		"code": code,
		"label_en": label_en,
		"label_ar": f"اختبار {code}",
	}
	if extra:
		payload.update(extra)
	doc = frappe.get_doc(payload).insert(ignore_permissions=True)
	return doc.name


def _ensure_unit_classification(classification_name: str = "ISO Infantry") -> str:
	if frappe.db.exists("Unit Classification", classification_name):
		return classification_name
	doc = frappe.get_doc(
		{
			"doctype": "Unit Classification",
			"classification_name": classification_name,
			"category": "Combat",
		}
	).insert(ignore_permissions=True)
	return doc.name


def _insert_predictable_or_regular(payload: dict, predictable_name: str | None = None):
	# Normal naming_series insert on a fresh scratch site naturally assigns
	# PLC-0001 / PER-0001 / EVT-0001 while advancing tabSeries cleanly (whereas
	# set_name= skips tabSeries and causes the next insert to collide).
	del predictable_name
	return frappe.get_doc(payload).insert(ignore_permissions=True)


def build_isolation_world() -> dict:
	"""Create users + GC/GD records inside the active test transaction."""
	frappe.set_user("Administrator")
	for role in ROLES:
		_ensure_role(role)
	if not frappe.db.exists("Workflow State", "Draft"):
		frappe.get_doc({"doctype": "Workflow State", "workflow_state_name": "Draft"}).insert(
			ignore_permissions=True
		)
	setup("Isolation-Suite-Password-2026!", commit=False)

	_ensure_user(UNASSIGNED_USER, "Unassigned Researcher", ("Group Member", "SIRAJ Researcher"), data_group=None)
	_ensure_user(VIEWER_GD_USER, "Viewer GD", ("Group Member", "SIRAJ Viewer"), data_group="GD")
	_ensure_user(RESEARCHER_GD_USER, "Researcher GD", ("Group Member", "SIRAJ Researcher"), data_group="GD")
	_ensure_user(REVIEWER_GD_USER, "Reviewer GD", ("Group Member", "SIRAJ Reviewer"), data_group="GD")
	_ensure_user(ROLE_ONLY_VIEWER_GD_USER, "Role Only Viewer GD", ("SIRAJ Viewer",), data_group="GD")
	_ensure_user(ROLE_ONLY_RESEARCHER_GD_USER, "Role Only Researcher GD", ("SIRAJ Researcher",), data_group="GD")
	_ensure_user(
		OFFICIAL_USER,
		"Official Supervisor",
		("Group Member", "SIRAJ Administrator", "SIRAJ Official"),
		data_group=None,
	)
	_ensure_user(NO_SIRAJ_USER, "Plain Desk User", (), data_group=None)

	place_type = _ensure_vocab("Place Type", "ISO_CITY")
	inst_type = _ensure_vocab("Institution Type", "ISO_ORG")
	event_type = _ensure_vocab("Event Type", "ISO_INCIDENT")
	source_type = _ensure_vocab("Source Type", "ISO_REPORT")
	rel_type = _ensure_vocab("Relationship Type", "ISO_AFFILIATED", {"is_symmetric": 1})
	unit_class = _ensure_unit_classification()
	dep_type = "Operational"

	if not frappe.db.exists("Boundary Dataset", "ISO-TEST-BND"):
		frappe.get_doc(
			{
				"doctype": "Boundary Dataset",
				"code": "ISO-TEST-BND",
				"label_en": "Isolation Boundary Pack",
				"source": "custom",
				"license_id": "CC-BY-4.0",
				"level": 1,
			}
		).insert(ignore_permissions=True)

	geo_settings = frappe.get_single("Geo Settings")
	geo_settings.allow_tile_fetch = 0
	geo_settings.online_geocoder_enabled = 0
	geo_settings.save(ignore_permissions=True)

	gc_place = _insert_predictable_or_regular(
		{
			"doctype": "Place",
			"name_ar": "موقع سري جيم",
			"name_en": "GC Secret Citadel",
			"place_type": place_type,
			"is_group": 1,
			"latitude": 31.5123,
			"longitude": 34.4567,
			"geocoding_method": "manual",
			"data_group": "GC",
		},
		predictable_name="PLC-0001",
	)
	gd_place = frappe.get_doc(
		{
			"doctype": "Place",
			"name_ar": "موقع دال العام",
			"name_en": "GD Harbor Base",
			"place_type": place_type,
			"is_group": 1,
			"latitude": 31.5223,
			"longitude": 34.4667,
			"geocoding_method": "manual",
			"data_group": "GD",
		}
	).insert(ignore_permissions=True)

	gc_person = _insert_predictable_or_regular(
		{
			"doctype": "Person",
			"name_ar": "شخصية سرية جيم",
			"name_en": "GC Classified Commander",
			"category": "Military",
			"birthplace": gc_place.name,
			"researcher_notes": "GC-ONLY-SENSITIVE-NOTE",
			"latitude": 31.5130,
			"longitude": 34.4570,
			"geocoding_method": "manual",
			"data_group": "GC",
		},
		predictable_name="PER-0001",
	)
	gc_person_edit = frappe.get_doc("Person", gc_person.name)
	gc_person_edit.name_variants = "GC-AUDIT-SECRET-VARIANT"
	gc_person_edit.save(ignore_permissions=True, ignore_version=False)

	gd_person = frappe.get_doc(
		{
			"doctype": "Person",
			"name_ar": "شخصية دال",
			"name_en": "GD Field Commander",
			"category": "Military",
			"birthplace": gd_place.name,
			"researcher_notes": "GD-INTERNAL-SENSITIVE-NOTE",
			"siblings": [
				{
					"sibling_name": "GD Sibling Alpha",
					"personal_id_number": "GD-SIBLING-PERMLEVEL1-ID",
				}
			],
			"latitude": 31.5230,
			"longitude": 34.4670,
			"geocoding_method": "manual",
			"data_group": "GD",
		}
	).insert(ignore_permissions=True)

	gc_inst = frappe.get_doc(
		{
			"doctype": "Institution",
			"name_ar": "مؤسسة جيم السرية",
			"name_en": "GC Shadow Directorate",
			"institution_type": inst_type,
			"place": gc_place.name,
			"data_group": "GC",
		}
	).insert(ignore_permissions=True)
	gd_inst = frappe.get_doc(
		{
			"doctype": "Institution",
			"name_ar": "مؤسسة دال",
			"name_en": "GD Civic Bureau",
			"institution_type": inst_type,
			"place": gd_place.name,
			"data_group": "GD",
		}
	).insert(ignore_permissions=True)

	gc_source = frappe.get_doc(
		{
			"doctype": "Source",
			"title": "GC Eyes-Only Dossier",
			"source_type": source_type,
			"data_group": "GC",
		}
	).insert(ignore_permissions=True)

	gc_unit = frappe.get_doc(
		{
			"doctype": "Military Unit",
			"unit_name": "GC 99th Special Brigade",
			"echelon": "Brigade",
			"is_group": 1,
			"classification": unit_class,
			"commander": gc_person.name,
			"linked_place": gc_place.name,
			"latitude": 31.5140,
			"longitude": 34.4580,
			"geocoding_method": "manual",
			"data_group": "GC",
		}
	).insert(ignore_permissions=True)
	gc_child_unit = frappe.get_doc(
		{
			"doctype": "Military Unit",
			"unit_name": "GC 991st Recon Battalion",
			"echelon": "Battalion",
			"parent_unit": gc_unit.name,
			"classification": unit_class,
			"data_group": "GC",
		}
	).insert(ignore_permissions=True)
	gd_unit = frappe.get_doc(
		{
			"doctype": "Military Unit",
			"unit_name": "GD 10th Coastal Brigade",
			"echelon": "Brigade",
			"is_group": 1,
			"classification": unit_class,
			"commander": gd_person.name,
			"linked_place": gd_place.name,
			"latitude": 31.5240,
			"longitude": 34.4680,
			"geocoding_method": "manual",
			"data_group": "GD",
		}
	).insert(ignore_permissions=True)

	gc_deployment = frappe.get_doc(
		{
			"doctype": "Operational Deployment",
			"deployment_name": "GC Forward Screen",
			"unit": gc_unit.name,
			"deployment_type": dep_type,
			"status": "Active",
			"is_current": 1,
			"start_date": "2026-01-10",
			"data_group": "GC",
		}
	).insert(ignore_permissions=True)
	gc_appointment = frappe.get_doc(
		{
			"doctype": "Command Appointment",
			"unit": gc_unit.name,
			"commander": gc_person.name,
			"role": "Commanding Officer",
			"assigned_date": "2026-01-01",
			"is_current": 1,
			"data_group": "GC",
		}
	).insert(ignore_permissions=True)

	gc_siraj_event_title = "GC Classified Briefing"
	if frappe.db.exists("Siraj Event", gc_siraj_event_title):
		frappe.delete_doc("Siraj Event", gc_siraj_event_title, force=True, ignore_permissions=True)
	gc_siraj_event = frappe.get_doc(
		{
			"doctype": "Siraj Event",
			"title": gc_siraj_event_title,
			"event_type": event_type,
			"workflow_state": "Draft",
			"data_group": "GC",
		}
	).insert(ignore_permissions=True)
	gd_siraj_event_title = "GD Public Convoy"
	if frappe.db.exists("Siraj Event", gd_siraj_event_title):
		frappe.delete_doc("Siraj Event", gd_siraj_event_title, force=True, ignore_permissions=True)
	gd_siraj_event = frappe.get_doc(
		{
			"doctype": "Siraj Event",
			"title": gd_siraj_event_title,
			"event_type": event_type,
			"workflow_state": "Draft",
			"data_group": "GD",
		}
	).insert(ignore_permissions=True)

	gc_research_event = None
	if frappe.db.exists("DocType", "Research Event"):
		gc_research_event = _insert_predictable_or_regular(
			{
				"doctype": "Research Event",
				"title_ar": "حدث سري جيم",
				"title_en": "GC Classified Operation",
				"event_type": event_type,
				"place": gc_place.name,
				"latitude": 31.5150,
				"longitude": 34.4590,
				"geocoding_method": "manual",
				"data_group": "GC",
			},
			predictable_name="EVT-0001",
		)

	gc_rel = frappe.get_doc(
		{
			"doctype": "Relationship",
			"relationship_type": rel_type,
			"subject_type": "Person",
			"subject": gc_person.name,
			"object_type": "Institution",
			"object": gc_inst.name,
			"primary_source": gc_source.name,
			"description": "GC covert command link",
			"data_group": "GC",
		}
	).insert(ignore_permissions=True)
	gd_rel = frappe.get_doc(
		{
			"doctype": "Relationship",
			"relationship_type": rel_type,
			"subject_type": "Person",
			"subject": gd_person.name,
			"object_type": "Institution",
			"object": gd_inst.name,
			"description": "GD public liaison link",
			"researcher_notes": "GD-REL-REVIEWER-ONLY-NOTE",
			"data_group": "GD",
		}
	).insert(ignore_permissions=True)

	gc_shared = frappe.get_doc(
		{"doctype": "Shared Record", "title": "GC Secret Memo", "details": "GC eyes only", "data_group": "GC"}
	).insert(ignore_permissions=True)
	gd_shared = frappe.get_doc(
		{"doctype": "Shared Record", "title": "GD Shared Brief", "details": "GD team brief", "data_group": "GD"}
	).insert(ignore_permissions=True)

	frappe.clear_cache()
	return {
		"vocab": {
			"place_type": place_type,
			"inst_type": inst_type,
			"event_type": event_type,
			"source_type": source_type,
			"rel_type": rel_type,
			"unit_class": unit_class,
			"dep_type": dep_type,
		},
		"gc": {
			"place": gc_place.name,
			"person": gc_person.name,
			"inst": gc_inst.name,
			"source": gc_source.name,
			"unit": gc_unit.name,
			"child_unit": gc_child_unit.name,
			"deployment": gc_deployment.name,
			"appointment": gc_appointment.name,
			"siraj_event": gc_siraj_event.name,
			"research_event": gc_research_event.name if gc_research_event else None,
			"rel": gc_rel.name,
			"shared": gc_shared.name,
		},
		"gd": {
			"place": gd_place.name,
			"person": gd_person.name,
			"inst": gd_inst.name,
			"unit": gd_unit.name,
			"siraj_event": gd_siraj_event.name,
			"rel": gd_rel.name,
			"shared": gd_shared.name,
		},
	}


def cleanup_isolation_caches(upload_paths: list[str] | None = None) -> None:
	"""Reset in-memory caches and remove any temporary files written by tests."""
	frappe.set_user("Administrator")
	geo_resolve._CACHE.clear()
	geo_resolve._COORD_CACHE.clear()
	for raw_path in upload_paths or []:
		try:
			if raw_path and os.path.isfile(raw_path):
				Path(raw_path).unlink(missing_ok=True)
		except OSError:
			pass
	frappe.clear_cache()
