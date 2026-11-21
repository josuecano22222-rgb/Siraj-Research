# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
"""Fictional [DEMO] dataset — load, remove and isolate for SIRAJ Research.

Bench commands (preferred):

    bench --site <site> siraj-research load-demo-data
    bench --site <site> siraj-research remove-demo-data
    bench --site <site> siraj-research isolate-demo-data

Direct execution (equivalent):

    bench --site <site> execute siraj_research.setup.demo_data.seed_demo_data
    bench --site <site> execute siraj_research.setup.demo_data.teardown_demo_data
    bench --site <site> execute siraj_research.setup.demo_data.demo_status

Contract:
  * Content is pure data in ``demo_content`` — every person, institution,
    source, unit and event is fictional; real geography is used only so the
    coordinate → hierarchy auto-fill can be demonstrated.
  * Every record carries the ``[DEMO]`` tag in its display/title field.
  * Coordinates are stored exactly as written — never rounded or shortened.
  * Idempotent: re-running the loader never duplicates records.
  * Removal is precise: a per-site manifest (``siraj_demo_manifest.json``)
    lists every created name; a ``[DEMO]`` tag sweep acts as fallback and
    also cleans datasets created by older builds of this script.
"""

from __future__ import annotations

import datetime as _dt
import json
import os

import frappe

from siraj_research.setup import demo_content as C

TAG = C.TAG
MANIFEST_NAME = "siraj_demo_manifest.json"

#: doctype -> field scanned by the [DEMO] fallback sweep.
TAG_FIELDS = (
    ("Person", "name_en"),
    ("Institution", "name_en"),
    ("Place", "name_en"),
    ("Source", "title"),
    ("Research Event", "title_en"),
    ("Siraj Event", "title"),
    ("Military Unit", "unit_name"),
    ("Relationship", "display_name"),
    ("Person Institution", "title_en"),
    ("Person Event", "title_en"),
    ("Institution Event", "title_en"),
    ("Military Unit Event", "title_en"),
    ("Siraj Event Person", "title_en"),
    ("Siraj Event Institution", "title_en"),
    ("Siraj Event Location", "title_en"),
    ("Siraj Event Military Unit", "title_en"),
    ("Person Military Unit", "title_en"),
    ("Person Location", "title_en"),
    # legacy datasets from earlier builds of this script
    ("Operational Deployment", "deployment_name"),
    ("Training Exercise", "exercise_name"),
    ("Mission", "mission_name"),
    ("Armament", "armament_name"),
    ("Unit Classification", "classification_name"),
)

#: Deletion order for teardown (parents last). Units are sorted deepest-
#: first inside the executor because MilitaryUnit.on_trash refuses to
#: delete a unit that still has subordinates or dependents.
TEARDOWN_ORDER = [
    ("Relationship", "display_name"),
    ("Person Institution", "title_en"),
    ("Person Event", "title_en"),
    ("Institution Event", "title_en"),
    ("Military Unit Event", "title_en"),
    ("Siraj Event Person", "title_en"),
    ("Siraj Event Institution", "title_en"),
    ("Siraj Event Location", "title_en"),
    ("Siraj Event Military Unit", "title_en"),
    ("Person Military Unit", "title_en"),
    ("Person Location", "title_en"),
    ("Siraj Event", "title"),
    ("Research Event", "title_en"),
    ("Military Unit", "unit_name"),
    ("Person", "name_en"),
    ("Institution", "name_en"),
    ("Place", "name_en"),
    ("Source", "title"),
    ("Unit Classification", "classification_name"),
    ("Armament", "armament_name"),
]

#: Legacy dependents that would block unit deletion (on_trash checks).
LEGACY_BLOCKERS = (
    ("Command Appointment", "name"),
    ("Operational Deployment", "deployment_name"),
    ("Training Exercise", "exercise_name"),
    ("Mission", "mission_name"),
)

UNIT_DEPTH = {"Division": 0, "Regiment": 1, "Brigade": 1, "Battalion": 2,
              "Company": 3, "Platoon": 4, "Squadron": 3, "Detachment": 3}

