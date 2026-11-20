"""Display/API contract checks that do not need a bench."""

import ast
from pathlib import Path

from siraj_research.geo_hierarchy_ui import format_chain

ROOT = Path(__file__).resolve().parents[1]


def _levels():
    return [
        {"field": "country", "status": "linked", "label_en": "Iraq",
         "label_ar_value": "العراق"},
        {"field": "governorate", "status": "linked", "label_en": "Baghdad",
         "label_ar_value": "بغداد"},
        {"field": "district", "status": "gap", "label": "District",
         "label_ar": "القضاء"},
        {"field": "municipality", "status": "gap", "label": "Municipality",
         "label_ar": "البلدية"},
    ]


def test_text_chain_skips_gaps_and_never_prints_level_names():
    result = {"levels": _levels()}
    assert format_chain(result, language="en") == "Iraq › Baghdad"
    assert format_chain(result, language="ar") == "العراق › بغداد"
    assert "District" not in format_chain(result, language="en")


def test_text_chain_is_empty_when_nothing_resolved():
    assert format_chain({"levels": _levels()[2:]}, language="en") == ""


def test_resolve_location_is_whitelisted_and_throttled():
    source = (ROOT / "siraj_research" / "api" / "geo_resolve.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    func = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "resolve_location"
    )
    decorators = " ".join(ast.unparse(node) for node in func.decorator_list)
    assert "frappe.whitelist()" in decorators
    body = ast.unparse(func)
    assert "guard('resolve_location')" in body or 'guard("resolve_location")' in body
    assert "has_permission('Place', 'read')" in body or 'has_permission("Place", "read")' in body
    for key in ("invalid_coordinates", "out_of_range", "unresolved",
                "unresolved_reason", "geographic_administration", "text_en", "text_ar"):
        assert key in body


def test_webform_cascade_is_dimension_free_and_local():
    path = ROOT / "siraj_research" / "public" / "js" / "siraj-cascade-webform.js"
    text = path.read_text(encoding="utf-8")
    assert "SirajWebFormCascade" in text
    for marker in ("http://", "https://", "//cdn", "unpkg.com"):
        assert marker not in text
    hooks = (ROOT / "siraj_research" / "hooks.py").read_text(encoding="utf-8")
    assert "siraj-cascade-webform.js" in hooks
