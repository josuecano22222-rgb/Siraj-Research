"""Explicitly requested synthetic records; never inserted during installation.

This is a bench-execute helper, not a web endpoint. If run on a production
site, samples share its database and are not isolated. See docs/test-data.md.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy

import frappe

LOOKUPS = (
    "Authentication Level", "Documentation Level", "Event Type", "Expertise Area",
    "Governance System", "Institution Subcategory", "Institution Type", "Leadership Level",
    "Leadership Quality", "Military Branch", "Military Service Status", "Person Category",
    "Person Classification", "Person Status", "Place Type", "Relationship Type",
    "Source Reliability", "Source Type", "Specialization",
)
# Presence of ANY operational record stops the fixture; this check is intentionally
# not limited to records visible to the calling user's list permissions.
OPERATIONAL_TYPES = (
    "Armament", "Command Appointment", "Command Region", "Event", "Institution",
    "Military Division", "Military Unit", "Mission", "Operational Deployment", "Person",
    "Place", "Relationship", "Source", "Training Exercise", "Unit Classification",
)
CHILD_TYPES = (
    "Evidence", "Expertise Link", "External Identifier", "Leadership Quality Assessment",
    "Person Position", "Social Account", "Specialization Link", "Unit Armament Holding",
)


def _guard():
    if not frappe.local.site or not frappe.db.exists("DocType", "SIRAJ Settings"):
        raise RuntimeError("Install siraj_research on the selected site first.")
    for doctype, name in (("Country", "Iraq"), ("Person Category", "Military"), ("Workflow State", "Draft")):
        if not frappe.db.exists(doctype, name):
            raise RuntimeError("Missing fixture prerequisite: " + doctype + " / " + name)

    # Fixed identifiers provide a conservative one-run guard, not ownership
    # proof. Never overwrite an existing matching name OR unique code.
    fixed = [(doctype, "TEST " + doctype, "TEST_" + doctype.upper().replace(" ", "_")) for doctype in LOOKUPS]
    fixed += [("Relationship Type", "TEST Symmetric Relationship", "TEST_RELATIONSHIP_SYMMETRIC")]
    for doctype, name, code in fixed:
        if frappe.db.exists(doctype, name) or frappe.db.exists(doctype, {"code": code}):
            raise RuntimeError("Sample identifier already exists in " + doctype + "; no records were inserted.")
    for doctype, code in (("External ID Scheme", "TEST_SCHEME"), ("Social Platform", "TEST_PLATFORM"),
                          ("Governorate", "TEST_GOV"), ("District", "TEST_DIST"),
                          ("Municipality", "TEST_MUNI"), ("Village", "TEST_VIL"), ("Community", "TEST_COMM")):
        if frappe.db.exists(doctype, code) or frappe.db.exists(doctype, {"code": code}):
            raise RuntimeError("Sample identifier already exists in " + doctype + "; no records were inserted.")
    if frappe.db.exists("Unit Classification", "TEST Unit Classification"):
        raise RuntimeError("Sample identifier already exists in Unit Classification; no records were inserted.")


def seed_test_data():
    """Insert one connected, fictional dataset; return counts, never commit here.

    A second run is deliberately rejected. On failure, roll back the entire
    transaction. Running on production deliberately mixes samples into its data.
    """
    _guard()
    created = Counter()
    created_names = {}
    def add(doctype, **values):
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
        lookup = {}
        for doctype in LOOKUPS:
            label = "TEST " + doctype
            lookup[doctype] = add(doctype, label_en=label, label_ar="اختبار " + doctype,
                                  code="TEST_" + doctype.upper().replace(" ", "_"), is_system=0)
        symmetric_type = add("Relationship Type", label_en="TEST Symmetric Relationship", label_ar="اختبار علاقة متبادلة", code="TEST_RELATIONSHIP_SYMMETRIC", is_symmetric=1, is_system=0)
        scheme = add("External ID Scheme", code="TEST_SCHEME", label_ar="اختبار معرف", label_en="TEST Scheme")
        platform = add("Social Platform", code="TEST_PLATFORM", label_ar="اختبار منصة", label_en="TEST Platform")
        gov = add("Governorate", code="TEST_GOV", label_ar="اختبار محافظة", label_en="TEST Governorate", country="Iraq")
        district = add("District", code="TEST_DIST", label_ar="اختبار قضاء", label_en="TEST District", governorate=gov, country="Iraq")
        municipality = add("Municipality", code="TEST_MUNI", label_ar="اختبار بلدية", label_en="TEST Municipality", district=district, governorate=gov, country="Iraq")
        village = add("Village", code="TEST_VIL", label_ar="اختبار قرية", label_en="TEST Village", municipality=municipality, district=district, governorate=gov, country="Iraq")
        community = add("Community", code="TEST_COMM", label_ar="اختبار مجتمع", label_en="TEST Community", village=village, municipality=municipality, district=district, governorate=gov, country="Iraq")
        ext = [{"scheme": scheme, "value": "TEST-001"}]
        source = add("Source", title="TEST fictional source", display_name="TEST fictional source", source_type=lookup["Source Type"], source_reliability=lookup["Source Reliability"], external_identifiers=ext)
        evidence = [{"source": source, "support_type": "supports", "supported_claim": "Fictional test claim"}]
        place = add("Place", name_ar="اختبار مكان", name_en="TEST Place", display_name="TEST Place", place_type=lookup["Place Type"], country="Iraq", governorate=gov, district=district, municipality=municipality, village=village, community=community, latitude=33.3, longitude=44.3, geo_precision="approximate", geocoding_method="manual", evidence=evidence)
        institution = add("Institution", name_ar="اختبار مؤسسة", name_en="TEST Institution", display_name="TEST Institution", institution_type=lookup["Institution Type"], institution_subcategory=lookup["Institution Subcategory"], governance_system=lookup["Governance System"], country="Iraq", place=place, latitude=33.31, longitude=44.31, expertise=[{"expertise": lookup["Expertise Area"]}], social_accounts=[{"platform": platform, "handle": "test-only"}], evidence=evidence)
        person = add("Person", name_ar="اختبار شخص", name_en="TEST Person", display_name="TEST Person", nationality="Iraq", birthplace=place, category="Military", classification=lookup["Person Classification"], person_status=lookup["Person Status"], branch=lookup["Military Branch"], latitude=33.32, longitude=44.32, positions=[{"title_ar": "اختبار منصب", "title_en": "TEST Position", "institution": institution, "place": place}], specializations=[{"specialization": lookup["Specialization"]}], leadership_assessments=[{"quality": lookup["Leadership Quality"], "level": lookup["Leadership Level"], "evidence_note": "Fictional assessment"}], evidence=evidence)
        other_person = add("Person", name_ar="اختبار شخص ثان", name_en="TEST Second Person", display_name="TEST Second Person", nationality="Iraq", birthplace=place, category=lookup["Person Category"], latitude=33.34, longitude=44.34)
        event = add("Event", title_ar="اختبار حدث", title_en="TEST Event", display_name="TEST Event", event_type=lookup["Event Type"], place=place, latitude=33.33, longitude=44.33, evidence=evidence)
        for index, (source_type, source_name, dest_type, dest_name) in enumerate((("Person", person, "Institution", institution), ("Institution", institution, "Place", place), ("Place", place, "Event", event), ("Event", event, "Source", source), ("Person", other_person, "Person", person))):
            add("Relationship", relationship_type=symmetric_type if index == 4 else lookup["Relationship Type"], subject_type=source_type, subject=source_name, object_type=dest_type, object=dest_name, evidence=[] if index == 4 else evidence, end_date="2020-12-31" if index == 4 else None, is_current=int(index != 4))
        region = add("Command Region", region_name="TEST Region", country="Iraq", is_group=1, region_type="Region")
        subregion = add("Command Region", region_name="TEST Subregion", country="Iraq", parent_region=region, region_type="Area")
        division = add("Military Division", division_name="TEST Division", region=subregion)
        classification = add("Unit Classification", classification_name="TEST Unit Classification", category="Training", external_identifiers=ext)
        armament = add("Armament", armament_name="TEST Equipment", category="Support", evidence=evidence)
        unit = add("Military Unit", unit_name="TEST Parent Unit", echelon="Brigade", status="Active", direct_personnel=50, is_group=1, region=subregion, division=division, classification=classification, commander=person, latitude=33.35, longitude=44.35, armaments=[{"armament": armament, "quantity": 2}])
        child = add("Military Unit", unit_name="TEST Child Unit", echelon="Company", status="Training", direct_personnel=20, parent_unit=unit, region=subregion, classification=classification)
        deployment = add("Operational Deployment", deployment_name="TEST Deployment", unit=unit, start_date="2020-01-01", status="Planned", latitude=33.36, longitude=44.36)
        add("Mission", mission_name="TEST Mission", unit=child, deployment=deployment, start_date="2020-01-02", status="Planned")
        add("Training Exercise", exercise_name="TEST Exercise", unit=child, start_date="2020-02-01", end_date="2020-02-03", participant_count=10)
        add("Command Appointment", unit=unit, commander=person, role="Commanding Officer", assigned_date="2020-01-01")
        missing = [doctype for doctype in (*LOOKUPS, *OPERATIONAL_TYPES, *CHILD_TYPES, "Governorate", "District", "Municipality", "Village", "Community", "External ID Scheme", "Social Platform") if not created[doctype]]
        if missing:
            raise RuntimeError("Fixture is incomplete: " + ", ".join(missing))
        return {"site": frappe.local.site, "created": dict(sorted(created.items())), "created_names": created_names,
                "existing_singleton": "SIRAJ Settings", "message": "Fictional samples share this site's database; SIRAJ Settings was not modified."}
    except Exception:
        frappe.db.rollback()
        raise
