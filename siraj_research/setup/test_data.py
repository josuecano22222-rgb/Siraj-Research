"""Explicitly requested synthetic records; never inserted during installation.

This is a bench-execute helper, not a web endpoint. If run on a production
site, samples share its database and are not isolated. See docs/test-data.md.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy

import frappe

from siraj_research.hooks import SCOPED_DOCTYPES

TEST_DATA_GROUP = "GD"

LOOKUPS = (
	"Authentication Level",
	"Documentation Level",
	"Event Type",
	"Expertise Area",
	"Governance System",
	"Institution Subcategory",
	"Institution Type",
	"Leadership Level",
	"Leadership Quality",
	"Military Branch",
	"Military Service Status",
	"Person Category",
	"Person Classification",
	"Person Status",
	"Place Type",
	"Relationship Type",
	"Source Reliability",
	"Source Type",
	"Specialization",
)
ARABIC_LOOKUPS = {
	"Authentication Level": "مستوى التحقق",
	"Documentation Level": "مستوى التوثيق",
	"Event Type": "نوع الحدث",
	"Expertise Area": "مجال الخبرة",
	"Governance System": "نظام الحوكمة",
	"Institution Subcategory": "الفئة الفرعية للمؤسسة",
	"Institution Type": "نوع المؤسسة",
	"Leadership Level": "مستوى القيادة",
	"Leadership Quality": "صفة قيادية",
	"Military Branch": "الفرع العسكري",
	"Military Service Status": "حالة الخدمة العسكرية",
	"Person Category": "فئة الشخص",
	"Person Classification": "تصنيف الشخص",
	"Person Status": "حالة الشخص",
	"Place Type": "نوع المكان",
	"Relationship Type": "نوع العلاقة",
	"Source Reliability": "موثوقية المصدر",
	"Source Type": "نوع المصدر",
	"Specialization": "التخصص",
}
FOLD_CLASSIFICATIONS = 16
FOLD_RECORDS = 52

# All sample operational records are marked; they are not access-isolated.
OPERATIONAL_TYPES = (
	"Armament",
	"Command Appointment",
	"Siraj Event",
	"Institution",
	"Military Unit",
	"Mission",
	"Operational Deployment",
	"Person",
	"Place",
	"Relationship",
	"Source",
	"Training Exercise",
	"Unit Classification",
)
CHILD_TYPES = (
	"Evidence",
	"Expertise Link",
	"External Identifier",
	"Leadership Quality Assessment",
	"Person Position",
	"Social Account",
	"Specialization Link",
	"Unit Armament Holding",
)


def _assert_event_safe():
	# SIRAJ's Event currently has the same global DocType name as Frappe's
	# calendar Event. Their schemas and lifecycle hooks are incompatible.
	# Refuse before making any writes; do not work around this by disabling
	# calendar hooks or overriding Frappe's metadata on a live site.
	raise RuntimeError(
		"Sample insertion is paused: SIRAJ Event conflicts with Frappe's built-in Event. Inspect the site and resolve the DocType collision before retrying."
	)


def _guard():
	if not frappe.local.site or not frappe.db.exists("DocType", "SIRAJ Settings"):
		raise RuntimeError("Install siraj_research on the selected site first.")
	_assert_event_safe()
	for doctype, name in (("Country", "Iraq"), ("Person Category", "Military"), ("Workflow State", "Draft")):
		if not frappe.db.exists(doctype, name):
			raise RuntimeError("Missing fixture prerequisite: " + doctype + " / " + name)

	# Fixed identifiers provide a conservative one-run guard, not ownership
	# proof. Never overwrite an existing matching name OR unique code.
	fixed = [(doctype, "TEST " + doctype, "TEST_" + doctype.upper().replace(" ", "_")) for doctype in LOOKUPS]
	fixed += [("Relationship Type", "TEST Symmetric Relationship", "TEST_RELATIONSHIP_SYMMETRIC")]
	fixed += [
		("Person Classification", f"TEST Fold Class {i:02}", f"TEST_FOLD_CLASS_{i:02}")
		for i in range(1, FOLD_CLASSIFICATIONS + 1)
	]
	for doctype, name, code in fixed:
		if frappe.db.exists(doctype, name) or frappe.db.exists(doctype, {"code": code}):
			raise RuntimeError(
				"Sample identifier already exists in " + doctype + "; no records were inserted."
			)
	for doctype, code in (
		("External ID Scheme", "TEST_SCHEME"),
		("Social Platform", "TEST_PLATFORM"),
		("Governorate", "TEST_GOV"),
		("District", "TEST_DIST"),
		("Municipality", "TEST_MUNI"),
		("Village", "TEST_VIL"),
		("Community", "TEST_COMM"),
	):
		if frappe.db.exists(doctype, code) or frappe.db.exists(doctype, {"code": code}):
			raise RuntimeError(
				"Sample identifier already exists in " + doctype + "; no records were inserted."
			)
	if frappe.db.exists("Unit Classification", "TEST Unit Classification"):
		raise RuntimeError(
			"Sample identifier already exists in Unit Classification; no records were inserted."
		)


def seed_test_data():
	"""Insert one connected, fictional dataset; return counts, never commit here.

	A second run is deliberately rejected. On failure, roll back the entire
	transaction. Running on production deliberately mixes samples into its data.
	"""
	_guard()
	created = Counter()
	created_names = {}

	def add(doctype, **values):
		if doctype in SCOPED_DOCTYPES and not values.get("data_group"):
			values["data_group"] = TEST_DATA_GROUP
		if doctype in OPERATIONAL_TYPES:
			values["researcher_notes"] = "TEST SAMPLE — fictional data, not a real record."
		doc = frappe.get_doc({"doctype": doctype, **deepcopy(values)})
		doc.insert(ignore_permissions=True)
		created[doctype] += 1
		created_names.setdefault(doctype, []).append(doc.name)
		for field in doc.meta.get_table_fields():
			for row in doc.get(field.fieldname) or []:
				created[row.doctype] += 1
		return doc.name

	try:
		if not frappe.db.exists("Data Group", TEST_DATA_GROUP):
			add("Data Group", group_name=TEST_DATA_GROUP)
		lookup = {}
		for doctype in LOOKUPS:
			label = "TEST " + doctype
			lookup[doctype] = add(
				doctype,
				label_en=label,
				label_ar="اختبار " + ARABIC_LOOKUPS[doctype],
				code="TEST_" + doctype.upper().replace(" ", "_"),
				is_system=0,
			)
		fold_classes = [
			add(
				"Person Classification",
				label_en=f"TEST Fold Class {i:02}",
				label_ar=f"اختبار تصنيف مطوي {i:02}",
				code=f"TEST_FOLD_CLASS_{i:02}",
				is_system=0,
			)
			for i in range(1, FOLD_CLASSIFICATIONS + 1)
		]
		symmetric_type = add(
			"Relationship Type",
			label_en="TEST Symmetric Relationship",
			label_ar="اختبار علاقة متبادلة",
			code="TEST_RELATIONSHIP_SYMMETRIC",
			is_symmetric=1,
			is_system=0,
		)
		scheme = add("External ID Scheme", code="TEST_SCHEME", label_ar="اختبار معرف", label_en="TEST Scheme")
		platform = add(
			"Social Platform", code="TEST_PLATFORM", label_ar="اختبار منصة", label_en="TEST Platform"
		)
		gov = add(
			"Governorate",
			name="TEST_GOV",
			code="TEST_GOV",
			label_ar="اختبار محافظة",
			label_en="TEST Governorate",
			country="Iraq",
		)
		district = add(
			"District",
			name="TEST_DIST",
			code="TEST_DIST",
			label_ar="اختبار قضاء",
			label_en="TEST District",
			governorate=gov,
			country="Iraq",
		)
		municipality = add(
			"Municipality",
			name="TEST_MUNI",
			code="TEST_MUNI",
			label_ar="اختبار بلدية",
			label_en="TEST Municipality",
			district=district,
			governorate=gov,
			country="Iraq",
		)
		village = add(
			"Village",
			name="TEST_VIL",
			code="TEST_VIL",
			label_ar="اختبار قرية",
			label_en="TEST Village",
			municipality=municipality,
			district=district,
			governorate=gov,
			country="Iraq",
		)
		community = add(
			"Community",
			name="TEST_COMM",
			code="TEST_COMM",
			label_ar="اختبار مجتمع",
			label_en="TEST Community",
			village=village,
			municipality=municipality,
			district=district,
			governorate=gov,
			country="Iraq",
		)
		ext = [{"scheme": scheme, "value": "TEST-001"}]
		source = add(
			"Source",
			title="TEST Fictional Al-Nur Community Archive: Annual Report 2019",
			title_ar="اختبار تقرير أرشيف النور المجتمعي لعام ٢٠١٩",
			publisher="TEST Al-Nur Community Archive (fictional)",
			archive_reference="TEST-BOX-04-FILE-02",
			publication_date_as_stated="2019",
			publication_date="2019-01-01",
			publication_date_precision="year",
			verification_notes="Fictional source for testing; no actual archive or report is implied.",
			source_type=lookup["Source Type"],
			source_reliability=lookup["Source Reliability"],
			external_identifiers=ext,
		)
		evidence = [
			{
				"source": source,
				"support_type": "supports",
				"supported_claim": "TEST fictional report documents a community outreach initiative.",
			}
		]
		place = add(
			"Place",
			name_ar="اختبار مركز النور المجتمعي",
			name_en="TEST Al-Nur Community Centre",
			place_type=lookup["Place Type"],
			country="Iraq",
			governorate=gov,
			district=district,
			municipality=municipality,
			village=village,
			community=community,
			latitude=33.3,
			longitude=44.3,
			geo_precision="approximate",
			geocoding_method="manual",
			geo_uncertainty_m=1500,
			geometry_source="TEST illustrative point, not a verified location",
			primary_source=source,
			evidence=evidence,
		)
		institution = add(
			"Institution",
			name_ar="اختبار جمعية النور",
			name_en="TEST Al-Nur Association",
			institution_type=lookup["Institution Type"],
			institution_subcategory=lookup["Institution Subcategory"],
			governance_system=lookup["Governance System"],
			country="Iraq",
			place=place,
			latitude=33.31,
			longitude=44.31,
			founded_date_as_stated="2015",
			founded_date="2015-01-01",
			founded_date_precision="year",
			objectives="TEST fictional association coordinates community outreach and training.",
			primary_source=source,
			expertise=[{"expertise": lookup["Expertise Area"]}],
			social_accounts=[{"platform": platform, "handle": "test-only"}],
			evidence=evidence,
		)
		person = add(
			"Person",
			name_ar="اختبار ليلى السهلي",
			name_en="TEST Layla Al-Sahli",
			nationality="Iraq",
			birthplace=place,
			category="Military",
			classification=lookup["Person Classification"],
			person_status=lookup["Person Status"],
			branch=lookup["Military Branch"],
			birth_date_as_stated="1984",
			birth_date="1984-01-01",
			birth_date_precision="year",
			current_position_as_stated="TEST community outreach coordinator",
			primary_source=source,
			latitude=33.32,
			longitude=44.32,
			specializations=[{"specialization": lookup["Specialization"]}],
			leadership_assessments=[
				{
					"quality": lookup["Leadership Quality"],
					"level": lookup["Leadership Level"],
					"evidence_note": "Fictional assessment",
				}
			],
			evidence=evidence,
		)
		add(
			"Person Position",
			title_ar="اختبار منسقة التواصل المجتمعي",
			title_en="TEST Community Outreach Coordinator",
			person=person,
			institution=institution,
			place=place,
		)
		other_person = add(
			"Person",
			name_ar="اختبار سامر الدالي",
			name_en="TEST Samir Al-Dali",
			display_name="TEST Second Person",
			nationality="Iraq",
			birthplace=place,
			category=lookup["Person Category"],
			latitude=33.34,
			longitude=44.34,
		)
		# Sparse records still satisfy required fields: "incomplete" means
		# optional research information is absent, not invalid database rows.
		second_source = add("Source", title="اختبار مصدر محدود البيانات", source_type=lookup["Source Type"])
		add("Place", name_ar="اختبار مكان بلا إحداثيات", place_type=lookup["Place Type"])
		add(
			"Institution",
			name_ar="اختبار مؤسسة محدودة البيانات",
			name_original="TEST 研究機関",
			institution_type=lookup["Institution Type"],
		)
		add(
			"Person",
			name_ar="اختبار شخص عربي فقط",
			birthplace_as_stated="غير معروف",
			birth_date_as_stated="نحو ١٩٨٠",
			birth_date_precision="approximate",
		)
		mixed = add(
			"Person",
			name_ar="اختبار اسم متعدد اللغات",
			name_en="TEST Élodie O'Neil & Noor",
			name_original="تاقیکردنەوە — آزمایش — 研究者",
			birthplace=place,
			latitude=0,
			longitude=20,
			geo_precision="uncertain",
			geo_uncertainty_m=1000,
		)
		add(
			"Person",
			name_ar="اختبار اسم بالخط السيريلي",
			name_en="TEST Амина Новак",
			name_original="TEST Амина Новак",
			birthplace=place,
			birth_date="1980-01-01",
			birth_date_precision="year",
			latitude=-33.4,
			longitude=-70.6,
			geo_precision="approximate",
		)
		add(
			"Person",
			name_ar="اختبار اسم بالخط الديفاناغاري",
			name_original="TEST अनाम शोधकर्ता",
			birthplace_as_stated="غير محدد",
			latitude=0,
			longitude=0,
		)
		for index, classification_name in enumerate(fold_classes, 1):
			add(
				"Person",
				name_ar=f"اختبار شخص تصنيف {index:02}",
				name_en=f"TEST Class Person {index:02}",
				birthplace=place,
				nationality="Iraq",
				classification=classification_name,
			)
		for index in range(1, FOLD_RECORDS + 1):
			add(
				"Person",
				name_ar=f"اختبار شخص دفعة {index:02}",
				name_en=f"TEST Batch Person {index:02}",
				birthplace=place,
				nationality="Iraq",
				classification=lookup["Person Classification"],
			)
		event = add(
			"Siraj Event",
			title_ar="اختبار يوم النور للتواصل المجتمعي",
			title_en="TEST Al-Nur Community Outreach Day",
			event_type=lookup["Event Type"],
			place=place,
			start_date_as_stated="2019-05-18",
			start_date="2019-05-18 00:00:00",
			start_date_precision="day",
			description="TEST fictional one-day outreach and training event at the community centre.",
			primary_source=source,
			latitude=33.33,
			longitude=44.33,
			geo_precision="approximate",
			evidence=evidence,
		)
		for index, (source_type, source_name, dest_type, dest_name) in enumerate(
			(
				("Person", person, "Institution", institution),
				("Institution", institution, "Place", place),
				("Place", place, "Siraj Event", event),
				("Siraj Event", event, "Source", source),
				("Person", other_person, "Person", person),
			)
		):
			add(
				"Relationship",
				relationship_type=symmetric_type if index == 4 else lookup["Relationship Type"],
				subject_type=source_type,
				subject=source_name,
				object_type=dest_type,
				object=dest_name,
				evidence=[] if index == 4 else evidence,
				end_date="2020-12-31" if index == 4 else None,
				is_current=int(index != 4),
			)
		# Parallel and self relationships exercise the inspector and matrix;
		# the isolated Arabic-only person deliberately has no relationship.
		add(
			"Relationship",
			relationship_type=lookup["Relationship Type"],
			subject_type="Person",
			subject=other_person,
			object_type="Person",
			object=person,
			evidence=[
				{
					"source": second_source,
					"support_type": "contradicts",
					"supported_claim": "TEST fictional second account disputes the reported association.",
				},
				{
					"source": source,
					"support_type": "contextualizes",
					"supported_claim": "TEST fictional report describes the outreach programme.",
				},
			],
		)
		add(
			"Relationship",
			relationship_type=lookup["Relationship Type"],
			subject_type="Person",
			subject=mixed,
			object_type="Person",
			object=mixed,
		)
		add("Siraj Event", title_ar="اختبار حدث ناقص البيانات", event_type=lookup["Event Type"])
		region = add(
			"Place",
			name_ar="اختبار منطقة قيادة",
			name_en="TEST Region Place",
			place_type=lookup["Place Type"],
			country="Iraq",
			is_group=1,
			latitude=33.34,
			longitude=44.34,
			geo_precision="approximate",
			geocoding_method="manual",
			geo_uncertainty_m=5000,
		)
		subregion = add(
			"Place",
			name_ar="اختبار قطاع فرعي",
			name_en="TEST Subregion Place",
			place_type=lookup["Place Type"],
			country="Iraq",
			parent_place=region,
			latitude=33.345,
			longitude=44.345,
			geo_precision="approximate",
			geocoding_method="manual",
			geo_uncertainty_m=2000,
		)
		division = add(
			"Military Unit",
			unit_name="TEST Division Unit",
			echelon="Division",
			status="Active",
			is_group=1,
			linked_place=subregion,
			classification=add(
				"Unit Classification",
				classification_name="TEST Div Class",
				category="Combat",
			),
		)
		classification = add(
			"Unit Classification",
			classification_name="TEST Unit Classification",
			category="Training",
			external_identifiers=ext,
		)
		armament = add("Armament", armament_name="TEST Equipment", category="Support", evidence=evidence)
		unit = add(
			"Military Unit",
			unit_name="TEST Parent Unit",
			echelon="Brigade",
			status="Active",
			direct_personnel=50,
			is_group=1,
			linked_place=subregion,
			parent_unit=division,
			classification=classification,
			commander=person,
			latitude=33.35,
			longitude=44.35,
			armaments=[{"armament": armament, "quantity": 2}],
		)
		child = add(
			"Military Unit",
			unit_name="TEST Child Unit",
			echelon="Company",
			status="Training",
			direct_personnel=20,
			parent_unit=unit,
			linked_place=subregion,
			classification=classification,
		)
		add(
			"Military Unit",
			unit_name="TEST Unassigned Unit",
			echelon="Detachment",
			status="Standby",
			direct_personnel=0,
		)
		deployment = add(
			"Operational Deployment",
			deployment_name="TEST Deployment",
			unit=unit,
			start_date="2020-01-01",
			status="Planned",
			latitude=33.36,
			longitude=44.36,
		)
		add(
			"Mission",
			mission_name="TEST Mission",
			unit=child,
			deployment=deployment,
			start_date="2020-01-02",
			status="Planned",
		)
		add(
			"Mission",
			mission_name="TEST Ongoing Mission",
			unit=unit,
			start_date="2020-03-01",
			status="Ongoing",
		)
		add(
			"Training Exercise",
			exercise_name="TEST Exercise",
			unit=child,
			start_date="2020-02-01",
			end_date="2020-02-03",
			participant_count=10,
		)
		add(
			"Training Exercise",
			exercise_name="TEST Single-day Exercise",
			unit=unit,
			start_date="2020-04-01",
			end_date="2020-04-01",
			participant_count=5,
			assessment="Needs Improvement",
		)
		add(
			"Command Appointment",
			unit=unit,
			commander=person,
			role="Commanding Officer",
			assigned_date="2020-01-01",
		)
		missing = [
			doctype
			for doctype in (
				*LOOKUPS,
				*OPERATIONAL_TYPES,
				*CHILD_TYPES,
				"Governorate",
				"District",
				"Municipality",
				"Village",
				"Community",
				"External ID Scheme",
				"Social Platform",
			)
			if not created[doctype]
		]
		if missing:
			raise RuntimeError("Fixture is incomplete: " + ", ".join(missing))
		return {
			"site": frappe.local.site,
			"created": dict(sorted(created.items())),
			"created_names": created_names,
			"existing_singleton": "SIRAJ Settings",
			"message": "Fictional samples share this site's database; SIRAJ Settings was not modified.",
		}
	except Exception:
		frappe.db.rollback()
		raise