_manifest: dict[str, set] = {}


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def _remember(doctype: str, name: str) -> None:
    if name:
        _manifest.setdefault(doctype, set()).add(name)


def _manifest_path() -> str:
    return frappe.get_site_path(MANIFEST_NAME)


def _manifest_load() -> None:
    global _manifest
    _manifest = {}
    path = _manifest_path()
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            for doctype, names in (data.get("docs") or {}).items():
                _manifest[doctype] = {n for n in names if n}
        except Exception as exc:  # pragma: no cover - corrupted manifest
            print(f"  ! demo manifest unreadable ({exc}); using tag sweep only")


def _manifest_save() -> None:
    payload = {
        "version": 1,
        "app": "siraj_research",
        "tag": TAG,
        "saved": _dt.datetime.now().isoformat(timespec="seconds"),
        "docs": {dt: sorted(names) for dt, names in sorted(_manifest.items())},
    }
    with open(_manifest_path(), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, ensure_ascii=False)


def _manifest_clear() -> None:
    global _manifest
    _manifest = {}
    path = _manifest_path()
    if os.path.exists(path):
        os.remove(path)


# ---------------------------------------------------------------------------
# Small helpers (same conventions as the previous loader)
# ---------------------------------------------------------------------------

def _gf(doctype: str, **filters):
    """Return the name of the first matching record or None."""
    return frappe.db.exists(doctype, filters)


def _add(doctype: str, values: dict, **check) -> str:
    """Insert unless ``check`` matches an existing record (idempotent)."""
    existing = frappe.db.exists(doctype, check) if check else None
    if existing:
        _remember(doctype, existing)
        return existing
    doc = frappe.get_doc({"doctype": doctype, **values})
    doc.insert(ignore_permissions=True)
    _remember(doctype, doc.name)
    return doc.name


def _ws(state: str) -> str | None:
    return _gf("Workflow State", workflow_state_name=state) or state


def _codes(doctype: str, codes) -> dict:
    return {code: _gf(doctype, code=code) for code in codes}


def _ref(kind_key: str, refs: dict) -> str:
    """Resolve a ``kind:key`` content reference to a document name."""
    kind, _, key = kind_key.partition(":")
    name = refs.get(kind, {}).get(key)
    if not name:
        raise ValueError(f"unresolved demo reference {kind_key!r}")
    return name


def _admin_value(level: str, code: str):
    if level == "country":
        return _gf("Country", code=code)
    doctype = {"governorate": "Governorate", "district": "District"}[level]
    return _gf(doctype, code=code)


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------

