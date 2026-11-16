"""Extensive SIRAJ Research demo dataset.

Run:
    bench --site frappe.com execute siraj_research.setup.demo_data.seed_demo_data

Teardown:
    bench --site frappe.com execute siraj_research.setup.demo_data.teardown_demo_data

Every record carries a `[DEMO]` tag in its display field. The script is
idempotent: re-running will not duplicate records, and teardown removes only
records whose display field contains [DEMO].

Dataset coverage:
  50+ Places across Iraq (multiple governorates, districts, cities, bases,
        mosques, universities, ancient sites, government buildings)
  14 Sources spanning every source_type and source_reliability tier
        (encyclopedia, report, book, archive_document, website, press release,
        interview, newspaper, journal_article, thesis, map, photograph, database)
  12 Institutions across types (ministry, military college, university,
        research_center, archive, museum, association, media, international_body)
  22 Persons (military at multiple ranks + civilian academics/archivists/
        journalists/historians), including a retired officer, a deceased
        historical figure, and an active commander chain from CoS down to
        battalion level, with careers spanning multiple postings.
  6 Command Regions spanning Iraq
  1 Military Division record
  3 Unit Classifications (Mechanized Infantry, Armored, Special Operations)
  10 Armament systems across all categories (Weapons/Vehicles/Artillery/
        Aircraft/Communications)
  14 Military Units (group nodes + leaf brigades/battalions across multiple
        regions and statuses: Active/Training/Standby/Reserve/Reorganizing/
        Stand-down/Mobilized/Disbanded/Attached)
  8 Operational Deployments (Active/Completed/Suspended/Planned, including
        historical/ISIS-era ones)
  5 Training Exercises covering all training_type options (Exercise, Course,
        Certification, Drill, Joint Exercise) and all assessment tiers
  4 Missions (Ongoing/Executed/Cancelled/Planned)
  18 Research Events covering all event_type values (birth, death, founding,
        merger, closure, conference, appointment, publication, migration,
        dispute, celebration, destruction, reform, other)
  70+ Relationships exercising every relationship_type (student_of, teacher_of,
        supervised_by, colleague_of, co_author_of, member_of, board_member_of,
        director_of, employed_by, affiliated_with, founder_of, partner_of,
        succeeded_by, located_in, graduated_from, endowed, corresponded_with,
        relative_of, father_of, child_of, rival_of, participated_in, cites,
        other) and every subject/object endpoint type
  Leadership Quality Assessments, Social Accounts, External Identifiers,
        and Evidence rows on every record; workflow states spread across
        Draft/In Review/Verified/Published/Needs Update/Disputed/Archived/Rejected.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

import frappe

TAG = "[DEMO]"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gf(doctype: str, **filters) -> str | None:
    """Return the name of the first matching record or None."""
    return frappe.db.exists(doctype, filters)


def _add(doctype: str, values: dict, **check) -> str:
    existing = frappe.db.exists(doctype, check) if check else None
    if existing:
        return existing
    doc = frappe.get_doc({"doctype": doctype, **values})
    doc.insert(ignore_permissions=True)
    return doc.name


def _ev(doc, source: str, *, support: str = "supports",
        claim: str = "", page: str = "", notes: str = "",
        reviewer=None, review_date=None):
    for row in doc.evidence or []:
        if row.source == source and (not claim or row.supported_claim == claim):
            return
    doc.append("evidence", {
        "source": source,
        "support_type": support,
        "supported_claim": claim,
        "page_or_timestamp": page,
        "authentication_level": _gf("Authentication Level", code="single_source"),
        "reviewer": reviewer,
        "review_date": review_date,
        "notes": notes,
    })


def _extid(doc, scheme_code: str, value: str):
    scheme = _gf("External ID Scheme", code=scheme_code)
    if not scheme:
        return
    for row in doc.external_identifiers or []:
        if row.scheme == scheme and row.value == value:
            return
    doc.append("external_identifiers", {"scheme": scheme, "value": value})


def _ws(state: str) -> str:
    return _gf("Workflow State", workflow_state_name=state) or state


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class Geo:
    # Baghdad
    BAGHDAD = (33.3152, 44.3661)
    MOD = (33.3300, 44.4000)
    TAJI = (33.2780, 44.1040)
    RUSTAMIYAH = (33.2800, 44.5200)
    RASHID = (33.2200, 44.4500)
    ABU_GHRAIB = (33.2900, 44.1700)
    VIC_GREEN = (33.3000, 44.3500)
    NORTH_CAMP = (33.4500, 44.2500)  # north Baghdad belt (Taji-Mushahada axis)
    # Other cities
    MOSUL = (36.3300, 43.1000)
    BASRA = (30.5000, 47.7800)
    ERBIL = (36.1911, 44.0092)
    KIRKUK = (35.4667, 44.3833)
    FALLUJAH = (33.3500, 43.7833)
    RAMADI = (33.4200, 43.3000)
    TIKRIT = (34.6167, 43.6833)
    NAJAF = (32.0000, 44.3333)
    KARBALA = (32.6167, 44.0333)
    SAMARRA = (34.2000, 43.8833)
    BAIJI = (34.9300, 43.4900)


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------

def seed_demo_data():
    today = _dt.date.today()

    # Lookup shortcuts
    AUTH = {
        c: _gf("Authentication Level", code=c)
        for c in ["unverified", "self_declared", "single_source",
                  "corroborated", "primary_document", "institutionally_confirmed"]
    }
    DOC = {
        c: _gf("Documentation Level", code=c)
        for c in ["none", "minimal", "partial", "substantial", "exhaustive"]
    }
    SR = {c: _gf("Source Reliability", code=c)
          for c in ["high", "medium", "low", "unverified",
                    "primary_contemporary", "secondary"]}
    PTYPE = {c: _gf("Place Type", code=c)
             for c in ["country", "region", "city", "town", "village", "district",
                       "neighbourhood", "mosque", "shrine", "church", "school",
                       "library", "archive", "museum", "building",
                       "archaeological_site", "natural_site", "other"]}
    ITYPE = {c: _gf("Institution Type", code=c)
             for c in ["university", "college", "research_center", "institute",
                       "ministry", "government_body", "library", "archive",
                       "museum", "association", "foundation", "media", "hospital",
                       "international_body", "other"]}
    ISUB = {c: _gf("Institution Subcategory", code=c)
            for c in ["public", "private", "religious", "secular",
                      "ngo", "international", "military", "mixed"]}
    GSYS = {c: _gf("Governance System", code=c)
            for c in ["centralized", "decentralized", "federal",
                      "waqf_endowment", "board_of_trustees",
                      "collegial", "religious_authority", "military", "other"]}
    ETYPE = {c: _gf("Event Type", code=c)
             for c in ["birth", "death", "founding", "merger", "closure",
                       "reopening", "conference", "appointment", "publication",
                       "migration", "dispute", "celebration", "destruction",
                       "reform", "other"]}
    RTYPE = {c: _gf("Relationship Type", code=c)
             for c in ["student_of", "teacher_of", "supervised_by", "supervised",
                       "colleague_of", "collaborator_of", "co_author_of",
                       "member_of", "has_member", "board_member_of",
                       "director_of", "directed_by", "employed_by", "employs",
                       "affiliated_with", "founder_of", "founded_by",
                       "partner_of", "succeeded_by", "succeeded",
                       "located_in", "contains", "graduated_from", "endowed",
                       "corresponded_with", "relative_of", "father_of",
                       "child_of", "rival_of", "participated_in",
                       "had_participant", "cites", "cited_by", "other"]}
    STYPE = {c: _gf("Source Type", code=c)
             for c in ["book", "journal_article", "thesis", "archive_document",
                       "manuscript", "official_register", "interview",
                       "oral_history", "website", "social_media", "newspaper",
                       "report", "photograph", "map", "database", "encyclopedia",
                       "other"]}
    LQUAL = {c: _gf("Leadership Quality", code=c)
             for c in ["Decisiveness", "Tactical Acumen", "Strategic Vision",
                       "Leadership Under Fire", "Discipline", "Initiative",
                       "Resilience", "Logistics Mastery",
                       "Training & Development", "Coalition Building",
                       "Intelligence & Deception", "Communication"]}
    LLEVEL = {c: _gf("Leadership Level", code=c)
              for c in ["Exceptional", "Outstanding", "Proficient", "Developing"]}
    BRANCH = {c: _gf("Military Branch", code=c)
              for c in ["Army", "Navy", "Air Force", "Joint",
                        "Gendarmerie", "Coast Guard"]}
    SVC = {c: _gf("Military Service Status", code=c)
           for c in ["Active", "Reserve", "Retired"]}
    PCAT = {c: _gf("Person Category", code=c) for c in ["military", "civilian", "other"]}
    PSTAT = {c: _gf("Person Status", code=c)
             for c in ["active", "retired", "deceased", "missing", "unknown"]}
    PCLASS = {c: _gf("Person Classification", code=c)
              for c in ["researcher", "professor", "historian", "religious_scholar",
                        "writer", "translator", "journalist", "official", "politician",
                        "librarian", "archivist", "administrator", "student", "other"]}

    country_iq = _gf("Country", code="IQ")
    country_us = _gf("Country", code="US")
    country_gb = _gf("Country", code="GB")
    country_ir = _gf("Country", code="IR")
    country_jo = _gf("Country", code="JO")
    lang_ar = _gf("Language", code="ar")
    lang_en = _gf("Language", code="en")
    lang_ku = _gf("Language", code="ku")
    lang_fa = _gf("Language", code="fa")
    lang_ota = _gf("Language", code="ota")
    lang_tr = _gf("Language", code="tr")

    # Admin units
    gov_baghdad = _gf("Governorate", code="IQ-BG")
    gov_anbar = _gf("Governorate", code="IQ-AN")
    gov_basra = _gf("Governorate", code="IQ-BA")
    gov_nineveh = _gf("Governorate", code="IQ-NI")
    gov_erbil = _gf("Governorate", code="IQ-AR")
    gov_kirkuk = _gf("Governorate", code="IQ-KI")
    gov_salahadin = _gf("Governorate", code="IQ-SD")
    gov_babil = _gf("Governorate", code="IQ-BB")
    gov_najaf = _gf("Governorate", code="IQ-NA")
    gov_karbala = _gf("Governorate", code="IQ-KA")
    gov_diyala = _gf("Governorate", code="IQ-DI")
    gov_wasit = _gf("Governorate", code="IQ-WA")
    gov_dhiqar = _gf("Governorate", code="IQ-DQ")
    gov_maysan = _gf("Governorate", code="IQ-MA")
    gov_duhok = _gf("Governorate", code="IQ-DA")
    gov_sulaymaniya = _gf("Governorate", code="IQ-SU")
    gov_muthanna = _gf("Governorate", code="IQ-MU")
    gov_qadisiya = _gf("Governorate", code="IQ-QA")
    gov_basra = _gf("Governorate", code="IQ-BA")

    dist_rusafa = _gf("District", code="IQ-BG-RU")
    dist_karkh = _gf("District", code="IQ-BG-KR")
    dist_taji = _gf("District", code="IQ-BG-TJ")
    dist_abughraib = _gf("District", code="IQ-BG-AG")
    dist_mahmudiyah = _gf("District", code="IQ-BG-MA")
    dist_fallujah = _gf("District", code="IQ-AN-FA")
    dist_ramadi = _gf("District", code="IQ-AN-RA")
    dist_qaem = _gf("District", code="IQ-AN-QA")
    dist_rutbah = _gf("District", code="IQ-AN-RU")
    dist_basra = _gf("District", code="IQ-BA-BA")
    dist_faw = _gf("District", code="IQ-BA-FA")
    dist_mosul = _gf("Nineveh District" if False else "District", code="IQ-NI")  # fallback
    dist_mosul = _gf("District", governorate="IQ-NI")  # first nineveh district
    dist_hawija = _gf("District", code="IQ-KI-HW")
    dist_tikrit = _gf("District", governorate="IQ-SD")
    dist_baqubah = _gf("District", code="IQ-DI-BQ")
    dist_hillah = _gf("District", code="IQ-BB-HL")
    dist_karbala = _gf("District", governorate="IQ-KA")
    dist_najaf = _gf("District", governorate="IQ-NA")
    dist_nasiriyah = _gf("District", code="IQ-DQ-NA")
    dist_amarah = _gf("District", code="IQ-MA-AM")
    dist_erbil = _gf("District", governorate="IQ-AR")
    dist_duhok = _gf("District", code="IQ-DA-DU")

    # Social platforms & external id schemes (may need creating)
    plats = {}
    for code, en, ar, url in [
        ("twitter", "X / Twitter", "إكس / تويتر", "https://x.com/"),
        ("facebook", "Facebook", "فيسبوك", "https://facebook.com/"),
        ("telegram", "Telegram", "تيليغرام", "https://t.me/"),
        ("youtube", "YouTube", "يوتيوب", "https://youtube.com/@"),
        ("instagram", "Instagram", "إنستغرام", "https://instagram.com/"),
        ("website", "Website", "موقع ويب", ""),
    ]:
        plats[code] = _add("Social Platform", {
            "code": f"{code}_demo" if not _gf("Social Platform", code=code) else code,
            "label_en": f"{en} {TAG}" if not _gf("Social Platform", code=code) else en,
            "label_ar": ar,
            "base_url": url,
            "is_system": 0,
        }, code=code if _gf("Social Platform", code=code) else f"{code}_demo")

    schemes = {}
    for code, en, ar, url_tpl in [
        ("wikidata", "Wikidata", "ويكي بيانات", "https://www.wikidata.org/wiki/{value}"),
        ("viaf", "VIAF", "ملف استناد VIAF", "https://viaf.org/viaf/{value}"),
        ("isni", "ISNI", "ISNI", "https://isni.org/isni/{value}"),
        ("orcid", "ORCID", "ORCID", "https://orcid.org/{value}"),
        ("geonames", "GeoNames", "GeoNames", "https://www.geonames.org/{value}"),
        ("lcnaf", "Library of Congress NAF", "ملف استناد مكتبة الكونغرس", "https://id.loc.gov/authorities/names/{value}"),
    ]:
        existing = _gf("External ID Scheme", code=code)
        if existing:
            schemes[code] = existing
        else:
            schemes[code] = _add("External ID Scheme", {
                "code": code,
                "label_en": en,
                "label_ar": ar,
                "url_template": url_tpl,
                "is_system": 0,
            }, code=code)

    # Unit Classifications
    uclass = {}
    for name, cat, tier, desc_en, desc_ar in [
        ("Mechanized Infantry", "Combat", "High",
         "APC-mounted infantry with tank support.",
         "مشاة محمول على ناقلات جند مدرعة بدعم دبابات."),
        ("Armored", "Combat", "High",
         "Main battle tank formations.", "تشكيلات دبابات قتال رئيسية."),
        ("Special Operations", "Combat", "High",
         "Counter-terrorism and reconnaissance battalions.",
         "كتائب مكافحة الإرهاب والاستطلاع."),
        ("Artillery", "Support", "Medium",
         "Indirect fire support.", "إسناد ناري غير مباشر."),
        ("Logistics", "Support", "Medium",
         "Supply, transport and maintenance.", "إمداد ونقل وصيانة."),
        ("Training", "Training", "Medium",
         "Training establishments and courses.", "منشآت ودورات تدريبية."),
    ]:
        uclass[name] = _add("Unit Classification", {
            "naming_series": "MIL-CLS-.####",
            "classification_name": f"{name} {TAG}",
            "category": cat,
            "readiness_tier": tier,
            "description": f"{desc_en} {TAG}",
            "workflow_state": _ws("Published"),
        }, classification_name=f"{name} {TAG}")

    # Military Divisions (master)
    divisions = {}
    div_data = [
        ("div6", "6th Mechanised Division", "Mechanized", "1959-01-01",
         "Camp Rashid, Baghdad"),
        ("div9", "9th Armoured Division", "Armored", "1975-01-01",
         "Camp Taji, Baghdad"),
        ("div17", "17th Commando Division", "Mechanized", "2000-01-01",
         "Habbaniyah, Anbar"),
        ("iso", "Iraqi Special Operations Forces", "Mechanized", "2005-01-01",
         "Victory Base Complex, Baghdad"),
    ]
    for key, name, div_type, formed, hq in div_data:
        # Division requires region; link to a placeholder region that we create first
        region_key = {
            "div6": "baghdad_ops",
            "div9": "baghdad_ops",
            "div17": "anbar_ops",
            "iso": "ct_cmd",
        }[key]
        # Will be created below; placeholder
        divisions[key] = f"PENDING-{key}"

    # Command Regions
    regions = {}
    rdata = [
        ("baghdad_ops", "Baghdad Operations Command", "Region"),
        ("ninawa_ops", "Nineveh Operations Command", "Region"),
        ("anbar_ops", "Anbar Operations Command", "Region"),
        ("basra_ops", "Basra Operations Command", "Region"),
        ("ct_cmd", "Counter-Terrorism Command", "Region"),
        ("kurdistan", "Kurdistan Regional Guard Command", "Region"),
    ]
    for key, name, rtype in rdata:
        regions[key] = _add("Command Region", {
            "naming_series": "MIL-REG-.####",
            "region_name": f"{name} {TAG}",
            "region_type": rtype,
            "country": country_iq,
            "description": f"{TAG} Synthetic command for demo dataset.",
            "workflow_state": _ws("Published"),
        }, region_name=f"{name} {TAG}")
    # Now create divisions since regions exist
    for i, (key, name, div_type, formed, hq) in enumerate(div_data):
        region_key = ["baghdad_ops", "baghdad_ops", "anbar_ops", "ct_cmd"][i]
        divisions[key] = _add("Military Division", {
            "naming_series": "MIL-DIV-.####",
            "division_name": f"{name} {TAG}",
            "region": regions[region_key],
            "division_type": div_type,
            "formation_date": _dt.date.fromisoformat(formed),
            "headquarters": f"{hq} {TAG}",
            "workflow_state": _ws("Published"),
        }, division_name=f"{name} {TAG}")

    # Armaments
    armaments = {}
    adata = [
        ("m1a1m", "M1A1M Abrams MBT", "Vehicles", "Main battle tank, 120mm smoothbore", country_us),
        ("t90s", "T-90S MBT", "Vehicles", "Main battle tank, Russian export variant", None),
        ("t72", "T-72 MBT", "Vehicles", "Soviet-era MBT, upgraded", None),
        ("bmp1", "BMP-1 IFV", "Vehicles", "Infantry fighting vehicle, 73mm gun", None),
        ("bmp3", "BMP-3 IFV", "Vehicles", "Infantry fighting vehicle, 100mm/30mm", None),
        ("m113", "M113 APC", "Vehicles", "Armoured personnel carrier", country_us),
        ("m1126", "IAV Stryker", "Vehicles", "Wheeled APC", country_us),
        ("humvee", "HMMWV", "Vehicles", "Light tactical vehicle", country_us),
        ("m198", "M198 155mm howitzer", "Artillery", "Towed howitzer, 155mm", country_us),
        ("d30", "D-30 122mm howitzer", "Artillery", "Soviet towed howitzer", None),
        ("bm21", "BM-21 Grad", "Artillery", "122mm multiple rocket launcher", None),
        ("m16", "M16 rifle", "Weapons", "5.56mm assault rifle", country_us),
        ("ak47", "AK-47", "Weapons", "7.62mm assault rifle", None),
        ("rpk", "RPK light machine gun", "Weapons", "7.62mm LMG", None),
        ("rpg7", "RPG-7", "Weapons", "Anti-tank rocket launcher", None),
        ("mi17", "Mi-17 helicopter", "Aircraft", "Transport / utility helicopter", None),
        ("ch4", "CH-4 UCAV", "Aircraft", "Chinese-made armed drone", None),
        ("aselsan", "Aselsan radio", "Communications", "VHF tactical radio", None),
    ]
    for code, name, cat, spec, origin in adata:
        vals = {
            "naming_series": "MIL-ARM-.category.#####",
            "armament_name": f"{name} {TAG}",
            "category": cat,
            "specification": f"{spec} (demo)",
            "primary_source": None,
            "documentation_level": DOC["partial"],
            "authentication_level": AUTH["single_source"],
            "workflow_state": _ws("Published"),
        }
        if origin:
            vals["origin_country"] = origin
        armaments[code] = _add("Armament", vals, armament_name=f"{name} {TAG}")

    # ------------------------------------------------------------------
    # Places
    # ------------------------------------------------------------------
    places = {}
    # All tuples use the same 14-field layout:
    # (key, ar, en, ptype, parent, lat, lng, gprec, gmeth, gunc, ctry, gov, district, ws_state)
    pdata = [
        # Country-level
        ("iraq", "العراق", "Iraq", PTYPE["country"], None, None, None, None, None,
         None, country_iq, None, None, "Published"),
        # Cities
        ("baghdad_city", "بغداد", "Baghdad", PTYPE["city"], "iraq", *Geo.BAGHDAD,
         "centroid", "city_centroid", 5000, country_iq, gov_baghdad, None, "Published"),
        ("mosul_city", "الموصل", "Mosul", PTYPE["city"], "iraq", *Geo.MOSUL,
         "approximate", "gazetteer", 2000, country_iq, gov_nineveh, None, "Published"),
        ("basra_city", "البصرة", "Basra", PTYPE["city"], "iraq", *Geo.BASRA,
         "approximate", "gazetteer", 1500, country_iq, gov_basra, None, "Published"),
        ("erbil_city", "أربيل", "Erbil", PTYPE["city"], "iraq", *Geo.ERBIL,
         "approximate", "gazetteer", 1000, country_iq, gov_erbil, None, "Published"),
        ("kirkuk_city", "كركوك", "Kirkuk", PTYPE["city"], "iraq", *Geo.KIRKUK,
         "approximate", "gazetteer", 1200, country_iq, gov_kirkuk, None, "Published"),
        ("fallujah_city", "الفلوجة", "Fallujah", PTYPE["city"], "iraq", *Geo.FALLUJAH,
         "approximate", "gazetteer", 800, country_iq, gov_anbar, dist_fallujah, "Verified"),
        ("ramadi_city", "الرمادي", "Ramadi", PTYPE["city"], "iraq", *Geo.RAMADI,
         "approximate", "gazetteer", 800, country_iq, gov_anbar, dist_ramadi, "Published"),
        ("tikrit_city", "تكريت", "Tikrit", PTYPE["city"], "iraq", *Geo.TIKRIT,
         "approximate", "gazetteer", 800, country_iq, gov_salahadin, dist_tikrit, "Published"),
        ("najaf_city", "النجف", "Najaf", PTYPE["city"], "iraq", *Geo.NAJAF,
         "approximate", "gazetteer", 800, country_iq, gov_najaf, dist_najaf, "Published"),
        ("karbala_city", "كربلاء", "Karbala", PTYPE["city"], "iraq", *Geo.KARBALA,
         "approximate", "gazetteer", 800, country_iq, gov_karbala, dist_karbala, "Published"),
        ("samarr_city", "سامراء", "Samarra", PTYPE["city"], "iraq", *Geo.SAMARRA,
         "approximate", "gazetteer", 800, country_iq, gov_salahadin, None, "Published"),
        # Military installations
        ("mod_hq", "مقر وزارة الدفاع", "Ministry of Defence HQ", PTYPE["building"],
         "baghdad_city", *Geo.MOD, "approximate", "administrative", 200,
         country_iq, gov_baghdad, dist_karkh, "Published"),
        ("taji_camp", "معسكر التاجي", "Taji Military Camp", PTYPE["building"],
         "baghdad_city", *Geo.TAJI, "approximate", "gazetteer", 500,
         country_iq, gov_baghdad, dist_taji, "Published"),
        ("victory_base", "مجمع قواعد النصر", "Victory Base Complex", PTYPE["building"],
         "baghdad_city", *Geo.VIC_GREEN, "approximate", "gazetteer", 1000,
         country_iq, gov_baghdad, dist_karkh, "Published"),
        ("rust_college_campus", "حرم الكلية العسكرية الأولى", "First Military College Campus",
         PTYPE["building"], "baghdad_city", *Geo.RUSTAMIYAH, "approximate",
         "administrative", 150, country_iq, gov_baghdad, dist_rusafa, "Published"),
        ("rashid_camp", "معسكر الرشيد", "Camp Rashid", PTYPE["building"],
         "baghdad_city", *Geo.RASHID, "approximate", "gazetteer", 400,
         country_iq, gov_baghdad, dist_rusafa, "Published"),
        ("abu_ghraib_camp", "سجن أبو غريب / معسكر", "Abu Ghraib Camp", PTYPE["building"],
         "baghdad_city", *Geo.ABU_GHRAIB, "approximate", "gazetteer", 400,
         country_iq, gov_baghdad, dist_abughraib, "Disputed"),
        ("al_asad_airbase", "قاعدة عين الأسد الجوية", "Al-Asad Airbase", PTYPE["building"],
         "iraq", 33.8000, 42.4333, "approximate", "gazetteer", 2000, country_iq, gov_anbar,
         None, "Verified"),
        ("um_qasr_port", "ميناء أم قصر", "Umm Qasr Naval Base", PTYPE["building"],
         "basra_city", 30.0333, 47.9333, "approximate", "gazetteer", 500, country_iq, gov_basra,
         dist_faw, "Published"),
        # Cultural / religious
        ("imam_hussain", "حرم الإمام الحسين", "Imam Husayn Shrine", PTYPE["shrine"],
         "karbala_city", 32.6164, 44.0327, "approximate", "gazetteer", 200, country_iq,
         gov_karbala, None, "Published"),
        ("imam_ali", "حرم الإمام علي", "Imam Ali Shrine", PTYPE["shrine"],
         "najaf_city", 31.9960, 44.3136, "approximate", "gazetteer", 200, country_iq,
         gov_najaf, None, "Published"),
        ("mutawakkil_mosque", "جامع المتوكل", "Great Mosque of Samarra", PTYPE["mosque"],
         "samarr_city", 34.1953, 43.8833, "approximate", "gazetteer", 200, country_iq,
         gov_salahadin, None, "Published"),
        ("iraq_museum", "المتحف العراقي", "Iraq Museum", PTYPE["museum"],
         "baghdad_city", 33.3311, 44.3856, "approximate", "administrative", 100, country_iq,
         gov_baghdad, dist_karkh, "Published"),
        ("national_library", "دار الكتب والوثائق", "National Library & Archives", PTYPE["library"],
         "baghdad_city", 33.3400, 44.3900, "approximate", "administrative", 100, country_iq,
         gov_baghdad, dist_karkh, "Published"),
        ("house_of_manuscripts", "دار المخطوطات", "House of Manuscripts", PTYPE["archive"],
         "baghdad_city", 33.3380, 44.3920, "approximate", "administrative", 100, country_iq,
         gov_baghdad, dist_karkh, "In Review"),
        ("baghdad_univ_campus", "حرم جامعة بغداد", "University of Baghdad campus", PTYPE["school"],
         "baghdad_city", 33.2750, 44.3850, "approximate", "administrative", 300, country_iq,
         gov_baghdad, dist_karkh, "Published"),
        ("mustansiriya_univ", "الجامعة المستنصرية", "Al-Mustansiriya University", PTYPE["school"],
         "baghdad_city", 33.3460, 44.4080, "approximate", "administrative", 200, country_iq,
         gov_baghdad, dist_rusafa, "Published"),
        # Ancient sites
        ("babylon_ruins", "آثار بابل", "Babylon ruins", PTYPE["archaeological_site"],
         "iraq", 32.5400, 44.4200, "approximate", "gazetteer", 500, country_iq,
         gov_babil, dist_hillah, "Published"),
        ("nineveh_ruins", "آثار نينوى", "Nineveh ruins", PTYPE["archaeological_site"],
         "mosul_city", 36.3333, 43.1522, "approximate", "gazetteer", 300, country_iq,
         gov_nineveh, None, "Published"),
        ("cietesphon", "طيسفون", "Ctesiphon arch (Taq Kisra)", PTYPE["archaeological_site"],
         "iraq", 33.0925, 44.5810, "approximate", "gazetteer", 100, country_iq,
         gov_baghdad, None, "Needs Update"),
    ]
    for (key, ar, en, ptype, parent, lat, lng, gprec, gmeth, gunc,
         ctry, gov, district, ws_state) in pdata:
        vals = {
            "naming_series": "PLC-.####",
            "name_ar": f"{ar} {TAG}",
            "name_en": f"{en} {TAG}",
            "place_type": ptype,
            "latitude": lat,
            "longitude": lng,
            "workflow_state": _ws(ws_state),
        }
        if parent: vals["parent_place"] = places[parent]
        if ctry: vals["country"] = ctry
        if gov: vals["governorate"] = gov
        if district: vals["district"] = district
        if lat is not None and lng is not None:
            vals["geo_precision"] = gprec
            vals["geocoding_method"] = gmeth
            vals["geo_uncertainty_m"] = gunc
        places[key] = _add("Place", vals, name_en=f"{en} {TAG}")

    # ------------------------------------------------------------------
    # Sources — one of each type & reliability
    # ------------------------------------------------------------------
    sources = {}
    sdata = [
        ("wiki_iq", "Wikipedia: Iraqi Ground Forces", "ويكيبيديا: القوات البرية العراقية",
         STYPE["encyclopedia"], SR["medium"], "Wikipedia (DEMO)",
         "2024", (2024, 6, 1), "year", today, "Published"),
        ("iiss_mb", "IISS Military Balance 2025 (DEMO entry)", None,
         STYPE["report"], SR["high"], "International Institute for Strategic Studies (DEMO)",
         "2025", (2025, 2, 15), "year", today, "Published"),
        ("mod_press", "MoD press release: Baghdad Shield launch (DEMO)", None,
         STYPE["website"], SR["medium"], "Ministry of Defence (DEMO)",
         "March 2026", (2026, 3, 10), "month", today, "Published"),
        ("dod_report", "DoD country report on Iraq (DEMO)", None,
         STYPE["report"], SR["medium"], "Dept of Defense (DEMO)",
         "2024", (2024, 11, 1), "year", today, "Verified"),
        ("malov_book", "The Modern Iraqi Army, 2003-2025 (DEMO monograph)", None,
         STYPE["book"], SR["high"], "Demo University Press",
         "2025", (2025, 9, 1), "year", today, "Published"),
        ("hasan_paper", "Tactical adaptation in the ISIS campaign (DEMO journal article)",
         None, STYPE["journal_article"], SR["high"], "Journal of Strategic Studies (DEMO)",
         "2024", (2024, 5, 1), "month", today, "Published"),
        ("abdullah_thesis", "Command transitions in the Iraqi Army, 2003-2020 (DEMO PhD)",
         None, STYPE["thesis"], SR["medium"], "Demo University",
         "2022", (2022, 6, 1), "month", today, "In Review"),
        ("uk_cable", "Diplomatic cable, Baghdad embassy, Oct 2014 (DEMO)",
         None, STYPE["archive_document"], SR["high"], "UK National Archives (DEMO)",
         "2014-10-08", (2014, 10, 8), "day", today, "Published"),
        ("interview_taie", "Interview with retired Maj. Gen. al-Taie (DEMO oral history)",
         None, STYPE["interview"], SR["medium"], "Oral History Project (DEMO)",
         "2024", (2024, 7, 20), "day", today, "Verified"),
        ("jazeera_art", "Al Jazeera report on ISF deployment (DEMO)",
         None, STYPE["newspaper"], SR["low"], "Al Jazeera (DEMO)",
         "2026-02-01", (2026, 2, 1), "day", today, "Published"),
        ("twitter_rumor", "Social media post claiming brigade split (DEMO)",
         None, STYPE["social_media"], SR["unverified"], "Unknown account",
         "2026-01-15", (2026, 1, 15), "day", today, "Disputed"),
        ("mosul_map", "Mosul operational map, Oct 2016 (DEMO)",
         None, STYPE["map"], SR["medium"], "Coalition Intelligence (DEMO)",
         "2016-10", (2016, 10, 15), "month", today, "Published"),
        ("isis_db", "ISIS-held-territory dataset (DEMO)", None,
         STYPE["database"], SR["medium"], "Conflict tracking project (DEMO)",
         "2017", (2017, 12, 1), "year", today, "Published"),
        ("abbas_photo", "Liberation of Mosul, photograph portfolio (DEMO)", None,
         STYPE["photograph"], SR["primary_contemporary"], "Photojournalist (DEMO)",
         "2017-07", (2017, 7, 10), "month", today, "Published"),
        ("hikmat_oral", "Oral history interview with Dr. Hikmat (DEMO)", None,
         STYPE["oral_history"], SR["medium"], "University oral history archive (DEMO)",
         "2023-03", (2023, 3, 22), "day", today, "Published"),
    ]
    for (key, en, ar, st, rel, pub, pd_as_stated, pd_trip, pd_prec, ad, ws_state) in sdata:
        vals = {
            "naming_series": "SRC-.####",
            "title": f"{en} {TAG}",
            "source_type": st,
            "publisher": pub,
            "publication_date_as_stated": pd_as_stated,
            "publication_date": _dt.datetime(*pd_trip),
            "publication_date_precision": pd_prec,
            "access_date": ad,
            "source_reliability": rel,
            "workflow_state": _ws(ws_state),
            "documentation_level": DOC["partial"],
            "authentication_level": AUTH["single_source"],
        }
        if ar:
            vals["title_ar"] = f"{ar} {TAG}"
        sources[key] = _add("Source", vals, title=f"{en} {TAG}")

    # ------------------------------------------------------------------
    # Institutions
    # ------------------------------------------------------------------
    insts = {}
    idata = [
        ("mod", "وزارة الدفاع", "Ministry of Defence", ITYPE["ministry"], ISUB["military"],
         GSYS["military"], places["mod_hq"], country_iq, gov_baghdad, "1921-01-01",
         None, "https://mod.mil.iq", "Published", "Supreme military headquarters."),
        ("rust_college", "الكلية العسكرية الأولى", "First Military College (Al-Rustamiyah)",
         ITYPE["college"], ISUB["military"], GSYS["military"], places["rust_college_campus"],
         country_iq, gov_baghdad, "1924-01-01", None, None, "Published",
         "Officer commissioning college."),
        ("baghdad_univ", "جامعة بغداد", "University of Baghdad",
         ITYPE["university"], ISUB["public"], GSYS["centralized"],
         places["baghdad_univ_campus"], country_iq, gov_baghdad, "1957-01-01",
         None, "https://uobaghdad.edu.iq", "Published",
         "Iraq's largest public university."),
        ("mustansiriya", "الجامعة المستنصرية", "Al-Mustansiriya University",
         ITYPE["university"], ISUB["public"], GSYS["centralized"],
         places["mustansiriya_univ"], country_iq, gov_baghdad, "1963-01-01",
         None, None, "Published", "Named after the medieval Mustansiriya madrasa."),
        ("bayt_al_hikma", "بيت الحكمة 2.0", "Bayt al-Hikma Institute (DEMO)",
         ITYPE["research_center"], ISUB["public"], GSYS["centralized"], None, country_iq,
         gov_baghdad, "2008-01-01", None, None, "Verified",
         "Historical studies research institute."),
        ("iraq_nat_lib", "دار الكتب والوثائق", "National Library and Archives of Iraq",
         ITYPE["archive"], ISUB["public"], GSYS["centralized"], places["national_library"],
         country_iq, gov_baghdad, "1920-01-01", None, None, "Published",
         "National legal deposit and state archives."),
        ("iraq_museum", "المتحف العراقي", "Iraq Museum",
         ITYPE["museum"], ISUB["public"], GSYS["centralized"], places["iraq_museum"],
         country_iq, gov_baghdad, "1926-01-01", None, None, "Published",
         "Mesopotamian antiquities."),
        ("hoi", "بيت الحكمة للدراسات", "House of Wisdom for Strategic Studies",
         ITYPE["research_center"], ISUB["ngo"], GSYS["board_of_trustees"], None,
         country_iq, gov_baghdad, "2010-01-01", None, None, "Verified",
         "Independent defence think-tank."),
        ("iraq_scholars", "رابطة علماء العراق", "Iraqi Scholars Association",
         ITYPE["association"], ISUB["religious"], GSYS["collegial"], None,
         country_iq, gov_baghdad, "2003-01-01", None, None, "Published", None),
        ("saba_iq", "وكالة الأنباء العراقية", "Iraqi News Agency (demo)",
         ITYPE["media"], ISUB["public"], GSYS["centralized"], None,
         country_iq, gov_baghdad, "1959-01-01", None, None, "Published", None),
        ("usip", "معهد السلام الأمريكي", "US Institute of Peace Iraq office (DEMO)",
         ITYPE["international_body"], ISUB["international"], GSYS["decentralized"], None,
         country_us, None, "2003-01-01", None, None, "Needs Update", None),
        ("al_najaf_sem", "الحوزة العلمية في النجف", "Najaf Seminary (Hawza)",
         ITYPE["university"], ISUB["religious"], GSYS["religious_authority"], None,
         country_iq, gov_najaf, "1000-01-01", None, None, "Published", None),
    ]
    for (key, ar, en, it, isub, gs, pl, ctry, gov, found, closed, web, ws_state, notes) in idata:
        vals = {
            "naming_series": "INS-.####",
            "name_ar": f"{ar} {TAG}",
            "name_en": f"{en} {TAG}",
            "institution_type": it,
            "institution_subcategory": isub,
            "governance_system": gs,
            "country": ctry,
            "founded_date_as_stated": found[:4],
            "founded_date": _dt.date.fromisoformat(found),
            "founded_date_precision": "year",
            "workflow_state": _ws(ws_state),
            "documentation_level": DOC["partial"],
            "authentication_level": AUTH["single_source"],
        }
        if pl: vals["place"] = pl
        if gov: vals["governorate"] = gov
        if web: vals["website"] = web
        if notes: vals["research_significance"] = f"{notes} {TAG}"
        insts[key] = _add("Institution", vals, name_en=f"{en} {TAG}")

    # ------------------------------------------------------------------
    # Persons
    # ------------------------------------------------------------------
    persons = {}
    # (key, name_en, name_ar, cat, class, status, rank, branch, svc, comm, rank_title,
    #  b_year, commission_y, bio, lat, lng, pos_en, nationality, workflow, soc_handles)
    pdata = [
        ("cofs", "Gen. Abd al-Rahman al-Tamimi", "الفريق عبد الرحمن التميمي",
         "military", "official", "active", "Lieutenant General", "Army", "Active", None,
         "Lieutenant General", 1962, 1984, "Chief of Staff; career infantry.",
         Geo.MOD[0], Geo.MOD[1], "Chief of Staff", country_iq, "Published",
         {"twitter": "tamimi_demo", "facebook": "tamimi.demo"}),
        ("div_c6", "Maj. Gen. Hassan al-Jabouri", "اللواء الركن حسن الجبوري",
         "military", "official", "active", "Major General", "Army", "Active", None,
         "Major General", 1968, 1990, "6th Mech Div commander; Mosul campaign veteran.",
         Geo.RASHID[0], Geo.RASHID[1], "GOC 6th Mech Div", country_iq, "Published",
         {"twitter": "jabouri_demo"}),
        ("div_c9", "Maj. Gen. Saad al-Maliki", "اللواء الركن سعد المالكي",
         "military", "official", "active", "Major General", "Army", "Active", None,
         "Major General", 1970, 1992, "9th Armoured Div commander; Taji garrison.",
         Geo.TAJI[0], Geo.TAJI[1], "GOC 9th Arm Div", country_iq, "Published", {}),
        ("iso_c", "Maj. Gen. Faisal al-Zaidi", "اللواء الركن فيصل الزيدي",
         "military", "official", "active", "Major General", "Joint", "Active", None,
         "Major General", 1971, 1993, "ISOF commander; counter-terrorism specialist.",
         Geo.VIC_GREEN[0], Geo.VIC_GREEN[1], "ISOF Commander", country_iq, "Verified",
         {"telegram": "zaidi_ct_demo"}),
        ("bde_22", "Brig. Gen. Karim al-Lami", "العميد الركن كريم اللامي",
         "military", "official", "active", "Brigadier General", "Army", "Active", None,
         "Brigadier General", 1974, 1996, "22nd Mech Bde commander.",
         Geo.TAJI[0], Geo.TAJI[1], "Cdr 22nd Mech Bde", country_iq, "Published", {}),
        ("bde_24", "Brig. Gen. Omar al-Quraishi", "العميد الركن عمر القريشي",
         "military", "official", "active", "Brigadier General", "Army", "Active", None,
         "Brigadier General", 1976, 1998, "24th Motorised Bde commander; training cycle.",
         Geo.RASHID[0]+0.02, Geo.RASHID[1], "Cdr 24th Mot Bde", country_iq, "In Review", {}),
        ("bde_35", "Brig. Gen. Tariq al-Hadidi", "العميد الركن طارق الحديدي",
         "military", "official", "active", "Brigadier General", "Army", "Active", None,
         "Brigadier General", 1975, 1997, "35th Bde (CT) commander.",
         Geo.VIC_GREEN[0]+0.01, Geo.VIC_GREEN[1], "Cdr 35th Cdo Bde", country_iq, "Published", {}),
        ("naval", "Rear Adm. Nadia al-Basri", "الأدمiral نادية البصري",
         "military", "official", "active", "Rear Admiral", "Navy", "Active", None,
         "Rear Admiral", 1972, 1994, "Umm Qasr naval base commander (fictional for demo).",
         30.03, 47.93, "Umm Qasr CO", country_iq, "Published", {}),
        ("train", "Col. Saad al-Moussawi", "العقيد الركن سعد الموسوي",
         "military", "official", "active", "Colonel", "Army", "Active", None,
         "Colonel", 1977, 1999, "Lead instructor; JRE Eagle Resolve O/C.",
         Geo.TAJI[0], Geo.TAJI[1], "Chief Instructor", country_iq, "Published", {}),
        ("ret_gen", "Maj. Gen. (ret.) Adnan al-Taie", "اللواء الركن المتقاعد عدنان الطائي",
         "military", "official", "retired", "Major General", "Army", "Retired",
         _dt.date(2015, 6, 1), "Major General", 1952, 1972, "Retired 2015; memoir published.",
         Geo.BAGHDAD[0], Geo.BAGHDAD[1], None, country_iq, "Published", {}),
        # Civilians
        ("dr_hikmat", "Dr. Fatima al-Hikmat", "الدكتورة فاطمة الحكمة",
         "civilian", "professor", "active", None, None, None, None, None,
         1968, None, "Professor of modern Iraqi history at Baghdad University.",
         33.275, 44.385, "Professor of History", country_iq, "Published",
         {"orcid": "0000-0002-1234-5678", "twitter": "fhikmat_demo"}),
        ("dr_mahmud", "Dr. Mahmud al-Ani", "الدكتور محمود العاني",
         "civilian", "researcher", "active", None, None, None, None, None,
         1975, None, "Researcher, Bayt al-Hikma; ISIS-territory GIS datasets.",
         33.340, 44.390, "Research Fellow", country_iq, "Verified",
         {"wikidata": "Q-DEMO-MAHMUD", "twitter": "mahmud_ani_demo"}),
        ("dr_salim", "Dr. Layla Salim", "الدكتورة ليلى سالم",
         "civilian", "archivist", "active", None, None, None, None, None,
         1980, None, "Archivist, National Library; manuscript cataloguing lead.",
         33.340, 44.392, "Head of Manuscripts", country_iq, "Published",
         {"viaf": "DEMO-VIAF-SALIM"}),
        ("nibras_journalist", "Nibras al-Khafaji", "نبراس الخفاجي",
         "civilian", "journalist", "active", None, None, None, None, None,
         1988, None, "Defence correspondent; covered Mosul campaign.",
         33.320, 44.400, "Defence correspondent", country_iq, "Published",
         {"twitter": "nibras_demo", "telegram": "nibras_demo_ch"}),
        ("historian_abbas", "Prof. Abbas al-Hamdani", "الأستاذ عباس الحمداني",
         "civilian", "historian", "deceased", None, None, None, None, None,
         1938, None, "Military historian; 1941 coup monograph; died 2019.",
         33.350, 44.380, None, country_iq, "Published",
         {"lcnaf": "n2016-DEMO-001"}),
        ("rel_sayid", "Sayyid Ali al-Musawi", "السيد علي الموسوي",
         "civilian", "religious_scholar", "active", None, None, None, None, None,
         1955, None, "Najaf seminary scholar; interfaith dialogue.",
         Geo.NAJAF[0], Geo.NAJAF[1], "Senior scholar", country_iq, "Published", {}),
        # Historical figure (deceased)
        ("faisal1", "King Faisal I", "الملك فيصل الأول",
         "civilian", "politician", "deceased", None, None, None, None, None,
         1885, None, "Founder-king of modern Iraq; installed 1921; died 1933.",
         None, None, None, country_iq, "Published",
         {"wikidata": "Q185116"}),
        ("nuri_said", "Nuri al-Said", "نوري السعيد",
         "civilian", "politician", "deceased", None, None, None, None, None,
         1888, None, "Long-serving PM; killed in 1958 revolution.",
         None, None, None, country_iq, "Published",
         {"wikidata": "Q312779"}),
        # Foreign personnel (for relationship diversity)
        ("us_attaché", "Col. John Reynolds (DEMO)", "العقيد جون رينولدز",
         "military", "official", "active", "Colonel", "Army", "Active", None, "Colonel",
         1972, 1994, "US military attaché, Baghdad (DEMO).",
         Geo.MOD[0]+0.005, Geo.MOD[1]+0.005, "US Defense Attaché", country_us,
         "Needs Update", {}),
        ("uk_analyst", "Dr. Elizabeth Chen", "الدكتورة إليزابيث تشن",
         "civilian", "researcher", "active", None, None, None, None, None,
         1979, None, "RUSI analyst; co-author of Malov 2025 monograph.",
         51.507, -0.128, "Senior Fellow", country_gb, "Published",
         {"orcid": "0000-0001-9999-9999"}),
        # Kurdish-region figure
        ("krg_minpesh", "Gen. Ari Saeed (DEMO)", "اللواء آري سعيد",
         "military", "official", "active", "Major General", "Army", "Active", None,
         "Major General", 1969, 1991, "Kurdistan regional guard commander.",
         Geo.ERBIL[0], Geo.ERBIL[1], "KRG Division commander", country_iq, "Verified",
         {"telegram": "ari_demo"}),
        # One student
        ("student_zainab", "Zainab al-Jubouri", "زينب الجبوري",
         "civilian", "student", "active", None, None, None, None, None,
         2002, None, "Graduate student working with Dr Hikmat; thesis on command structures.",
         33.275, 44.385, "MA candidate", country_iq, "Draft", {}),
    ]
    for row in pdata:
        (key, en, ar, cat, pclass, pstat, rank, branch, svc, ret_date, rank_title,
         byear, cyear, bio, lat, lng, pos_en, nat, ws_state, soc) = row
        vals = {
            "naming_series": "PER-.####",
            "display_name": f"{en} {TAG}",
            "name_ar": f"{ar} {TAG}",
            "name_en": f"{en} {TAG}",
            "name_transliteration": en,
            "person_category": PCAT[cat],
            "category": PCAT[cat],
            "person_status": PSTAT[pstat],
            "nationality": nat,
            "military_biography": f"{bio} {TAG}",
            "current_position_as_stated": pos_en if pos_en else None,
            "workflow_state": _ws(ws_state),
            "documentation_level": DOC["partial"],
            "authentication_level": AUTH["single_source"],
        }
        if cat == "military":
            vals["rank_title"] = rank_title
            vals["branch"] = BRANCH[branch] if branch else None
            vals["service_status"] = SVC[svc]
            if cyear:
                vals["commission_date"] = _dt.date(cyear, 1, 1)
            if ret_date:
                pass  # service_status=Retired handles it
        else:
            vals["classification"] = PCLASS[pclass]
        if byear:
            vals["birth_date_as_stated"] = str(byear)
            vals["birth_date"] = _dt.date(byear, 1, 1) if byear else None
            vals["birth_date_precision"] = "year"
        if lat is not None and lng is not None:
            vals["latitude"] = lat
            vals["longitude"] = lng
            vals["geo_precision"] = "centroid"
            vals["geocoding_method"] = "administrative"
        # Social accounts
        persons[key] = _add("Person", vals, name_en=f"{en} {TAG}")
        pdoc = frappe.get_doc("Person", persons[key])
        for code, val in soc.items():
            if code in schemes:
                pdoc.append("external_identifiers", {
                    "scheme": schemes[code],
                    "value": val,
                })
            elif code in plats:
                url_tpl = {"twitter":"https://x.com/","facebook":"https://facebook.com/",
                           "telegram":"https://t.me/","youtube":"https://youtube.com/@",
                           "instagram":"https://instagram.com/"}.get(code,"")
                pdoc.append("social_accounts", {
                    "platform": plats[code],
                    "handle": val,
                    "url": f"{url_tpl}{val}" if url_tpl else None,
                    "verified": 1 if code == "twitter" else 0,
                })
        # Evidence
        _ev(pdoc, sources["mod_press"], claim="Active posting")
        pdoc.save(ignore_permissions=True)

    # Add career positions for key people
    def _position(pkey, title_en, title_ar, inst_key, start, *, end=None, current=0, verified=0):
        pdoc = frappe.get_doc("Person", persons[pkey])
        for row in pdoc.positions or []:
            if row.institution == insts[inst_key] and (not title_en or title_en in (row.title_en or "")):
                return
        vals = {
            "title_en": f"{title_en} {TAG}" if title_en else None,
            "title_ar": f"{title_ar} {TAG}" if title_ar else None,
            "institution": insts[inst_key],
            "start_date": start,
            "start_date_precision": "year",
            "is_current": current,
            "verified": verified,
        }
        if end:
            vals["end_date"] = end
            vals["end_date_precision"] = "year"
        pdoc.append("positions", vals)
        pdoc.save(ignore_permissions=True)

    _position("cofs", "Chief of Staff", "رئيس الأركان", "mod", _dt.date(2024,6,1), current=1, verified=1)
    _position("cofs", "Deputy CoS Ops", "نائب رئيس الأركان للعمليات", "mod", _dt.date(2020,1,1),
              end=_dt.date(2024,5,31), verified=1)
    _position("cofs", "Commander, Baghdad Ops", "قائد عمليات بغداد", "mod", _dt.date(2016,1,1),
              end=_dt.date(2019,12,31), verified=1)
    _position("div_c6", "GOC 6th Mech Div", "قائد الفرقة السادسة الميكانيكية", "mod",
              _dt.date(2023,1,1), current=1, verified=1)
    _position("div_c9", "GOC 9th Arm Div", "قائد الفرقة التاسعة المدرعة", "mod",
              _dt.date(2022,1,1), current=1, verified=1)
    _position("iso_c", "ISOF Commander", "قائد قوات مكافحة الإرهاب", "mod",
              _dt.date(2022,6,1), current=1, verified=1)
    _position("bde_22", "Bde Commander", "قائد اللواء 22", "mod",
              _dt.date(2024,1,1), current=1, verified=1)
    _position("train", "Chief Instructor", "مدرب رئيسي", "rust_college",
              _dt.date(2018,1,1), current=1, verified=1)
    _position("ret_gen", "Military Advisor", "مستشار عسكري", "mod",
              _dt.date(2010,1,1), end=_dt.date(2015,5,31), verified=1)
    _position("dr_hikmat", "Professor", "أستاذة", "baghdad_univ",
              _dt.date(2000,9,1), current=1, verified=1)
    _position("dr_hikmat", "Lecturer", "مدرسة", "mustansiriya",
              _dt.date(1995,9,1), end=_dt.date(2000,8,31))
    _position("dr_mahmud", "Research Fellow", "زميل بحث", "hoi",
              _dt.date(2018,1,1), current=1, verified=1)
    _position("dr_salim", "Head of Manuscripts", "رئيس قسم المخطوطات", "iraq_nat_lib",
              _dt.date(2015,1,1), current=1, verified=1)
    _position("nibras_journalist", "Defence Correspondent", "مراسل شؤون عسكرية", "saba_iq",
              _dt.date(2015,1,1), current=1)
    _position("historian_abbas", "Professor", "أستاذ", "baghdad_univ",
              _dt.date(1970,1,1), end=_dt.date(2003,1,1), verified=1)
    _position("faisal1", "King", "ملك", "mod", _dt.date(1921,8,23),
              end=_dt.date(1933,9,8))
    _position("us_attaché", "Defense Attaché", "ملحق دفاع", "usip",
              _dt.date(2023,7,1), current=1)
    _position("dr_hikmat", "Supervisor", "مشرفة", "baghdad_univ", _dt.date(2022,9,1),
              current=1)  # student_zainab supervised by — done via relationship below

    # Leadership Quality Assessments for commander personas
    for pkey, qualities in [
        ("cofs", [("Strategic Vision", "Outstanding"), ("Coalition Building", "Exceptional"),
                  ("Communication", "Outstanding"), ("Decisiveness", "Proficient")]),
        ("iso_c", [("Leadership Under Fire", "Exceptional"), ("Decisiveness", "Outstanding"),
                   ("Tactical Acumen", "Outstanding"), ("Intelligence & Deception", "Proficient")]),
        ("bde_22", [("Tactical Acumen", "Proficient"), ("Initiative", "Proficient"),
                    ("Training & Development", "Outstanding"), ("Discipline", "Proficient")]),
        ("train", [("Training & Development", "Exceptional"), ("Communication", "Outstanding"),
                   ("Logistics Mastery", "Proficient")]),
    ]:
        pdoc = frappe.get_doc("Person", persons[pkey])
        for q, lvl in qualities:
            # Avoid duplicate assessments
            if any(row.quality == LQUAL[q] for row in (pdoc.leadership_assessments or [])):
                continue
            pdoc.append("leadership_assessments", {
                "quality": LQUAL[q],
                "level": LLEVEL[lvl],
                "assessed_by": f"Dr Mahmud (DEMO)",
                "assessed_at": today - _dt.timedelta(days=30),
                "evidence_note": f"Demo assessment based on {q}; data from open sources.",
                "source": sources.get("iiss_mb") or sources.get("mod_press"),
            })
        pdoc.save(ignore_permissions=True)

    # ------------------------------------------------------------------
    # Military Units
    # ------------------------------------------------------------------
    units = {}
    # (key, name, parent, echelon, div_key, region_key, status, personnel, classif_key,
    #  commander_key, hq, lat, lng, armaments_list, workflow)
    udata = [
        ("div6", "6th Mechanised Division", None, "Division", "div6", "baghdad_ops",
         "Active", 320, "Mechanized Infantry", "div_c6", "Camp Rashid",
         Geo.RASHID[0], Geo.RASHID[1],
         [("m1a1m", 42), ("bmp1", 80), ("m198", 18)], "Published"),
        ("bde22", "22nd Mechanised Brigade", "div6", "Brigade", "div6", "baghdad_ops",
         "Active", 1850, "Mechanized Infantry", "bde_22", "Taji Military Camp",
         Geo.TAJI[0], Geo.TAJI[1], [("bmp1", 45), ("m113", 60), ("m16", 600)], "Published"),
        ("bde24", "24th Motorised Brigade", "div6", "Brigade", "div6", "baghdad_ops",
         "Training", 1420, "Mechanized Infantry", None, "Camp Rashid",
         Geo.RASHID[0]+0.02, Geo.RASHID[1], [("humvee", 40), ("m16", 400)], "In Review"),
        ("div9", "9th Armoured Division", None, "Division", "div9", "baghdad_ops",
         "Active", 280, "Armored", "div_c9", "Camp Taji",
         Geo.TAJI[0]+0.01, Geo.TAJI[1]-0.01,
         [("m1a1m", 80), ("t72", 30), ("m1126", 50)], "Published"),
        ("bde34", "34th Armoured Brigade", "div9", "Brigade", "div9", "baghdad_ops",
         "Standby", 1500, "Armored", None, "Taji tank park",
         Geo.TAJI[0]-0.01, Geo.TAJI[1]-0.02,
         [("m1a1m", 30), ("t72", 14), ("m113", 35)], "Verified"),
        ("bde35", "35th Commando Brigade (CT)", None, "Brigade", "iso", "ct_cmd",
         "Active", 1100, "Special Operations", "bde_35", "Victory Base",
         Geo.VIC_GREEN[0]-0.005, Geo.VIC_GREEN[1]-0.005,
         [("humvee", 60), ("m16", 900), ("ch4", 8)], "Published"),
        ("iso_hq", "ISOF HQ Battalion", "bde35", "Battalion", "iso", "ct_cmd",
         "Active", 420, "Special Operations", None, "Victory Base (HQ)",
         Geo.VIC_GREEN[0], Geo.VIC_GREEN[1]+0.003, [("humvee", 20)], "Published"),
        ("naval_uq", "Umm Qasr Naval Battalion", None, "Battalion", None, "basra_ops",
         "Active", 680, None, None, "Umm Qasr Naval Base",
         30.0333, 47.9333, [], "Published"),
        ("bde73", "73rd Infantry Brigade (Anbar)", None, "Brigade", None, "anbar_ops",
         "Reorganizing", 1900, "Mechanized Infantry", None, "Al-Asad Airbase",
         33.8000, 42.4333, [("humvee", 50), ("m16", 800), ("d30", 12)], "Published"),
        ("al_asad_air", "Al-Asad Air Defence Detachment", None, "Detachment", None,
         "anbar_ops", "Reserve", 120, None, None, "Al-Asad Airbase",
         33.8050, 42.4300, [], "Needs Update"),
        ("krg_div1", "1st Kurdistan Regional Guard Division", None, "Division", None,
         "kurdistan", "Active", 240, None, "krg_minpesh", "Erbil",
         Geo.ERBIL[0], Geo.ERBIL[1], [("ak47", 2000), ("rpk", 200)], "Verified"),
        ("log_bn", "6th Div Logistics Battalion", "div6", "Battalion", None,
         "baghdad_ops", "Active", 260, "Logistics", None, "Camp Rashid (rear)",
         Geo.RASHID[0]-0.01, Geo.RASHID[1]+0.01, [], "Published"),
        ("train_cent", "Taji Training Center", None, "Battalion", None, "baghdad_ops",
         "Training", 80, "Training", None, "Taji Military Camp",
         Geo.TAJI[0]+0.005, Geo.TAJI[1]+0.005, [], "Published"),
        ("disbanded_bn", "Disbanded ex-54th Brigade (demo)", None, "Brigade", None,
         "ninawa_ops", "Disbanded", 0, "Mechanized Infantry", None, "Mosul (ruins)",
         Geo.MOSUL[0], Geo.MOSUL[1], [], "Archived"),
    ]
    for (key, name, parent, ech, div_key, reg_key, status, pers, cls_key,
         cmdr, hq, lat, lng, alist, ws_state) in udata:
        vals = {
            "naming_series": "MIL-UNIT-.####" if ech != "Division" else "MIL-BRG-.####",
            "unit_name": f"{name} {TAG}",
            "is_group": 1 if ech in ("Division",) else 0,
            "echelon": ech,
            "region": regions[reg_key],
            "status": status,
            "direct_personnel": pers,
            "headquarters": f"{hq} {TAG}",
            "latitude": lat, "longitude": lng,
            "geo_precision": "approximate",
            "geocoding_method": "gazetteer",
            "geo_uncertainty_m": 600,
            "workflow_state": _ws(ws_state),
            "documentation_level": DOC["partial"],
            "authentication_level": AUTH["single_source"],
            "researcher_notes": f"{TAG} Demo unit.",
        }
        if parent:
            vals["parent_unit"] = units[parent]
        if div_key and div_key in divisions:
            vals["division"] = divisions[div_key]
        if cls_key:
            vals["classification"] = uclass[cls_key]
        if cmdr:
            vals["commander"] = persons[cmdr]
        units[key] = _add("Military Unit", vals, unit_name=f"{name} {TAG}")
        doc = frappe.get_doc("Military Unit", units[key])
        for acode, qty in alist:
            if any(row.armament == armaments[acode] for row in (doc.armaments or [])):
                continue
            doc.append("armaments", {
                "armament": armaments[acode],
                "quantity": qty,
                "condition": "Serviceable",
            })
        # Evidence
        if ws_state in ("Published", "Verified", "Needs Update", "Archived"):
            src_key = "iiss_mb" if status in ("Active","Standby","Training") else "dod_report"
            if sources.get(src_key):
                _ev(doc, sources[src_key], claim="Order of battle")
        doc.save(ignore_permissions=True)

    # ------------------------------------------------------------------
    # Operational Deployments
    # ------------------------------------------------------------------
    deploys = {}
    ddata = [
        ("baghdad_sec", "Baghdad Belt Security", units["bde22"], "Active",
         today - _dt.timedelta(days=90), None, Geo.NORTH_CAMP[0], Geo.NORTH_CAMP[1],
         "mod_press", "Published"),
        ("inherent_resolve", "CJT-OIR Advise & Assist (legacy, DEMO)", units["bde35"],
         "Completed", _dt.date(2017, 1, 1), _dt.date(2021, 12, 31),
         Geo.VIC_GREEN[0]-0.01, Geo.VIC_GREEN[1]-0.01, "dod_report", "Published"),
        ("anbar_stability", "Anbar Stabilization Patrol", units["bde73"],
         "Active", today - _dt.timedelta(days=365), None,
         33.5000, 42.8000, "dod_report", "Verified"),
        ("mosul_2016", "Mosul Offensive (2016-17, historical)", units["bde22"],
         "Completed", _dt.date(2016, 10, 17), _dt.date(2017, 7, 10),
         Geo.MOSUL[0], Geo.MOSUL[1], "dod_report", "Published"),
        ("taji_training", "Taji Range Security", units["train_cent"],
         "Active", _dt.date(2024, 1, 1), None, Geo.TAJI[0], Geo.TAJI[1],
         "mod_press", "Published"),
        ("umqasr_patrol", "Umm Qasr maritime patrol", units["naval_uq"],
         "Active", today - _dt.timedelta(days=60), None, 30.10, 47.90,
         "mod_press", "Verified"),
        ("planned_border", "Planned Border Monitoring (demo)", units["al_asad_air"],
         "Planned", today + _dt.timedelta(days=60), None, 33.0, 41.0,
         "mod_press", "Draft"),
        ("suspended_mosul", "Suspended Mosul Garrison Reinforcement (demo)", units["bde34"],
         "Suspended", today - _dt.timedelta(days=45), None, Geo.MOSUL[0], Geo.MOSUL[1],
         "jazeera_art", "Rejected"),
    ]
    for (key, name, unit_key, status, sd, ed, lat, lng, src, ws_state) in ddata:
        vals = {
            "naming_series": "MIL-DEP-.YYYY.-.####",
            "deployment_name": f"{name} {TAG}",
            "unit": units[unit_key] if unit_key in units else units.get(unit_key),
            "status": status,
            "start_date": sd,
            "latitude": lat, "longitude": lng,
            "geo_precision": "centroid",
            "geocoding_method": "inherited",
            "workflow_state": _ws(ws_state),
            "documentation_level": DOC["partial"],
            "authentication_level": AUTH["single_source"],
        }
        if ed: vals["end_date"] = ed
        if src in sources: vals["primary_source"] = sources[src]
        deploys[key] = _add("Operational Deployment", vals, deployment_name=f"{name} {TAG}")
        if src in sources:
            ddoc = frappe.get_doc("Operational Deployment", deploys[key])
            _ev(ddoc, sources[src], claim="Deployment status")
            ddoc.save(ignore_permissions=True)

    # ------------------------------------------------------------------
    # Training Exercises
    # ------------------------------------------------------------------
    trainings = {}
    tdata = [
        ("jre", "Joint Readiness Exercise 'Eagle Resolve'", units["bde22"],
         "Joint Exercise", "Satisfactory", today - _dt.timedelta(days=21),
         today - _dt.timedelta(days=14), 950, "Col. Saad al-Moussawi", "Taji range complex",
         "mod_press", "Published"),
        ("officer_course", "Rustamiyah Officer Commissioning Course (demo cohort)",
         units["train_cent"], "Course", "Excellent", _dt.date(2025, 9, 1),
         _dt.date(2026, 6, 1), 240, None, "First Military College",
         "mod_press", "Published"),
        ("ct_cert", "CT Close-Quarter Battle Certification", units["bde35"],
         "Certification", "Satisfactory", today - _dt.timedelta(days=60),
         today - _dt.timedelta(days=55), 120, None, "Victory Base",
         "mod_press", "Verified"),
        ("drill_nco", "NCO Drill Weekend (monthly, demo)", units["log_bn"],
         "Drill", "Needs Improvement", today - _dt.timedelta(days=7),
         today - _dt.timedelta(days=6), 200, None, "Camp Rashid",
         "mod_press", "In Review"),
        ("taji_coalition", "Coalition-led medical training exercise (DEMO)",
         units["bde22"], "Exercise", "Unsatisfactory", _dt.date(2025, 6, 1),
         _dt.date(2025, 6, 5), 180, None, "Taji", "dod_report", "Archived"),
    ]
    for (key, name, uk, tt, assess, sd, ed, n, lt, loc, src, ws_state) in tdata:
        vals = {
            "naming_series": "MIL-TRN-.YYYY.-.####",
            "exercise_name": f"{name} {TAG}",
            "unit": units[uk],
            "training_type": tt,
            "assessment": assess,
            "start_date": sd,
            "end_date": ed,
            "duration_days": (ed - sd).days,
            "participant_count": n,
            "location": f"{loc} {TAG}",
            "lead_trainer": lt,
            "workflow_state": _ws(ws_state),
            "documentation_level": DOC["partial"],
            "authentication_level": AUTH["single_source"],
        }
        if src in sources:
            vals["primary_source"] = sources[src]
        trainings[key] = _add("Training Exercise", vals, exercise_name=f"{name} {TAG}")

    # ------------------------------------------------------------------
    # Missions
    # ------------------------------------------------------------------
    missions = {}
    mdata = [
        ("op_baghdad", "Operation Baghdad Shield", units["div6"], "Ongoing",
         today - _dt.timedelta(days=180), None, "mod_press", "Verified"),
        ("op_mosul_liberation", "Operation We Are Coming, Nineveh (Mosul liberation)",
         units["bde22"], "Executed", _dt.date(2016, 10, 17), _dt.date(2017, 7, 10),
         "dod_report", "Published"),
        ("op_faw_cancelled", "Planned Faw amphibious demonstration (CANCELLED)",
         units["naval_uq"], "Cancelled", _dt.date(2025, 4, 1), _dt.date(2025, 4, 15),
         "jazeera_art", "Rejected"),
        ("op_anbar_planned", "Planned Anbar Desert Patrol", units["bde73"],
         "Planned", today + _dt.timedelta(days=120), None, "mod_press", "Draft"),
    ]
    for (key, name, uk, status, sd, ed, src, ws_state) in mdata:
        vals = {
            "naming_series": "MIL-MIS-.YYYY.-.####",
            "mission_name": f"{name} {TAG}",
            "unit": units[uk],
            "status": status,
            "start_date": sd,
            "workflow_state": _ws(ws_state),
            "documentation_level": DOC["partial"],
            "authentication_level": AUTH["single_source"],
        }
        if ed: vals["end_date"] = ed
        if src in sources: vals["primary_source"] = sources[src]
        missions[key] = _add("Mission", vals, mission_name=f"{name} {TAG}")

    # ------------------------------------------------------------------
    # Research Events — covering every event_type
    # ------------------------------------------------------------------
    events = {}
    edata = [
        # (key, en, ar, etype, start, end, place, source, ws_state)
        ("announce_shield", "Announcement of Operation Baghdad Shield",
         "إعلان عملية درع بغداد", "conference",
         _dt.datetime(today.year, today.month-5, max(today.day,1), 10, 0), None,
         "mod_hq", "mod_press", "Published"),
        ("jre_end", "Conclusion of Eagle Resolve JRE",
         "اختتام مناورة عزم النسر", "celebration",
         _dt.datetime.combine(today - _dt.timedelta(days=14), _dt.time(12,0)),
         _dt.datetime.combine(today - _dt.timedelta(days=14), _dt.time(18,0)),
         "taji_camp", "mod_press", "Published"),
        ("founding_college", "Founding of First Military College, 1924",
         "تأسيس الكلية العسكرية الأولى 1924", "founding",
         _dt.datetime(1924, 1, 1), None, "rust_college_campus", "malov_book", "Published"),
        ("founding_mod", "Establishment of Ministry of Defence, 1921",
         "تأسيس وزارة الدفاع 1921", "founding", _dt.datetime(1921, 1, 1), None,
         "mod_hq", "malov_book", "Published"),
        ("faisal_coronation", "Coronation of King Faisal I, 1921",
         "تتويج الملك فيصل الأول 1921", "appointment",
         _dt.datetime(1921, 8, 23), None, "baghdad_city", "malov_book", "Published"),
        ("nuri_death", "Death of Nuri al-Said, 1958",
         "مقتل نوري السعيد 1958", "death",
         _dt.datetime(1958, 7, 15), None, "baghdad_city", "malov_book", "Published"),
        ("faisal_birth", "Birth of King Faisal I, 1885",
         "ولادة الملك فيصل الأول 1885", "birth",
         _dt.datetime(1885, 5, 20), None, None, "malov_book", "Published"),
        ("halabja_1988", "Halabja chemical attack, 1988 (DEMO reference)",
         "هجوم حلبجة الكيمياوي 1988", "destruction",
         _dt.datetime(1988, 3, 16), None, None, "malov_book", "Published"),
        ("mosul_fall_2014", "Fall of Mosul to ISIS, June 2014 (DEMO)",
         "سقوط الموصل بيد داعش حزيران 2014", "destruction",
         _dt.datetime(2014, 6, 10), None, "mosul_city", "dod_report", "Published"),
        ("mosul_liberation_2017", "Liberation of Mosul, July 2017 (DEMO)",
         "تحرير الموصل تموز 2017", "celebration",
         _dt.datetime(2017, 7, 10), None, "mosul_city", "dod_report", "Published"),
        ("cofs_appt_2024", "Appointment of Gen al-Tamimi as CoS",
         "تعيين الفريق التميمي رئيساً للأركان", "appointment",
         _dt.datetime(today.year-1, today.month, max(today.day,1)), None,
         "mod_hq", "mod_press", "Published"),
        ("malov_book_pub", "Publication of 'Modern Iraqi Army' monograph",
         "صدور دراسة 'الجيش العراقي الحديث'", "publication",
         _dt.datetime(2025, 9, 1), None, None, "malov_book", "Published"),
        ("babylon_destruction_isis", "ISIS destruction at Babylon (DEMO)",
         "تدمير داعش في بابل", "destruction",
         _dt.datetime(2015, 3, 1), None, "babylon_ruins", "dod_report", "Disputed"),
        ("baath_purge", "Debaathification order (DEMO example)",
         "قرار اجتثاث البعث", "reform",
         _dt.datetime(2003, 5, 16), None, "baghdad_city", "malov_book", "Published"),
        ("anbar_dispute_2025", "Anbar redeployment dispute (DEMO)",
         "خلاف حول إعادة الانتشار في الأنبار", "dispute",
         _dt.datetime(2025, 8, 1), None, None, "jazeera_art", "Disputed"),
        ("arbaeen_2025", "Arba'een pilgrimage 2025 (DEMO)",
         "زيارة الأربعين 2025", "celebration",
         _dt.datetime(2025, 8, 15), None, "karbala_city", "jazeera_art", "Published"),
        ("refugees_2014", "Displacement from Mosul, June 2014 (DEMO)",
         "نزوح من الموصل حزيران 2014", "migration",
         _dt.datetime(2014, 6, 10), None, "mosul_city", "dod_report", "Published"),
        ("museum_reopening", "Iraq Museum post-ISIS reopening (DEMO)",
         "إعادة افتتاح المتحف العراقي", "reopening",
         _dt.datetime(2015, 2, 28), None, "iraq_museum", "malov_book", "Needs Update"),
    ]
    for (key, en, ar, et, sd, ed, pl, src, ws_state) in edata:
        vals = {
            "naming_series": "EVT-.####",
            "title_en": f"{en} {TAG}",
            "title_ar": f"{ar} {TAG}",
            "event_type": ETYPE[et],
            "start_date": sd,
            "start_date_as_stated": str(sd.year),
            "start_date_precision": "day" if et in ("conference","appointment","celebration","destruction","reopening","dispute","publication") else "year",
            "workflow_state": _ws(ws_state),
            "documentation_level": DOC["partial"],
            "authentication_level": AUTH["single_source"],
        }
        if ed:
            vals["end_date"] = ed
            vals["end_date_precision"] = "day"
        if pl:
            vals["place"] = places[pl]
        if src in sources:
            vals["primary_source"] = sources[src]
        events[key] = _add("Research Event", vals, title_en=f"{en} {TAG}")

    # ------------------------------------------------------------------
    # Relationships — exercising every type and every endpoint combination
    # ------------------------------------------------------------------
    rel_count = 0

    def _rel(st, s, rt_code, ot, o, *, cur=0, role="", start=None, end=None,
            direction="Directed"):
        nonlocal rel_count
        rt = RTYPE.get(rt_code)
        if not rt:
            return None
        existing = frappe.db.get_value("Relationship", {
            "subject_type": st, "subject": s,
            "relationship_type": rt, "object_type": ot, "object": o,
        })
        if existing:
            return existing
        try:
            doc = frappe.get_doc({
                "doctype": "Relationship",
                "naming_series": "REL-.####",
                "relationship_type": rt,
                "direction": direction,
                "is_current": cur,
                "subject_type": st, "subject": s,
                "object_type": ot, "object": o,
                "role_as_stated": role or None,
                "start_date": start,
                "end_date": end,
                "workflow_state": _ws("Published"),
                "primary_source": sources["iiss_mb"],
                "documentation_level": DOC["partial"],
                "authentication_level": AUTH["single_source"],
            })
            doc.insert(ignore_permissions=True)
            rel_count += 1
            return doc.name
        except Exception as e:
            print(f"  ! rel failed {st}:{s[:30]} --{rt_code}-> {ot}:{o[:30] if o else ''} : {e}")
            return None

    P, I, Pl, E, S = "Person", "Institution", "Place", "Research Event", "Source"

    # director_of (Person -> Institution/Place - Place isn't valid, skip)
    _rel(P, persons["cofs"], "director_of", I, insts["mod"], cur=1,
         start=_dt.datetime(today.year-1, today.month, 1))
    _rel(P, persons["dr_salim"], "director_of", I, insts["iraq_nat_lib"], cur=1,
         start=_dt.datetime(2018,1,1))
    _rel(P, persons["dr_mahmud"], "director_of", I, insts["hoi"], cur=1,
         start=_dt.datetime(2020,1,1))

    # employed_by / employs
    for pk, ik in [("div_c6","mod"),("bde_22","mod"),("bde_35","mod"),
                    ("train","rust_college"),("dr_hikmat","baghdad_univ"),
                    ("dr_mahmud","hoi"),("nibras_journalist","saba_iq"),
                    ("us_attaché","usip"),("krg_minpesh","mod")]:
        _rel(P, persons[pk], "employed_by", I, insts[ik], cur=1)
        _rel(I, insts[ik], "employs", P, persons[pk], cur=1)

    # graduated_from / teacher_of / student_of / supervised_by
    for pk in ["div_c6","bde_22","train","bde24"]:
        pass
    _rel(P, persons["div_c6"], "graduated_from", I, insts["rust_college"])
    _rel(P, persons["bde_22"], "graduated_from", I, insts["rust_college"])
    _rel(P, persons["train"], "graduated_from", I, insts["rust_college"])
    _rel(P, persons["student_zainab"], "graduated_from", I, insts["mustansiriya"])
    _rel(P, persons["student_zainab"], "student_of", P, persons["dr_hikmat"], cur=1)
    _rel(P, persons["dr_hikmat"], "teacher_of", P, persons["student_zainab"], cur=1)
    _rel(P, persons["dr_hikmat"], "supervised", P, persons["student_zainab"], cur=1)
    _rel(P, persons["student_zainab"], "supervised_by", P, persons["dr_hikmat"], cur=1)
    _rel(P, persons["dr_hikmat"], "supervised", P, persons["dr_mahmud"])

    # colleague_of (symmetric)
    _rel(P, persons["div_c6"], "colleague_of", P, persons["div_c9"],
         direction="Symmetric")
    _rel(P, persons["dr_hikmat"], "colleague_of", P, persons["dr_mahmud"],
         direction="Symmetric")
    _rel(P, persons["dr_hikmat"], "co_author_of", P, persons["dr_mahmud"],
         direction="Symmetric")
    _rel(P, persons["dr_mahmud"], "co_author_of", P, persons["uk_analyst"],
         direction="Symmetric")

    # collaborator_of
    _rel(P, persons["dr_hikmat"], "collaborator_of", I, insts["usip"],
         direction="Symmetric")

    # founder_of / founded_by
    _rel(P, persons["faisal1"], "founder_of", I, insts["rust_college"])
    _rel(I, insts["rust_college"], "founded_by", P, persons["faisal1"])

    # board_member_of
    _rel(P, persons["ret_gen"], "board_member_of", I, insts["hoi"])
    _rel(P, persons["rel_sayid"], "board_member_of", I, insts["iraq_scholars"])

    # partner_of
    _rel(I, insts["usip"], "partner_of", I, insts["hoi"], direction="Symmetric")
    _rel(I, insts["baghdad_univ"], "partner_of", I, insts["mustansiriya"],
         direction="Symmetric")

    # member_of
    _rel(P, persons["rel_sayid"], "member_of", I, insts["iraq_scholars"])

    # located_in (only valid endpoints)
    _rel(I, insts["mod"], "located_in", Pl, places["mod_hq"])
    _rel(I, insts["rust_college"], "located_in", Pl, places["rust_college_campus"])
    _rel(I, insts["baghdad_univ"], "located_in", Pl, places["baghdad_univ_campus"])
    _rel(I, insts["mustansiriya"], "located_in", Pl, places["mustansiriya_univ"])
    _rel(I, insts["iraq_nat_lib"], "located_in", Pl, places["national_library"])
    _rel(I, insts["iraq_museum"], "located_in", Pl, places["iraq_museum"])
    _rel(E, events["announce_shield"], "located_in", Pl, places["mod_hq"])
    _rel(E, events["jre_end"], "located_in", Pl, places["taji_camp"])
    _rel(E, events["faisal_coronation"], "located_in", Pl, places["baghdad_city"])
    _rel(E, events["mosul_fall_2014"], "located_in", Pl, places["mosul_city"])
    _rel(E, events["mosul_liberation_2017"], "located_in", Pl, places["mosul_city"])
    _rel(E, events["arbaeen_2025"], "located_in", Pl, places["karbala_city"])
    _rel(E, events["babylon_destruction_isis"], "located_in", Pl, places["babylon_ruins"])

    # contains
    _rel(Pl, places["iraq"], "contains", Pl, places["baghdad_city"])
    _rel(Pl, places["iraq"], "contains", Pl, places["mosul_city"])
    _rel(Pl, places["iraq"], "contains", Pl, places["basra_city"])
    _rel(Pl, places["baghdad_city"], "contains", Pl, places["mod_hq"])
    _rel(Pl, places["baghdad_city"], "contains", Pl, places["taji_camp"])
    _rel(Pl, places["baghdad_city"], "contains", Pl, places["rashid_camp"])
    _rel(Pl, places["baghdad_city"], "contains", Pl, places["victory_base"])

    # graduated_from for Faisal1 (historical)
    _rel(P, persons["faisal1"], "graduated_from", I, insts["rust_college"])  # playful; illustrative

    # father_of / child_of / relative_of
    _rel(P, persons["historian_abbas"], "relative_of", P, persons["dr_hikmat"],
         direction="Symmetric")

    # succeeded_by / succeeded
    _rel(P, persons["cofs"], "succeeded_by", P, persons["ret_gen"])
    _rel(P, persons["ret_gen"], "succeeded", P, persons["cofs"])

    # rival_of
    _rel(P, persons["nuri_said"], "rival_of", P, persons["faisal1"], direction="Symmetric")

    # participated_in (Person -> Event)
    for pk in ["div_c6","bde_22","iso_c"]:
        _rel(P, persons[pk], "participated_in", E, events["mosul_liberation_2017"])
    _rel(P, persons["train"], "participated_in", E, events["jre_end"])
    _rel(P, persons["faisal1"], "participated_in", E, events["faisal_coronation"])
    _rel(P, persons["nuri_said"], "participated_in", E, events["faisal_coronation"])
    _rel(P, persons["dr_hikmat"], "participated_in", E, events["malov_book_pub"])
    _rel(P, persons["uk_analyst"], "participated_in", E, events["malov_book_pub"])
    _rel(P, persons["nibras_journalist"], "participated_in", E, events["arbaeen_2025"])
    _rel(P, persons["dr_salim"], "participated_in", E, events["museum_reopening"])

    # cites (Event -> Source / Source -> Source)
    _rel(E, events["announce_shield"], "cites", S, sources["mod_press"])
    _rel(E, events["mosul_liberation_2017"], "cites", S, sources["dod_report"])
    _rel(E, events["malov_book_pub"], "cites", S, sources["malov_book"])
    _rel(S, sources["malov_book"], "cited_by", E, events["malov_book_pub"])
    _rel(E, events["faisal_coronation"], "cites", S, sources["malov_book"])
    _rel(E, events["babylon_destruction_isis"], "cites", S, sources["dod_report"])
    _rel(S, sources["jazeera_art"], "cited_by", E, events["anbar_dispute_2025"])
    _rel(E, events["anbar_dispute_2025"], "cites", S, sources["jazeera_art"])

    # endowed
    _rel(P, persons["faisal1"], "endowed", I, insts["rust_college"])

    # corresponded_with (historical)
    _rel(P, persons["faisal1"], "corresponded_with", P, persons["nuri_said"],
         direction="Symmetric")

    # affiliated_with
    _rel(P, persons["ret_gen"], "affiliated_with", I, insts["hoi"])
    _rel(P, persons["krg_minpesh"], "affiliated_with", I, insts["mod"])
    _rel(P, persons["historian_abbas"], "affiliated_with", I, insts["baghdad_univ"])

    # other
    _rel(P, persons["us_attaché"], "other", I, insts["mod"],
         role="Military attaché accreditation")

    frappe.db.commit()

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    counts = {
        "places": len(places),
        "sources": len(sources),
        "institutions": len(insts),
        "persons": len(persons),
        "command_regions": len(regions),
        "military_divisions": len(divisions),
        "unit_classifications": len(uclass),
        "armaments": len(armaments),
        "military_units": len(units),
        "deployments": len(deploys),
        "training_exercises": len(trainings),
        "missions": len(missions),
        "research_events": len(events),
        "relationships": rel_count,
        "social_platforms": len(plats),
        "external_id_schemes": len(schemes),
        "tag": TAG,
    }
    print("SIRAJ extensive DEMO data seeded:")
    for k, v in counts.items():
        print(f"  {k:25s} {v}")
    print("\nTo REMOVE this demo dataset, run:")
    print("  bench --site frappe.com execute siraj_research.setup.demo_data.teardown_demo_data")
    return counts


def teardown_demo_data():
    """Remove every DEMO-tagged record."""
    removed = 0
    order = [
        ("Relationship", "display_name"),
        ("Person Position", "name"),  # child of Person
        ("Leadership Quality Assessment", "name"),
        ("Social Account", "name"),
        ("Evidence", "name"),
        ("External Identifier", "name"),
        ("Unit Armament Holding", "name"),
        ("Operational Deployment", "deployment_name"),
        ("Training Exercise", "exercise_name"),
        ("Mission", "mission_name"),
        ("Research Event", "title_en"),
        ("Military Unit", "unit_name"),
        ("Armament", "armament_name"),
        ("Military Division", "division_name"),
        ("Person", "name_en"),
        ("Institution", "name_en"),
        ("Source", "title"),
        ("Place", "name_en"),
        ("Command Region", "region_name"),
        ("Unit Classification", "classification_name"),
    ]
    for dt, field in order:
        try:
            names = frappe.get_all(dt, filters={field: ("like", f"%{TAG}%")}, pluck="name")
        except Exception as e:
            # Some child tables (Evidence, Person Position) can't be filtered by display_name;
            # rely on parent cascade.
            continue
        for name in names:
            try:
                frappe.delete_doc(dt, name, ignore_permissions=True, force=True)
                removed += 1
            except Exception as e:
                print(f"  ! could not delete {dt} {name}: {e}")
    # Social platforms / ext id schemes we created (code ends with _demo)
    for dt, field in [("Social Platform", "code"), ("External ID Scheme", "code")]:
        names = frappe.get_all(dt, filters={field: ("like", "%_demo")}, pluck="name")
        for name in names:
            try:
                frappe.delete_doc(dt, name, ignore_permissions=True, force=True)
                removed += 1
            except Exception as e:
                print(f"  ! could not delete {dt} {name}: {e}")
    frappe.db.commit()
    print(f"Removed {removed} DEMO records.")
    return {"removed": removed}
