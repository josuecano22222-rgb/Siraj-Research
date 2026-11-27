# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
"""Pure contracts for the demo dataset (no frappe required).

Covers what only source structure can prove in CI: spec volumes, the
fictional guard, edge cases, confidence variety, teardown coverage and
the bench command surface. The live load/remove round-trip lives in
siraj_research/tests/test_demo_data.py (needs a real site).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from siraj_research.setup import demo_content as C

ROOT = Path(__file__).resolve().parents[1]
DEMO_PY = ROOT / "siraj_research" / "setup" / "demo_data.py"
COMMANDS_PY = ROOT / "siraj_research" / "commands.py"


# -- volumes (spec: ~25 / 8 / 12 / 15 / 10 / 6 across 3 levels) ----------

def test_spec_volumes_match_content():
    assert len(C.PERSONS) == C.SPEC["persons"] == 25
    assert len(C.INSTITUTIONS) == C.SPEC["institutions"] == 8
    assert len(C.PLACES) == C.SPEC["places"] == 12
    assert len(C.SOURCES) == C.SPEC["sources"] == 10
    assert len(C.UNITS) == C.SPEC["military_units"] == 6
    assert len(C.SIRAJ_EVENT_DATE_PRECISION) == C.SPEC["siraj_event_date_precision"]
    assert len(C.SIRAJ_EVENTS) == C.SPEC["siraj_events"]
    assert (len(C.SIRAJ_EVENT_DATE_PRECISION) + len(C.SIRAJ_EVENTS)
            == C.SPEC["events_total"] == 15)


def test_units_span_three_levels_with_resolvable_parents():
    by_key = {u["key"]: u for u in C.UNITS}
    echelons = {u["echelon"] for u in C.UNITS}
    assert {"Division", "Brigade", "Battalion"} <= echelons
    depths = set()
    for unit in C.UNITS:
        depth = 0
        parent = unit.get("parent")
        while parent:
            parent = by_key[parent]["parent"]
            depth += 1
            assert depth < 10, "cycle in demo unit parents"
        depths.add(depth)
        if unit.get("parent"):
            assert unit["parent"] in by_key
    assert max(depths) == C.SPEC["unit_levels"] - 1
    # every commander is military (the controller enforces this)
    persons = {p["key"]: p for p in C.PERSONS}
    for unit in C.UNITS:
        assert persons[unit["commander"]]["cat"] == "military"


# -- fictional guard ------------------------------------------------------

def test_content_is_fictional():
    haystack = []
    for row in C.PERSONS:
        haystack += [row["en"], row["ar"]]
    for row in C.INSTITUTIONS:
        haystack += [row["en"], row["ar"]]
    for row in C.SIRAJ_EVENT_DATE_PRECISION:
        haystack += [row["en"], row["ar"]]
    for row in C.SIRAJ_EVENTS:
        haystack += [row["title"]]
    for row in C.SOURCES:
        haystack += [row["en"], row["ar"]]
    blob = "\n".join(haystack)
    for banned in C.BANNED_NAMES:
        assert banned.lower() not in blob.lower(), (
            f"real-world name {banned!r} leaked into demo content")


# -- edge cases -----------------------------------------------------------

def test_edge_cases_present():
    places = {p["key"]: p for p in C.PLACES}
    # coordinates-only place → auto-fill demo (no admin levels set)
    auto = places["pl05"]
    assert auto["lat"] is not None and not auto["admin"]
    # country-only place → missing levels, no coordinates
    missing = places["pl06"]
    assert missing["lat"] is None and set(missing["admin"]) == {"country"}
    # open-water point with exact, unrounded coordinates
    ocean = places["pl07"]
    assert (ocean["lat"], ocean["lng"]) == C.OCEAN_STATION == (31.6, 33.8)
    # uncertain dates: approximate + decade + a person with `uncertain`
    precisions = {e["sprec"] for e in C.SIRAJ_EVENT_DATE_PRECISION}
    assert {"approximate", "decade"} <= precisions
    assert any(e["sas"] == "circa 1947" for e in C.SIRAJ_EVENT_DATE_PRECISION)
    assert any(p["bprec"] == "uncertain" for p in C.PERSONS)


def test_coordinates_are_exact_literals():
    """No rounding anywhere in the content module (mandatory rule)."""
    source = (ROOT / "siraj_research" / "setup" / "demo_content.py").read_text(
        encoding="utf-8")
    assert "round(" not in source
    assert ".2f" not in source and "%.2f" not in source
    for place in C.PLACES:
        if place["lat"] is None:
            continue
        # stored exactly as the literal declares
        assert isinstance(place["lat"], float)
        assert isinstance(place["lng"], float)


# -- relationships: confidence + endpoints -------------------------------

def test_relationship_confidence_varies():
    used = {r["auth"] for r in C.RELATIONSHIPS}
    assert used == set(C.CONFIDENCE_CODES), (
        f"confidence codes not all exercised: {set(C.CONFIDENCE_CODES) - used}")


def test_relationship_endpoints_resolve():
    kinds = {"P": {p["key"] for p in C.PERSONS},
             "I": {i["key"] for i in C.INSTITUTIONS},
             "Pl": {p["key"] for p in C.PLACES},
             "U": {u["key"] for u in C.UNITS},
             "E": {e["key"] for e in C.SIRAJ_EVENT_DATE_PRECISION},
             "S": {e["key"] for e in C.SIRAJ_EVENTS},
             "Src": {s["key"] for s in C.SOURCES}}
    for rel in C.RELATIONSHIPS:
        for end in (rel["subject"], rel["object"]):
            kind, _, key = end.partition(":")
            assert kind in kinds, end
            assert key in kinds[kind], end
    # showcases required by the spec
    assert any(r["type"] in ("employed_by", "member_of", "director_of")
               and r["subject"].startswith("P:")
               and r["object"].startswith("I:") for r in C.RELATIONSHIPS)
    assert any(r["type"] == "participated_in" for r in C.RELATIONSHIPS)
    assert any(r["object"].startswith("S:") for r in C.RELATIONSHIPS)
    assert any(r["subject"].startswith("U:") for r in C.RELATIONSHIPS)


def test_association_rows_resolve_and_carry_the_tag_field():
    kinds = {"P": {p["key"] for p in C.PERSONS},
             "I": {i["key"] for i in C.INSTITUTIONS},
             "Pl": {p["key"] for p in C.PLACES},
             "U": {u["key"] for u in C.UNITS},
             "S": {e["key"] for e in C.SIRAJ_EVENTS}}
    for row in C.ASSOCIATIONS:
        assert row["title"], row
        for ref in row["refs"].values():
            kind, _, key = ref.partition(":")
            assert kind in kinds and key in kinds[kind], ref
    # person↔org and person↔event link tables are populated
    assert any(r["dt"] == "Person Institution" for r in C.ASSOCIATIONS)
    assert any(r["dt"] == "Person Event" for r in C.ASSOCIATIONS)
    # every Person Event row points at a Siraj Event (the Link target)
    assert all(ref.startswith("S:")
               for r in C.ASSOCIATIONS if r["dt"] == "Person Event"
               for ref in [r["refs"]["event"]])


def test_family_showcase_dates_are_consistent():
    persons = {p["key"]: p for p in C.PERSONS}
    for key, fam in C.FAMILY.items():
        person = persons[key]
        assert fam["marital"] in ("Single", "Married")
        if fam["marital"] == "Single":
            assert not fam["children"] and not fam["grandchildren"]
            assert not fam["spouse"]
            continue
        assert fam["marriage"] > _date(person["byear"], 1, 1)
        child_names = set()
        for child in fam["children"]:
            assert child["birth"] > fam["marriage"]
            assert child["birth"] > _date(person["byear"], 1, 1)
            child_names.add(child["child_name"])
        for grand in fam["grandchildren"]:
            assert grand["through"] in child_names
            parent_birth = next(c["birth"] for c in fam["children"]
                                if c["child_name"] == grand["through"])
            assert grand["birth"] > parent_birth


def _date(year: int, month: int, day: int):
    import datetime as dt
    return dt.date(year, month, day)


# -- executor source contracts (AST) -------------------------------------

def _demo_ast() -> ast.Module:
    return ast.parse(DEMO_PY.read_text(encoding="utf-8"))


def _add_doctypes(tree: ast.Module) -> set[str]:
    found = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "_add"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            found.add(node.args[0].value)
    return found


def test_teardown_covers_every_seeded_doctype():
    tree = _demo_ast()
    seeded = _add_doctypes(tree)
    # dynamic doctype from content rows
    assoc_doctypes = {row["dt"] for row in C.ASSOCIATIONS}
    seeded |= assoc_doctypes
    # read TEARDOWN_ORDER + TAG_FIELDS literals from the module
    covered = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in ("TEARDOWN_ORDER",
                                                     "TAG_FIELDS")
                for t in node.targets):
            for elt in ast.walk(node.value):
                if (isinstance(elt, ast.Tuple) and elt.elts
                        and isinstance(elt.elts[0], ast.Constant)):
                    covered.add(elt.elts[0].value)
    missing = seeded - covered
    assert not missing, f"teardown does not cover: {sorted(missing)}"


def test_manifest_helpers_and_status_exist():
    tree = _demo_ast()
    names = {n.name for n in tree.body
             if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)}
    for required in ("seed_demo_data", "teardown_demo_data", "demo_status",
                     "_manifest_path", "_manifest_save", "_manifest_load",
                     "_manifest_clear"):
        assert required in names
    source = DEMO_PY.read_text(encoding="utf-8")
    assert 'MANIFEST_NAME = "siraj_demo_manifest.json"' in source
    assert "frappe.get_site_path" in source
    # units must be deleted deepest-first (on_trash blocks parents)
    assert "UNIT_DEPTH" in source


def test_no_rounding_in_executor():
    source = DEMO_PY.read_text(encoding="utf-8")
    assert "round(" not in source
    for bad in ("%.2f", ".2f)", "round("):
        assert bad not in source


# -- bench command surface ------------------------------------------------

def test_commands_module_exposes_spec_commands():
    source = COMMANDS_PY.read_text(encoding="utf-8")
    assert '@click.group("siraj-research")' in source
    assert 'commands = [siraj_research]' in source
    for cmd in ("load-demo-data", "remove-demo-data",
                "isolate-demo-data"):
        assert f'"{cmd}"' in source, cmd
    # commands must be listed in the module-level `commands` iterable
    tree = ast.parse(source)
    listed = None
    for node in tree.body:
        if (isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "commands"
                        for t in node.targets)):
            listed = node.value
    assert isinstance(listed, ast.List)
    assert any(isinstance(e, ast.Name) and e.id == "siraj_research"
               for e in listed.elts)


def test_loader_is_idempotent_by_construction():
    """Every top-level insert must pass an existence check (keyword args
    to _add, or an explicit db.get_value guard)."""
    tree = _demo_ast()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "_add"):
            # _add(doctype, values, **check) — check kwargs required
            assert node.keywords, (
                " _add call without existence-check kwargs (not idempotent)")
    source = DEMO_PY.read_text(encoding="utf-8")
    assert "frappe.db.get_value" in source  # relationship guard
    assert re.search(r"if .*exists|existing", source)