def seed_demo_data() -> dict:
    # Reference registries (workflow states, lookups, geography) must exist;
    # they are additive, so running the seeder again is harmless.
    if not frappe.db.exists("Authentication Level", {"code": "corroborated"}):
        from siraj_research.setup.master_data import seed_master_data
        seed_master_data()

    _manifest_load()

    AUTH = _codes("Authentication Level", C.CONFIDENCE_CODES)
    DOC = _codes("Documentation Level",
                 ("none", "minimal", "partial", "substantial", "exhaustive"))
    STYPE = _codes("Source Type",
                   ("archive_document", "report", "interview", "manuscript",
                    "website", "journal_article", "official_register",
                    "oral_history", "newspaper", "map"))
    SR = _codes("Source Reliability",
                ("primary_contemporary", "secondary", "high", "medium",
                 "low", "unverified"))
    PTYPE = _codes("Place Type",
                   ("city", "town", "building", "natural_site", "library",
                    "museum", "school"))
    ITYPE = _codes("Institution Type",
                   ("university", "research_center", "library", "ministry",
                    "museum", "association", "media", "international_body"))
    ISUB = _codes("Institution Subcategory",
                  ("public", "private", "ngo", "international"))
    GSYS = _codes("Governance System",
                  ("collegial", "board_of_trustees", "centralized"))
    ETYPE = _codes("Event Type",
                   ("founding", "migration", "reform", "reopening",
                    "conference", "dispute", "publication", "appointment",
                    "celebration", "other"))
    RTYPE = _codes("Relationship Type", (
        "employed_by", "member_of", "director_of", "teacher_of",
        "student_of", "colleague_of", "succeeded_by",
        "corresponded_with", "participated_in", "located_in", "contains",
        "cites", "affiliated_with"))
    PCAT = _codes("Person Category", ("military", "civilian"))
    PSTAT = _codes("Person Status", ("active", "retired", "deceased"))
    PCLASS = _codes("Person Classification", (
        "professor", "student", "researcher", "historian", "journalist",
        "religious_scholar", "archivist", "librarian", "administrator",
        "official", "translator"))
    BRANCH = _codes("Military Branch", ("Army",))
    SVC = _codes("Military Service Status", ("Active", "Reserve"))
    country = lambda code: _gf("Country", code=code)  # noqa: E731

    missing = [f"{dt}:{c}" for dt, mp in (
        ("Authentication Level", AUTH), ("Source Type", STYPE),
        ("Place Type", PTYPE), ("Institution Type", ITYPE),
        ("Event Type", ETYPE), ("Relationship Type", RTYPE)) for c, v in mp.items() if not v]
    if missing:
        raise RuntimeError(
            "demo data needs the reference registries first; run "
            "bench execute siraj_research.setup.master_data.seed_master_data "
            f"(missing: {', '.join(missing)})")

    seeded: list[tuple[str, str]] = []   # (doctype, name) for provenance pass
    counts: dict[str, int] = {}

    def _tally(dt: str) -> None:
        counts[dt] = counts.get(dt, 0) + 1

    # -- Sources (k01 first: it becomes the master demo source) -----------
    sources: dict[str, str] = {}
    for row in C.SOURCES:
        vals = {
            "naming_series": "SRC-.####",
            "title": f"{row['en']} {TAG}",
            "title_ar": f"{row['ar']} {TAG}",
            "source_type": STYPE[row["st"]],
            "source_reliability": SR[row["rel"]],
            "publisher": row["pub"],
            "publication_date_as_stated": row["pd_as"],
            "publication_date": row["pd"],
            "publication_date_precision": row["prec"],
            "access_date": _dt.date.today(),
            "workflow_state": _ws(row["ws"]),
        }
        sources[row["key"]] = _add("Source", vals,
                                   title=f"{row['en']} {TAG}")
        _tally("Source")
    master = sources["k01"]

    # -- Places -----------------------------------------------------------
    places: dict[str, str] = {}
    for row in C.PLACES:
        vals = {
            "naming_series": "PLC-.####",
            "display_name": f"{row['en']} {TAG}",
            "name_en": f"{row['en']} {TAG}",
            "name_ar": f"{row['ar']} {TAG}",
            "place_type": PTYPE[row["ptype"]],
            "workflow_state": _ws(row["ws"]),
            "documentation_level": DOC["partial"],
            "authentication_level": AUTH["single_source"],
            "primary_source": master,
        }
        if row.get("lat") is not None:
            # Exact literals from demo_content — never rounded.
            vals["latitude"] = row["lat"]
            vals["longitude"] = row["lng"]
            vals["geo_precision"] = row["gprec"]
            vals["geocoding_method"] = row["gmeth"]
            vals["geo_uncertainty_m"] = row["gunc"]
        for level, code in (row.get("admin") or {}).items():
            value = _admin_value(level, code)
            if value:
                vals[level] = value
        if row.get("parent"):
            vals["parent_place"] = places.get(row["parent"])
        places[row["key"]] = _add(
            "Place", vals,
            name_en=f"{row['en']} {TAG}", name_ar=f"{row['ar']} {TAG}")
        _tally("Place")
        seeded.append(("Place", places[row["key"]]))

    # -- Institutions -----------------------------------------------------
    institutions: dict[str, str] = {}
    for row in C.INSTITUTIONS:
        vals = {
            "naming_series": "INS-.####",
            "display_name": f"{row['en']} {TAG}",
            "name_en": f"{row['en']} {TAG}",
            "name_ar": f"{row['ar']} {TAG}",
            "institution_type": ITYPE[row["itype"]],
            "institution_subcategory": ISUB[row["sub"]],
            "governance_system": GSYS[row["gov"]],
            "founded_date_as_stated": row["founded_as"],
            "founded_date": row["founded"],
            "founded_date_precision": row["fprec"],
            "workflow_state": _ws(row["ws"]),
            "authentication_level": AUTH[row["auth"]],
            "documentation_level": DOC[row["doc"]],
            "primary_source": master,
        }
        if row.get("place"):
            vals["place"] = places[row["place"]]
        institutions[row["key"]] = _add(
            "Institution", vals,
            name_en=f"{row['en']} {TAG}", name_ar=f"{row['ar']} {TAG}")
        _tally("Institution")
        seeded.append(("Institution", institutions[row["key"]]))

    # -- Persons ----------------------------------------------------------
    persons: dict[str, str] = {}
    for row in C.PERSONS:
        vals = {
            "naming_series": "PER-.####",
            "display_name": f"{row['en']} {TAG}",
            "name_en": f"{row['en']} {TAG}",
            "name_ar": f"{row['ar']} {TAG}",
            "name_transliteration": row["en"],
            "category": PCAT[row["cat"]],
            "person_status": PSTAT[row["status"]],
            "workflow_state": _ws(row["ws"]),
            "authentication_level": AUTH[row["auth"]],
            "documentation_level": DOC[row["doc"]],
            "primary_source": master,
            "military_biography": (f"{row['bio']} {TAG}"
                                   if row.get("bio") else None),
        }
        nat = country(row["nat"]) if row.get("nat") else None
        if nat:
            vals["nationality"] = nat
        if row["cat"] == "military":
            vals["rank_title"] = row["rank"]
            vals["branch"] = BRANCH[row["branch"]] if row["branch"] else None
            vals["service_status"] = SVC[row["svc"]]
            if row["comm"]:
                vals["commission_date"] = _dt.date(row["comm"], 1, 1)
        else:
            vals["classification"] = PCLASS[row["cls"]]
        if row.get("byear"):
            vals["birth_date_as_stated"] = row["bas"]
            vals["birth_date"] = _dt.date(row["byear"], 1, 1)
            vals["birth_date_precision"] = row["bprec"]
        if row.get("pos"):
            vals["current_position_as_stated"] = row["pos"]
        if row.get("lat") is not None:
            vals["latitude"] = row["lat"]
            vals["longitude"] = row["lng"]
            vals["geo_precision"] = "centroid"
            vals["geocoding_method"] = "administrative"
        persons[row["key"]] = _add(
            "Person", vals,
            name_en=f"{row['en']} {TAG}", name_ar=f"{row['ar']} {TAG}")
        _tally("Person")
        seeded.append(("Person", persons[row["key"]]))

    # -- Family showcase (Phase 0 tab) -----------------------------------
    for key, fam in C.FAMILY.items():
        name = persons.get(key)
        if not name:
            continue
        pdoc = frappe.get_doc("Person", name)
        if pdoc.get("children") or pdoc.get("grandchildren") \
                or pdoc.get("siblings") or pdoc.get("spouse_name"):
            continue  # already applied (idempotent)
        pdoc.marital_status = fam["marital"]
        if fam.get("spouse"):
            pdoc.spouse_name = fam["spouse"]
            pdoc.marriage_date = fam["marriage"]
            pdoc.marriage_date_as_stated = fam["marriage_as"]
            pdoc.spouse_birth_date = fam["spouse_birth"]
            if fam.get("spouse_nat"):
                pdoc.spouse_nationality = country(fam["spouse_nat"])
            pdoc.spouse_occupation = fam["spouse_occ"]
        for child in fam.get("children") or []:
            pdoc.append("children", {
                "child_name": child["child_name"],
                "child_name_ar": child["child_name_ar"],
                "gender": child["gender"],
                "birth_date": child["birth"],
                "birth_date_as_stated": child["birth_as"],
                "occupation_or_school": child["occupation"],
                "number_of_children": child["number_of_children"],
            })
        for grand in fam.get("grandchildren") or []:
            pdoc.append("grandchildren", {
                "grandchild_name": grand["grandchild_name"],
                "grandchild_name_ar": grand["grandchild_name_ar"],
                "through_child": grand["through"],
                "gender": grand["gender"],
                "birth_date": grand["birth"],
                "birth_date_as_stated": grand["birth_as"],
            })
        for sib in fam.get("siblings") or []:
            pdoc.append("siblings", {
                "sibling_name": sib["sibling_name"],
                "sibling_name_ar": sib["sibling_name_ar"],
                "relation": sib["relation"],
                "birth_date": sib["birth"],
            })
        pdoc.save(ignore_permissions=True)

    # -- Military units (3-level hierarchy) ------------------------------
    units: dict[str, str] = {}
    for row in C.UNITS:
        vals = {
            "naming_series": "MIL-UNIT-.####",
            "unit_name": f"{row['en']} {TAG}",
            "unit_code": row["key"].upper(),
            "echelon": row["echelon"],
            "status": row["status"],
            "direct_personnel": row["personnel"],
            "commander": persons[row["commander"]],
            "formation_date": row["formed"],
            "headquarters": row["hq"],
            "role": row["role"],
            "workflow_state": _ws(row["ws"]),
            "authentication_level": AUTH[row["auth"]],
            "documentation_level": DOC["substantial"],
            "primary_source": master,
        }
        if row.get("parent"):
            vals["parent_unit"] = units[row["parent"]]
        if row.get("place"):
            vals["linked_place"] = places[row["place"]]
        units[row["key"]] = _add(
            "Military Unit", vals, unit_name=f"{row['en']} {TAG}")
        _tally("Military Unit")
        seeded.append(("Military Unit", units[row["key"]]))

    # -- Research Events (date precision showcase) -----------------------
    research_events: dict[str, str] = {}
    for row in C.RESEARCH_EVENTS:
        vals = {
            "naming_series": "EVT-.####",
            "title_en": f"{row['en']} {TAG}",
            "title_ar": f"{row['ar']} {TAG}",
            "event_type": ETYPE[row["etype"]],
            "start_date": row["start"],
            "start_date_as_stated": row["sas"],
            "start_date_precision": row["sprec"],
            "workflow_state": _ws(row["ws"]),
            "authentication_level": AUTH[row["auth"]],
            "documentation_level": DOC[row["doc"]],
            "primary_source": sources[row["src"]],
        }
        if row.get("place"):
            vals["place"] = places[row["place"]]
            vals["place_as_stated"] = C.PLACES[
                [p["key"] for p in C.PLACES].index(row["place"])]["en"]
        research_events[row["key"]] = _add(
            "Research Event", vals, title_en=f"{row['en']} {TAG}")
        _tally("Research Event")
        seeded.append(("Research Event", research_events[row["key"]]))

    # -- Siraj Events (desk flagship) ------------------------------------
    siraj_events: dict[str, str] = {}
    for row in C.SIRAJ_EVENTS:
        vals = {
            "title": f"{row['title']} {TAG}",
            "event_type": ETYPE[row["etype"]],
            "status": row["status"],
            "start_date": row["start"],
            "end_date": row.get("end"),
            "description": f"{row['desc']} {TAG}",
            "workflow_state": _ws(row["ws"]),
            "authentication_level": AUTH[row["auth"]],
            "documentation_level": DOC["partial"],
            "primary_source": sources[row["src"]],
        }
        if row.get("place"):
            vals["linked_place"] = places[row["place"]]
        siraj_events[row["key"]] = _add(
            "Siraj Event", vals, title=f"{row['title']} {TAG}")
        _tally("Siraj Event")
        seeded.append(("Siraj Event", siraj_events[row["key"]]))

    refs = {"P": persons, "I": institutions, "Pl": places, "U": units,
            "E": research_events, "S": siraj_events, "Src": sources}

    # -- Relationships (varied confidence) -------------------------------
    for row in C.RELATIONSHIPS:
        subject = _ref(row["subject"], refs)
        obj = _ref(row["object"], refs)
        rt = RTYPE[row["type"]]
        if not rt:
            raise RuntimeError(f"relationship type missing: {row['type']}")
        existing = frappe.db.get_value(
            "Relationship",
            {"subject_type": _kind_of(row["subject"]),
             "subject": subject, "relationship_type": rt,
             "object_type": _kind_of(row["object"]), "object": obj},
            "name")
        if existing:
            _remember("Relationship", existing)
            continue
        doc = frappe.get_doc({
            "doctype": "Relationship",
            "naming_series": "REL-.####",
            "relationship_type": rt,
            "direction": row.get("direction", "Directed"),
            "is_current": row.get("cur", 0),
            "subject_type": _kind_of(row["subject"]),
            "subject": subject,
            "object_type": _kind_of(row["object"]),
            "object": obj,
            "role_as_stated": row.get("role"),
            "start_date": row.get("start"),
            "end_date": row.get("end"),
            "authentication_level": AUTH[row["auth"]],
            "documentation_level": DOC["partial"],
            "primary_source": master,
            "workflow_state": _ws("Published"),
        })
        doc.insert(ignore_permissions=True)
        _remember("Relationship", doc.name)
        _tally("Relationship")
        seeded.append(("Relationship", doc.name))

    # -- Association (link-table) rows -----------------------------------
    for row in C.ASSOCIATIONS:
        resolved = {field: _ref(ref, refs)
                    for field, ref in row["refs"].items()}
        check = dict(resolved)
        title = f"{row['title']} {TAG}"
        vals = {
            "title_en": title,
            "title_ar": f"{row['title']} {TAG}",
            "role": row["role"],
            "authentication_level": AUTH[row["auth"]],
            "documentation_level": DOC["partial"],
            "primary_source": master,
            "workflow_state": _ws(row["ws"]),
            **resolved,
        }
        name = _add(row["dt"], vals, **check)
        _tally(row["dt"])
        seeded.append((row["dt"], name))

    # -- Provenance post-pass: source for every claim --------------------
    failures = 0
    for doctype, name in dict.fromkeys(seeded):
        try:
            doc = frappe.get_doc(doctype, name)
            touched = False
            if doc.meta.has_field("primary_source") and not doc.get("primary_source"):
                doc.primary_source = master
                touched = True
            if doc.meta.has_field("evidence") and not doc.get("evidence"):
                doc.append("evidence", {
                    "source": doc.get("primary_source") or master,
                    "support_type": "supports",
                    "supported_claim": f"Demo record: {name}",
                    "authentication_level": AUTH["single_source"],
                    "notes": f"Seeded demo evidence {TAG}",
                })
                touched = True
            if touched:
                doc.save(ignore_permissions=True)
        except Exception as exc:
            failures += 1
            print(f"  ! provenance pass failed for {doctype} {name}: {exc}")

    _manifest_save()
    frappe.db.commit()

    result = dict(counts)
    result["manifest_records"] = sum(len(v) for v in _manifest.values())
    result["provenance_failures"] = failures
    result["tag"] = TAG
    print("SIRAJ demo dataset loaded (fictional, [DEMO]-tagged):")
    for key in sorted(result):
        print(f"  {key:28s} {result[key]}")
    print("\nRemove it with:  bench --site <site> siraj-research remove-demo-data")
    return result


