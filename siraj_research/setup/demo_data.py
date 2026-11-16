"""Seed a rich [DEMO] dataset for SIRAJ Research.

Run on the server:

    bench --site frappe.com execute siraj_research.setup.demo_data.seed_demo_data

The script is idempotent: it checks for the `[DEMO]` marker on primary records
before creating anything, so re-running it will not duplicate records. It does
not touch non-DEMO records.

Companion teardown:

    bench --site frappe.com execute siraj_research.setup.demo_data.teardown_demo_data
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

import frappe

TAG = "[DEMO]"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_first(doctype: str, **filters) -> str | None:
    return frappe.db.exists(doctype, filters)


def _add(doctype: str, values: dict[str, Any], **check) -> str:
    existing = frappe.db.exists(doctype, check) if check else None
    if existing:
        return existing
    doc = frappe.get_doc({"doctype": doctype, **values})
    doc.insert(ignore_permissions=True)
    return doc.name


def _append_evidence(doc, source_name: str, *, support: str = "supports",
                     claim: str = "", page: str = "", notes: str = "") -> None:
    for row in doc.evidence or []:
        if row.source == source_name and (not claim or row.supported_claim == claim):
            return
    auth = _get_first("Authentication Level", code="single_source")
    doc.append("evidence", {
        "source": source_name,
        "support_type": support,
        "supported_claim": claim,
        "page_or_timestamp": page,
        "authentication_level": auth,
        "notes": notes,
    })


def _workflow_state(state: str = "Published") -> str:
    return _get_first("Workflow State", workflow_state_name=state) or state


# ---------------------------------------------------------------------------
# Geo
# ---------------------------------------------------------------------------

class Geo:
    BAGHDAD = (33.3152, 44.3661)
    NORTH_CAMP = (33.3850, 44.3400)
    TAJI = (33.2780, 44.1040)
    RASHID = (33.2200, 44.4500)
    MOD = (33.3300, 44.4000)
    MIL_COLLEGE = (33.3500, 44.3800)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def seed_demo_data():
    report = {}
    today = _dt.date.today()

    # ------------------------------------------------------------------
    # Country & admin units — seeded by master_data; lookup by code/label
    # ------------------------------------------------------------------
    country_iq = _get_first("Country", code="IQ") or "Iraq"
    baghdad_gov = _get_first("Governorate", code="BG") or _get_first("Governorate", country=country_iq)

    # Place types — master_data seeds these with codes
    pt_city = _get_first("Place Type", code="city")
    pt_building = _get_first("Place Type", code="building")
    pt_region = _get_first("Place Type", code="region")

    # Lookup-domain codes (verified against reference_data/lookups.json):
    AUTH_SINGLE = _get_first("Authentication Level", code="single_source")
    AUTH_CORROB = _get_first("Authentication Level", code="corroborated")
    AUTH_PRIMARY = _get_first("Authentication Level", code="primary_document")
    DOC_SUBSTANTIAL = _get_first("Documentation Level", code="substantial")
    DOC_PARTIAL = _get_first("Documentation Level", code="partial")
    DOC_MINIMAL = _get_first("Documentation Level", code="minimal")
    SRC_RELIAB_MED = _get_first("Source Reliability", code="medium")
    SRC_RELIAB_HIGH = _get_first("Source Reliability", code="high")
    SRC_TYPE_ENCYC = _get_first("Source Type", code="encyclopedia")
    SRC_TYPE_REPORT = _get_first("Source Type", code="report")
    SRC_TYPE_WEB = _get_first("Source Type", code="website")
    CAT_MIL = _get_first("Person Category", code="military")
    STAT_ACTIVE = _get_first("Person Status", code="active")
    STAT_RETIRED = _get_first("Person Status", code="retired")
    BRANCH_ARMY = _get_first("Military Branch", code="Army")
    SVC_ACTIVE = _get_first("Military Service Status", code="Active")
    SVC_RESERVE = _get_first("Military Service Status", code="Reserve")
    INST_MINISTRY = _get_first("Institution Type", code="ministry")
    INST_COLLEGE = _get_first("Institution Type", code="college")
    INST_SUB_MIL = _get_first("Institution Subcategory", code="military")
    GOV_MIL = _get_first("Governance System", code="military")
    PTYPE_BIRTH = _get_first("Event Type", code="birth")
    PTYPE_APPT = _get_first("Event Type", code="appointment")
    PTYPE_FOUND = _get_first("Event Type", code="founding")
    PTYPE_CONF = _get_first("Event Type", code="conference")
    PTYPE_OTHER = _get_first("Event Type", code="other")

    # Relationship-type codes from lookups.json:
    REL_COMMANDS = _get_first("Relationship Type", code="director_of")
    REL_EMPLOYED_BY = _get_first("Relationship Type", code="employed_by")
    REL_MEMBER_OF = _get_first("Relationship Type", code="member_of")
    REL_LOCATED_IN = _get_first("Relationship Type", code="located_in")
    REL_CONTAINS = _get_first("Relationship Type", code="contains")
    REL_GRADUATED = _get_first("Relationship Type", code="graduated_from")
    REL_PARTICIPATED = _get_first("Relationship Type", code="participated_in")
    REL_FOUNDER_OF = _get_first("Relationship Type", code="founder_of")
    REL_AFFILIATED = _get_first("Relationship Type", code="affiliated_with")

    # ------------------------------------------------------------------
    # 1. Command Region (created FIRST because Military Division.region is mandatory)
    # ------------------------------------------------------------------
    regions = {}
    regions["baghdad_ops"] = _add("Command Region", {
        "naming_series": "MIL-REG-.####",
        "region_name": f"Baghdad Operations Command {TAG}",
        "region_type": "Region",
        "country": country_iq,
        "description": f"{TAG} Unified command covering Baghdad governorate and the central belts.",
        "workflow_state": _workflow_state("Published"),
    }, region_name=f"Baghdad Operations Command {TAG}")

    # ------------------------------------------------------------------
    # 2. Military Division (top-level formation; unit-classification record)
    # ------------------------------------------------------------------
    cls_mech = _get_first("Unit Classification", classification_name="Mechanized Infantry")
    if not cls_mech:
        cls_mech = _add("Unit Classification", {
            "naming_series": "MIL-CLS-.####",
            "classification_name": "Mechanized Infantry",
            "category": "Combat",
            "readiness_tier": "High",
            "description": "Armoured personnel carrier-mounted infantry with organic tank support.",
            "workflow_state": _workflow_state("Published"),
        }, classification_name="Mechanized Infantry")

    div6_md = _add("Military Division", {
        "naming_series": "MIL-DIV-.####",
        "division_name": f"6th Mechanised Division (demo) {TAG}",
        "region": regions["baghdad_ops"],
        "division_type": "Mechanized",
        "formation_date": _dt.date(2005, 1, 1),
        "headquarters": f"Camp Rashid, Baghdad {TAG}",
        "workflow_state": _workflow_state("Published"),
    }, division_name=f"6th Mechanised Division (demo) {TAG}")

    # ------------------------------------------------------------------
    # 3. Places
    # ------------------------------------------------------------------
    places = {}

    places["baghdad"] = _add("Place", {
        "naming_series": "PLC-.####",
        "name_ar": f"بغداد {TAG}",
        "name_en": f"Baghdad {TAG}",
        "is_group": 1,
        "place_type": pt_city,
        "country": country_iq,
        "governorate": baghdad_gov,
        "latitude": Geo.BAGHDAD[0],
        "longitude": Geo.BAGHDAD[1],
        "geo_precision": "centroid",
        "geocoding_method": "city_centroid",
        "geo_uncertainty_m": 5000,
        "workflow_state": _workflow_state("Published"),
    }, name_en=f"Baghdad {TAG}")

    places["taji_camp"] = _add("Place", {
        "naming_series": "PLC-.####",
        "name_ar": f"معسكر التاجي {TAG}",
        "name_en": f"Taji Military Camp {TAG}",
        "place_type": pt_building,
        "country": country_iq,
        "governorate": baghdad_gov,
        "parent_place": places["baghdad"],
        "latitude": Geo.TAJI[0],
        "longitude": Geo.TAJI[1],
        "geo_precision": "approximate",
        "geocoding_method": "gazetteer",
        "geo_uncertainty_m": 500,
        "workflow_state": _workflow_state("Published"),
    }, name_en=f"Taji Military Camp {TAG}")

    places["mod_hq"] = _add("Place", {
        "naming_series": "PLC-.####",
        "name_ar": f"مقر وزارة الدفاع {TAG}",
        "name_en": f"Ministry of Defence HQ {TAG}",
        "place_type": pt_building,
        "country": country_iq,
        "governorate": baghdad_gov,
        "parent_place": places["baghdad"],
        "latitude": Geo.MOD[0],
        "longitude": Geo.MOD[1],
        "geo_precision": "approximate",
        "geocoding_method": "administrative",
        "geo_uncertainty_m": 200,
        "workflow_state": _workflow_state("Published"),
    }, name_en=f"Ministry of Defence HQ {TAG}")

    places["mil_college"] = _add("Place", {
        "naming_series": "PLC-.####",
        "name_ar": f"الكلية العسكرية {TAG}",
        "name_en": f"Military College Campus {TAG}",
        "place_type": pt_building,
        "country": country_iq,
        "governorate": baghdad_gov,
        "parent_place": places["baghdad"],
        "latitude": Geo.MIL_COLLEGE[0],
        "longitude": Geo.MIL_COLLEGE[1],
        "geo_precision": "approximate",
        "geocoding_method": "administrative",
        "geo_uncertainty_m": 150,
        "workflow_state": _workflow_state("Published"),
    }, name_en=f"Military College Campus {TAG}")

    places["rashid"] = _add("Place", {
        "naming_series": "PLC-.####",
        "name_ar": f"معسكر الرشيد {TAG}",
        "name_en": f"Camp Rashid {TAG}",
        "place_type": pt_building,
        "country": country_iq,
        "governorate": baghdad_gov,
        "parent_place": places["baghdad"],
        "latitude": Geo.RASHID[0],
        "longitude": Geo.RASHID[1],
        "geo_precision": "approximate",
        "geocoding_method": "gazetteer",
        "geo_uncertainty_m": 400,
        "workflow_state": _workflow_state("Published"),
    }, name_en=f"Camp Rashid {TAG}")

    # ------------------------------------------------------------------
    # 4. Sources
    # ------------------------------------------------------------------
    sources = {}

    sources["wiki"] = _add("Source", {
        "naming_series": "SRC-.####",
        "title": f"Wikipedia: Iraqi Ground Forces {TAG}",
        "title_ar": f"ويكيبيديا: القوات البرية العراقية {TAG}",
        "source_type": SRC_TYPE_ENCYC,
        "publisher": "Wikipedia (demo entry)",
        "publication_date_as_stated": "2024",
        "publication_date": _dt.datetime(2024, 6, 1),
        "publication_date_precision": "year",
        "access_date": today,
        "source_reliability": SRC_RELIAB_MED,
        "workflow_state": _workflow_state("Published"),
    }, title=f"Wikipedia: Iraqi Ground Forces {TAG}")

    sources["iiss"] = _add("Source", {
        "naming_series": "SRC-.####",
        "title": f"IISS Military Balance (demo entry) {TAG}",
        "source_type": SRC_TYPE_REPORT,
        "publisher": "International Institute for Strategic Studies (DEMO)",
        "publication_date_as_stated": "2025",
        "publication_date": _dt.datetime(2025, 2, 15),
        "publication_date_precision": "year",
        "access_date": today,
        "source_reliability": SRC_RELIAB_HIGH,
        "workflow_state": _workflow_state("Published"),
    }, title=f"IISS Military Balance (demo entry) {TAG}")

    sources["mod"] = _add("Source", {
        "naming_series": "SRC-.####",
        "title": f"Ministry of Defence press release (DEMO) {TAG}",
        "source_type": SRC_TYPE_WEB,
        "publisher": "Ministry of Defence (DEMO)",
        "publication_date_as_stated": "March 2026",
        "publication_date": _dt.datetime(2026, 3, 10),
        "publication_date_precision": "month",
        "access_date": today,
        "source_reliability": SRC_RELIAB_MED,
        "url": "https://mod.mil.iq/demo-press-release",
        "workflow_state": _workflow_state("Published"),
    }, title=f"Ministry of Defence press release (DEMO) {TAG}")

    sources["dod"] = _add("Source", {
        "naming_series": "SRC-.####",
        "title": f"Country report on Iraq (DEMO) {TAG}",
        "source_type": SRC_TYPE_REPORT,
        "publisher": "Defunct reference publisher (DEMO)",
        "publication_date_as_stated": "2024",
        "publication_date": _dt.datetime(2024, 11, 1),
        "publication_date_precision": "year",
        "access_date": today,
        "source_reliability": SRC_RELIAB_MED,
        "workflow_state": _workflow_state("Verified"),
    }, title=f"Country report on Iraq (DEMO) {TAG}")

    # ------------------------------------------------------------------
    # 5. Institutions
    # ------------------------------------------------------------------
    insts = {}

    insts["mod"] = _add("Institution", {
        "naming_series": "INS-.####",
        "name_ar": f"وزارة الدفاع {TAG}",
        "name_en": f"Ministry of Defence {TAG}",
        "abbreviation": "MoD",
        "institution_type": INST_MINISTRY,
        "institution_subcategory": INST_SUB_MIL,
        "governance_system": GOV_MIL,
        "country": country_iq,
        "governorate": baghdad_gov,
        "place": places["mod_hq"],
        "founded_date": _dt.date(1921, 1, 1),
        "founded_date_as_stated": "1921",
        "founded_date_precision": "year",
        "website": "https://mod.mil.iq",
        "latitude": Geo.MOD[0],
        "longitude": Geo.MOD[1],
        "geo_precision": "approximate",
        "geocoding_method": "administrative",
        "research_significance": f"{TAG} Supreme headquarters of the armed forces in this demo dataset.",
        "workflow_state": _workflow_state("Published"),
    }, name_en=f"Ministry of Defence {TAG}")

    insts["rust_college"] = _add("Institution", {
        "naming_series": "INS-.####",
        "name_ar": f"الكلية العسكرية الأولى (الرستمية) {TAG}",
        "name_en": f"First Military College (Al-Rustamiyah) {TAG}",
        "abbreviation": "RMC",
        "institution_type": INST_COLLEGE,
        "institution_subcategory": INST_SUB_MIL,
        "governance_system": GOV_MIL,
        "country": country_iq,
        "governorate": baghdad_gov,
        "place": places["mil_college"],
        "founded_date_as_stated": "1924",
        "founded_date": _dt.date(1924, 1, 1),
        "founded_date_precision": "year",
        "latitude": Geo.MIL_COLLEGE[0],
        "longitude": Geo.MIL_COLLEGE[1],
        "geo_precision": "approximate",
        "geocoding_method": "administrative",
        "objectives": f"{TAG} Commissions officers through a three-year academic and military curriculum.",
        "workflow_state": _workflow_state("Published"),
    }, name_en=f"First Military College (Al-Rustamiyah) {TAG}")

    # ------------------------------------------------------------------
    # 6. Persons
    # ------------------------------------------------------------------
    persons = {}

    def _person(name_en: str, name_ar: str, rank_en: str, lat, lng, pos_en: str) -> str:
        return _add("Person", {
            "naming_series": "PER-.####",
            "display_name": f"{name_en} {TAG}",
            "name_ar": f"{name_ar} {TAG}",
            "name_en": f"{name_en} {TAG}",
            "name_transliteration": name_en,
            "person_category": CAT_MIL,
            "category": CAT_MIL,
            "person_status": STAT_ACTIVE,
            "nationality": country_iq,
            "rank_title": rank_en,
            "branch": BRANCH_ARMY,
            "commission_date": _dt.date(1992, 1, 1),
            "service_status": SVC_ACTIVE,
            "current_position_as_stated": pos_en,
            "military_biography": f"{TAG} Synthetic profile for SIRAJ demo data.",
            "latitude": lat, "longitude": lng,
            "geo_precision": "centroid",
            "geocoding_method": "administrative",
            "workflow_state": _workflow_state("Published"),
        }, name_en=f"{name_en} {TAG}")

    persons["cofs"] = _person("Gen. Abd al-Rahman al-Tamimi", "الفريق عبد الرحمن التميمي",
                              "Lieutenant General", Geo.MOD[0], Geo.MOD[1],
                              "Chief of Staff, Iraqi Armed Forces (demo)")
    persons["div1"] = _person("Maj. Gen. Hassan al-Jabouri", "اللواء الركن حسن الجبوري",
                              "Major General", Geo.RASHID[0], Geo.RASHID[1],
                              "Commander, 6th Mechanised Division (demo)")
    persons["bde1"] = _person("Brig. Gen. Karim al-Lami", "العميد الركن كريم اللامي",
                              "Brigadier General", Geo.TAJI[0], Geo.TAJI[1],
                              "Commander, 22nd Mechanised Brigade (demo)")
    persons["train"] = _person("Col. Saad al-Moussawi", "العقيد الركن سعد الموسوي",
                               "Colonel", Geo.TAJI[0], Geo.TAJI[1],
                               "Lead Trainer, Joint Readiness Exercise (demo)")

    # Positions + evidence on each person
    pos_map = {
        "cofs": ("Chief of Staff", "رئيس الأركان", insts["mod"]),
        "div1": ("Division Commander", "قائد فرقة", insts["mod"]),
        "bde1": ("Brigade Commander", "قائد لواء", insts["mod"]),
        "train": ("Senior Instructor", "مدرب أول", insts["rust_college"]),
    }
    for key, doc_name in persons.items():
        doc = frappe.get_doc("Person", doc_name)
        t_en, t_ar, inst = pos_map[key]
        if not doc.positions:
            doc.append("positions", {
                "title_en": f"{t_en} {TAG}",
                "title_ar": f"{t_ar} {TAG}",
                "institution": inst,
                "start_date": _dt.date(today.year - 2, today.month, max(today.day, 1)),
                "start_date_precision": "year",
                "is_current": 1,
                "verified": 1,
            })
        _append_evidence(doc, sources["iiss"], claim="Command posting and rank")
        doc.save(ignore_permissions=True)

    # ------------------------------------------------------------------
    # 7. Armaments (master records — armament child table requires a Link)
    # ------------------------------------------------------------------
    armaments = {}
    def _armament(code, name, category, spec=""):
        aname = f"{name} {TAG}"
        armaments[code] = _add("Armament", {
            "naming_series": "MIL-ARM-.category.#####",
            "armament_name": aname,
            "category": category,
            "origin_country": country_iq,
            "specification": spec,
            "primary_source": sources["iiss"],
            "documentation_level": DOC_MINIMAL,
            "authentication_level": AUTH_SINGLE,
            "workflow_state": _workflow_state("Published"),
        }, armament_name=aname)

    _armament("m1a1m", "M1A1M Abrams MBT", "Vehicles", "Main battle tank, 120mm gun")
    _armament("bmp1", "BMP-1 IFV", "Vehicles", "Infantry fighting vehicle, 73mm gun")
    _armament("m113", "M113 APC", "Vehicles", "Armoured personnel carrier")
    _armament("m198", "M198 155mm howitzer", "Artillery", "Towed howitzer")

    # ------------------------------------------------------------------
    # 8. Military Units
    # ------------------------------------------------------------------
    units = {}

    units["div6"] = _add("Military Unit", {
        "naming_series": "MIL-UNIT-.####",
        "unit_name": f"6th Mechanised Division (demo) {TAG}",
        "is_group": 1,
        "echelon": "Division",
        "division": div6_md,
        "region": regions["baghdad_ops"],
        "status": "Active",
        "direct_personnel": 320,
        "classification": cls_mech,
        "headquarters": f"Camp Rashid, Baghdad {TAG}",
        "formation_date": _dt.date(2005, 1, 1),
        "commander": persons["div1"],
        "latitude": Geo.RASHID[0],
        "longitude": Geo.RASHID[1],
        "geo_precision": "approximate",
        "geocoding_method": "gazetteer",
        "geo_uncertainty_m": 800,
        "workflow_state": _workflow_state("Published"),
        "primary_source": sources["iiss"],
        "documentation_level": DOC_PARTIAL,
        "authentication_level": AUTH_SINGLE,
        "researcher_notes": f"{TAG} Demo mechanised infantry division.",
    }, unit_name=f"6th Mechanised Division (demo) {TAG}")

    d6doc = frappe.get_doc("Military Unit", units["div6"])
    if not d6doc.armaments:
        d6doc.append("armaments", {"armament": armaments["m1a1m"], "quantity": 42, "condition": "Serviceable"})
        d6doc.append("armaments", {"armament": armaments["bmp1"],  "quantity": 80, "condition": "Serviceable"})
        d6doc.append("armaments", {"armament": armaments["m198"],  "quantity": 18, "condition": "Limited"})
    _append_evidence(d6doc, sources["iiss"], claim="Established 2005; composition")
    d6doc.save(ignore_permissions=True)

    units["bde22"] = _add("Military Unit", {
        "naming_series": "MIL-BRG-.####",
        "unit_name": f"22nd Mechanised Brigade (demo) {TAG}",
        "is_group": 0,
        "parent_unit": units["div6"],
        "echelon": "Brigade",
        "division": div6_md,
        "region": regions["baghdad_ops"],
        "status": "Active",
        "direct_personnel": 1850,
        "classification": cls_mech,
        "commander": persons["bde1"],
        "headquarters": f"Taji Military Camp {TAG}",
        "latitude": Geo.TAJI[0],
        "longitude": Geo.TAJI[1],
        "geo_precision": "approximate",
        "geocoding_method": "gazetteer",
        "geo_uncertainty_m": 600,
        "workflow_state": _workflow_state("Published"),
        "primary_source": sources["iiss"],
        "documentation_level": DOC_PARTIAL,
        "authentication_level": AUTH_SINGLE,
    }, unit_name=f"22nd Mechanised Brigade (demo) {TAG}")
    b22 = frappe.get_doc("Military Unit", units["bde22"])
    if not b22.armaments:
        b22.append("armaments", {"armament": armaments["bmp1"],  "quantity": 45, "condition": "Serviceable"})
        b22.append("armaments", {"armament": armaments["m113"],  "quantity": 60, "condition": "Serviceable"})
    _append_evidence(b22, sources["iiss"], claim="Brigade garrison and commander")
    b22.save(ignore_permissions=True)

    units["bde24"] = _add("Military Unit", {
        "naming_series": "MIL-BRG-.####",
        "unit_name": f"24th Motorised Brigade (demo) {TAG}",
        "is_group": 0,
        "parent_unit": units["div6"],
        "echelon": "Brigade",
        "division": div6_md,
        "region": regions["baghdad_ops"],
        "status": "Training",
        "direct_personnel": 1420,
        "classification": cls_mech,
        "headquarters": f"Camp Rashid {TAG}",
        "latitude": Geo.RASHID[0],
        "longitude": Geo.RASHID[1] + 0.02,
        "geo_precision": "approximate",
        "geocoding_method": "gazetteer",
        "geo_uncertainty_m": 800,
        "workflow_state": _workflow_state("In Review"),
        "primary_source": sources["dod"],
        "documentation_level": DOC_MINIMAL,
        "authentication_level": AUTH_SINGLE,
    }, unit_name=f"24th Motorised Brigade (demo) {TAG}")

    # ------------------------------------------------------------------
    # 9. Operational Deployment
    # ------------------------------------------------------------------
    deploys = {}
    dep_start = today - _dt.timedelta(days=90)
    deploys["baghdad_sec"] = _add("Operational Deployment", {
        "naming_series": "MIL-DEP-.YYYY.-.####",
        "deployment_name": f"Baghdad Belt Security (DEMO) {TAG}",
        "unit": units["bde22"],
        "status": "Active",
        "start_date": dep_start,
        "latitude": Geo.NORTH_CAMP[0],
        "longitude": Geo.NORTH_CAMP[1],
        "geo_precision": "centroid",
        "geocoding_method": "inherited",
        "primary_source": sources["mod"],
        "documentation_level": DOC_MINIMAL,
        "authentication_level": AUTH_SINGLE,
        "workflow_state": _workflow_state("Verified"),
    }, deployment_name=f"Baghdad Belt Security (DEMO) {TAG}")
    ddoc = frappe.get_doc("Operational Deployment", deploys["baghdad_sec"])
    _append_evidence(ddoc, sources["mod"], claim="Deployment to northern Baghdad belt", page="2026-03-10")
    ddoc.save(ignore_permissions=True)

    # ------------------------------------------------------------------
    # 10. Training Exercise
    # ------------------------------------------------------------------
    t_start = today - _dt.timedelta(days=21)
    t_end = today - _dt.timedelta(days=14)
    trainings = {}
    trainings["jre"] = _add("Training Exercise", {
        "naming_series": "MIL-TRN-.YYYY.-.####",
        "exercise_name": f"Joint Readiness Exercise 'Eagle Resolve' (DEMO) {TAG}",
        "unit": units["bde22"],
        "training_type": "Joint Exercise",
        "assessment": "Satisfactory",
        "start_date": t_start,
        "end_date": t_end,
        "duration_days": (t_end - t_start).days,
        "participant_count": 950,
        "lead_trainer": "Col. Saad al-Moussawi (demo)",
        "location": f"Taji range complex {TAG}",
        "notes": f"{TAG} Brigade-level live-fire exercise; demo data.",
        "primary_source": sources["mod"],
        "documentation_level": DOC_MINIMAL,
        "authentication_level": AUTH_SINGLE,
        "workflow_state": _workflow_state("Published"),
    }, exercise_name=f"Joint Readiness Exercise 'Eagle Resolve' (DEMO) {TAG}")

    # ------------------------------------------------------------------
    # 11. Mission
    # ------------------------------------------------------------------
    missions = {}
    missions["op_baghdad"] = _add("Mission", {
        "naming_series": "MIL-MIS-.YYYY.-.####",
        "mission_name": f"Operation Baghdad Shield (DEMO) {TAG}",
        "unit": units["div6"],
        "status": "Ongoing",
        "start_date": today - _dt.timedelta(days=180),
        "primary_source": sources["mod"],
        "documentation_level": DOC_MINIMAL,
        "authentication_level": AUTH_SINGLE,
        "workflow_state": _workflow_state("Verified"),
        "notes": f"{TAG} Combined Baghdad-belts operation; 22nd Bde is the committed element.",
    }, mission_name=f"Operation Baghdad Shield (DEMO) {TAG}")

    # ------------------------------------------------------------------
    # 12. Research Events
    # ------------------------------------------------------------------
    events = {}
    events["announce"] = _add("Research Event", {
        "naming_series": "EVT-.####",
        "title_en": f"Announcement of Baghdad Shield operation (DEMO) {TAG}",
        "title_ar": f"إعلان عملية درع بغداد (تجريبي) {TAG}",
        "event_type": PTYPE_CONF,
        "start_date": _dt.datetime(today.year, max(today.month - 5, 1), max(today.day, 1), 10, 0),
        "start_date_precision": "day",
        "place": places["mod_hq"],
        "description": f"{TAG} Press conference launching the operation.",
        "significance": f"{TAG} Public beginning of the operational cycle documented in this dataset.",
        "primary_source": sources["mod"],
        "documentation_level": DOC_PARTIAL,
        "authentication_level": AUTH_CORROB,
        "workflow_state": _workflow_state("Published"),
    }, title_en=f"Announcement of Baghdad Shield operation (DEMO) {TAG}")

    events["jre_end"] = _add("Research Event", {
        "naming_series": "EVT-.####",
        "title_en": f"Conclusion of Eagle Resolve exercise (DEMO) {TAG}",
        "title_ar": f"اختتام مناورة عزم النسر (تجريبي) {TAG}",
        "event_type": PTYPE_OTHER,
        "start_date": _dt.datetime.combine(t_end, _dt.time(12, 0)),
        "start_date_precision": "day",
        "end_date": _dt.datetime.combine(t_end, _dt.time(18, 0)),
        "end_date_precision": "day",
        "place": places["taji_camp"],
        "description": f"{TAG} Closing / DV day of the brigade exercise.",
        "primary_source": sources["mod"],
        "documentation_level": DOC_MINIMAL,
        "authentication_level": AUTH_SINGLE,
        "workflow_state": _workflow_state("Published"),
    }, title_en=f"Conclusion of Eagle Resolve exercise (DEMO) {TAG}")

    events["founding_college"] = _add("Research Event", {
        "naming_series": "EVT-.####",
        "title_en": f"Founding of First Military College (DEMO) {TAG}",
        "title_ar": f"تأسيس الكلية العسكرية الأولى (تجريبي) {TAG}",
        "event_type": PTYPE_FOUND,
        "start_date": _dt.datetime(1924, 1, 1),
        "start_date_as_stated": "1924",
        "start_date_precision": "year",
        "place": places["mil_college"],
        "description": f"{TAG} Founding date used in demo data.",
        "primary_source": sources["wiki"],
        "documentation_level": DOC_MINIMAL,
        "authentication_level": AUTH_SINGLE,
        "workflow_state": _workflow_state("Published"),
    }, title_en=f"Founding of First Military College (DEMO) {TAG}")

    # ------------------------------------------------------------------
    # 13. Relationships — power the Explorer network view
    # ------------------------------------------------------------------
    rel_count = 0

    def _rel(subj_type, subj, rel_code, obj_type, obj, *, is_current=0, role="", start=None):
        nonlocal rel_count
        rt = _get_first("Relationship Type", code=rel_code)
        if not rt:
            return None
        existing = frappe.db.get_value("Relationship", {
            "subject_type": subj_type, "subject": subj,
            "relationship_type": rt, "object_type": obj_type, "object": obj,
        })
        if existing:
            return existing
        doc = frappe.get_doc({
            "doctype": "Relationship",
            "naming_series": "REL-.####",
            "relationship_type": rt,
            "direction": "Directed" if rel_code not in ("colleague_of", "relative_of") else "Symmetric",
            "is_current": is_current,
            "subject_type": subj_type, "subject": subj,
            "object_type": obj_type, "object": obj,
            "role_as_stated": role or None,
            "start_date": start,
            "workflow_state": _workflow_state("Published"),
            "primary_source": sources["iiss"],
            "documentation_level": DOC_MINIMAL,
            "authentication_level": AUTH_SINGLE,
        })
        doc.insert(ignore_permissions=True)
        rel_count += 1
        return doc.name

    # NOTE: Relationship.subject_type / object_type are restricted Select fields
    # (Person / Institution / Place / Research Event / Source). Connections that
    # involve Military Unit, Training Exercise, Operational Deployment, or Mission
    # are already expressed natively by the Link fields on those DocTypes
    # (commander, parent_unit, deployment.mission, lead_trainer, etc.) and do not
    # need additional Relationship rows.
    _rel("Person", persons["cofs"], "director_of", "Institution", insts["mod"], is_current=1,
         start=_dt.datetime(today.year - 1, today.month, max(today.day, 1)))
    _rel("Institution", insts["mod"], "located_in", "Place", places["mod_hq"])
    _rel("Institution", insts["rust_college"], "located_in", "Place", places["mil_college"])
    _rel("Person", persons["div1"], "affiliated_with", "Institution", insts["mod"], is_current=1)
    _rel("Person", persons["bde1"], "affiliated_with", "Institution", insts["mod"], is_current=1)
    _rel("Person", persons["train"], "affiliated_with", "Institution", insts["rust_college"], is_current=1)
    for p in (persons["div1"], persons["bde1"], persons["train"]):
        _rel("Person", p, "graduated_from", "Institution", insts["rust_college"])
    _rel("Person", persons["cofs"], "employed_by", "Institution", insts["mod"], is_current=1)
    _rel("Research Event", events["announce"], "located_in", "Place", places["mod_hq"])
    _rel("Research Event", events["jre_end"], "located_in", "Place", places["taji_camp"])
    _rel("Research Event", events["founding_college"], "located_in", "Place", places["mil_college"])
    _rel("Research Event", events["announce"], "cites", "Source", sources["mod"])

    frappe.db.commit()

    summary = {
        "places": len(places),
        "sources": len(sources),
        "institutions": len(insts),
        "persons": len(persons),
        "command_regions": len(regions),
        "military_units": len(units),
        "military_divisions": 1,
        "unit_classifications": 1,
        "deployments": len(deploys),
        "training_exercises": len(trainings),
        "missions": len(missions),
        "research_events": len(events),
        "relationships": rel_count,
        "tag": TAG,
    }
    print("SIRAJ DEMO data seeded:")
    for k, v in summary.items():
        print(f"  {k:25s} {v}")
    print("\nTo REMOVE this demo dataset, run:")
    print(f"  bench --site frappe.com execute siraj_research.setup.demo_data.teardown_demo_data")
    return summary


def teardown_demo_data():
    """Remove every DEMO-tagged record. Safe to re-run."""
    removed = 0
    # Delete child-containing documents first so FKs don't block us.
    # Order: leaf records → records that link to them → parents last.
    doctypes_field = {
        "Relationship": "display_name",
        "Operational Deployment": "deployment_name",
        "Training Exercise": "exercise_name",
        "Mission": "mission_name",
        "Research Event": "title_en",
        "Unit Armament Holding": "name",   # child rows (Military Unit will cascade, but be safe)
        "Military Unit": "unit_name",
        "Armament": "armament_name",       # FK from Military Unit.armaments
        "Military Division": "division_name",
        "Person": "name_en",
        "Institution": "name_en",
        "Source": "title",
        "Place": "name_en",
        "Command Region": "region_name",
        "Unit Classification": "classification_name",
    }
    for dt, field in doctypes_field.items():
        try:
            names = frappe.get_all(dt, filters={field: ("like", f"%{TAG}%")}, pluck="name")
        except Exception:
            continue
        for name in names:
            try:
                frappe.delete_doc(dt, name, ignore_permissions=True, force=True)
                removed += 1
            except Exception as e:
                print(f"  ! could not delete {dt} {name}: {e}")
    frappe.db.commit()
    print(f"Removed {removed} DEMO records.")
    return {"removed": removed}
