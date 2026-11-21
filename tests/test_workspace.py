"""Workspace integrity: every DocType is linked and every widget resolves.

The workspace is the app's front door — it must encompass every single
DocType (the user's standing requirement), and every block it renders must
reference a record that actually ships in the module tree. These checks run
pure-Python in CI so a newly added DocType cannot silently go missing from
the desk.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "siraj_research" / "siraj_research"
WS_PATH = APP / "workspace" / "siraj_research" / "siraj_research.json"


def _workspace() -> dict:
    return json.loads(WS_PATH.read_text(encoding="utf-8"))


def _content(workspace: dict) -> list[dict]:
    content = workspace.get("content")
    if isinstance(content, str):
        content = json.loads(content)
    return content or []


def _app_doctypes() -> set[str]:
    names = set()
    for path in (APP / "doctype").glob("*/*.json"):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if doc.get("doctype") == "DocType" and doc.get("name"):
            names.add(doc["name"])
    return names


def _module_json_names(kind: str) -> set[str]:
    """Names of shipped records for a module folder (number_card, ...)."""
    names = set()
    for path in (APP / kind).glob("*/*.json"):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if doc.get("name"):
            names.add(doc["name"])
    return names


def test_every_doctype_is_linked_from_the_workspace():
    workspace = _workspace()
    linked = {
        row.get("link_to")
        for row in workspace["links"]
        if row.get("type") == "Link" and row.get("link_type") == "DocType"
    }
    missing = sorted(_app_doctypes() - linked)
    assert not missing, (
        "DocTypes missing from the workspace links (add a Card Break section + Link row): "
        + ", ".join(missing)
    )


def test_no_duplicate_workspace_links():
    workspace = _workspace()
    rows = [r for r in workspace["links"] if r.get("type") == "Link"]
    seen, dupes = set(), []
    for row in rows:
        key = (row.get("link_type"), row.get("link_to"))
        if key in seen:
            dupes.append(key)
        seen.add(key)
    assert not dupes, f"duplicate workspace links: {dupes}"


def test_every_card_block_matches_a_card_break():
    workspace = _workspace()
    breaks = {
        r["label"] for r in workspace["links"] if r.get("type") == "Card Break"
    }
    for block in _content(workspace):
        if block.get("type") == "card":
            name = block.get("data", {}).get("card_name")
            assert name in breaks, f"card block references unknown Card Break: {name!r}"
    # every Card Break is rendered as a content card (no orphan sections)
    rendered = {
        b.get("data", {}).get("card_name")
        for b in _content(workspace)
        if b.get("type") == "card"
    }
    orphans = sorted(breaks - rendered)
    assert not orphans, f"Card Break sections without a content card: {orphans}"


def test_every_widget_reference_ships_a_record():
    workspace = _workspace()
    cards = _module_json_names("number_card")
    charts = _module_json_names("dashboard_chart")
    onboardings = _module_json_names("module_onboarding")
    for block in _content(workspace):
        typ = block.get("type")
        data = block.get("data") or {}
        if typ == "number_card":
            name = data.get("number_card_name")
            assert name in cards, f"number_card block without shipped Number Card: {name!r}"
        elif typ == "chart":
            name = data.get("chart_name")
            assert name in charts, f"chart block without shipped Dashboard Chart: {name!r}"
        elif typ == "onboarding":
            name = data.get("onboarding_name")
            assert name in onboardings, (
                f"onboarding block without shipped Module Onboarding: {name!r}"
            )
        elif typ == "shortcut":
            names = {s.get("label") for s in workspace.get("shortcuts") or []}
            assert data.get("shortcut_name") in names, (
                f"shortcut block without a shortcut row: {data.get('shortcut_name')!r}"
            )
    # child rows themselves must reference shipped documents
    for row in workspace.get("number_cards") or []:
        assert row.get("number_card_name") in cards, row
    for row in workspace.get("charts") or []:
        assert row.get("chart_name") in charts, row


def test_module_onboarding_steps_all_ship():
    """The onboarding checklist must reference real Onboarding Step records."""
    onboardings = list((APP / "module_onboarding").glob("*/*.json"))
    assert onboardings, "no Module Onboarding JSON shipped"
    steps = _module_json_names("onboarding_step")
    for path in onboardings:
        doc = json.loads(path.read_text(encoding="utf-8"))
        for row in doc.get("steps") or []:
            assert row.get("step") in steps, (
                f"{doc['name']} references missing Onboarding Step: {row.get('step')!r}"
            )
        assert doc.get("allow_roles"), f"{doc['name']} must allow roles"
        assert doc.get("module"), f"{doc['name']} must name a module"


def test_onboarding_steps_have_usable_actions():
    valid_actions = {
        "Create Entry", "Update Settings", "Show Form Tour", "View Report",
        "Go to Page", "View Docs", "Complete Onboarding",
    }
    count = 0
    for path in (APP / "onboarding_step").glob("*/*.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        count += 1
        assert doc.get("action") in valid_actions, doc.get("name")
        assert doc.get("title"), doc.get("name")
        action = doc["action"]
        if action == "Go to Page":
            assert doc.get("path"), f"{doc['name']}: Go to Page needs a path"
        elif action == "Create Entry":
            assert doc.get("reference_document"), f"{doc['name']}: Create Entry needs a DocType"
        elif action == "View Report":
            assert doc.get("reference_report"), f"{doc['name']}: View Report needs a report"
    assert count >= 5, f"onboarding feels thin: {count} steps"