_KIND_MAP = {"P": "Person", "I": "Institution", "Pl": "Place",
             "U": "Military Unit", "E": "Research Event",
             "S": "Siraj Event", "Src": "Source"}


def _kind_of(ref: str) -> str:
    kind = ref.partition(":")[0]
    return _KIND_MAP[kind]


# ---------------------------------------------------------------------------
# Teardown
# ---------------------------------------------------------------------------

def _tagged(doctype: str, field: str) -> list[str]:
    try:
        return list(frappe.get_all(
            doctype, filters={field: ("like", f"%{TAG}%")},
            pluck="name", limit_page_length=0))
    except Exception:
        return []


def _tagged_relationships() -> list[str]:
    """Relationship display_name embeds series names (no tag) — match on
    the tagged primary_source instead, plus any tagged display_name."""
    names = set(_tagged("Relationship", "display_name"))
    tagged_sources = _tagged("Source", "title")
    if tagged_sources:
        names.update(frappe.get_all(
            "Relationship", filters={"primary_source": ["in", tagged_sources]},
            pluck="name", limit_page_length=0))
    return sorted(names)


def teardown_demo_data() -> dict:
    _manifest_load()
    removed: dict[str, int] = {}
    failed: dict[str, int] = {}

    def _delete(doctype: str, name: str) -> None:
        try:
            frappe.delete_doc(doctype, name, ignore_permissions=True,
                              force=True)
            removed[doctype] = removed.get(doctype, 0) + 1
        except Exception as exc:
            failed[doctype] = failed.get(doctype, 0) + 1
            print(f"  ! could not delete {doctype} {name}: {exc}")

    def _names(doctype: str, field: str | None) -> set:
        names = set(_manifest.get(doctype) or ())
        if field:
            names.update(_tagged(doctype, field))
        return names

    # 1. Legacy dependents that would block unit deletion.
    for doctype, field in LEGACY_BLOCKERS:
        for name in _names(doctype, None if field == "name" else field):
            _delete(doctype, name)

    # 2. Everything else in parent-last order; units deepest-first.
    for doctype, field in TEARDOWN_ORDER:
        if doctype == "Relationship":
            names = set(_manifest.get(doctype) or ())
            names.update(_tagged_relationships())
        else:
            names = _names(doctype, field)
        if doctype == "Military Unit":
            rows = frappe.get_all(
                "Military Unit", filters={"name": ["in", sorted(names)]},
                fields=["name", "echelon"], limit_page_length=0) if names else []
            ordered = sorted(
                rows,
                key=lambda r: UNIT_DEPTH.get(r.echelon or "", 9),
                reverse=True)
            known = {r.name for r in ordered}
            ordered += [{"name": n, "echelon": None}
                        for n in sorted(names) if n not in known]
            for row in ordered:
                _delete("Military Unit", row["name"])
            continue
        for name in sorted(names):
            _delete(doctype, name)

    # 3. Legacy extras kept from earlier builds (tag-swept only).
    for doctype, field in (("Social Platform", "code"),
                           ("External ID Scheme", "code")):
        try:
            for name in frappe.get_all(
                    doctype, filters={field: ("like", "%_demo")},
                    pluck="name", limit_page_length=0):
                _delete(doctype, name)
        except Exception:
            pass

    _manifest_clear()
    frappe.db.commit()
    total = sum(removed.values())
    print(f"Removed {total} DEMO records"
          + (f" ({sum(failed.values())} failed)" if failed else "") + ".")
    if failed:
        print("  failed by doctype:", failed)
    return {"removed": removed, "failed": failed, "total": total}


# ---------------------------------------------------------------------------
# Isolation report
# ---------------------------------------------------------------------------

def demo_status() -> dict:
    """Report demo records per DocType — how to isolate them."""
    per_doctype: dict[str, int] = {}
    for doctype, field in TAG_FIELDS:
        if doctype == "Relationship":
            count = len(_tagged_relationships())
        else:
            count = len(_tagged(doctype, field))
        if count:
            per_doctype[doctype] = count
    manifest_records = 0
    manifest_doctypes = 0
    try:
        _manifest_load()
        manifest_records = sum(len(v) for v in _manifest.values())
        manifest_doctypes = len(_manifest)
    except Exception:
        pass
    print("SIRAJ demo dataset isolation report")
    print(f"  tag: {TAG}   manifest: {MANIFEST_NAME}")
    print(f"  manifest: {manifest_records} records in {manifest_doctypes} doctypes")
    print("  database ([DEMO] tag sweep):")
    if not per_doctype:
        print("    (no tagged records found)")
    for doctype in sorted(per_doctype):
        print(f"    {doctype:32s} {per_doctype[doctype]}")
    total = sum(per_doctype.values())
    print(f"    {'TOTAL':32s} {total}")
    print("\nIsolate in the UI: search for [DEMO] in the list view, or open")
    print("a report filtered on the display/title field containing [DEMO].")
    return {"tag": TAG, "per_doctype": per_doctype, "total": total,
            "manifest_records": manifest_records}
