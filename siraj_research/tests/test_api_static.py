"""Static (non-bench) checks for SIRAJ API modules.

Run with:
    python -m pytest siraj_research/tests/test_api_static.py
or simply:
    python siraj_research/tests/test_api_static.py

These tests do not require a running bench / Frappe site; they only import
modules, parse source, and assert the whitelisted endpoints expose the
function signatures the Explorer depends on.
"""
import ast
import importlib.util
import os
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[2]
APP  = ROOT / "siraj_research"


def _parse(relpath):
    return ast.parse((APP / relpath).read_text())


def _has_whitelisted(tree, fn_name):
    """Return True iff `fn_name` is defined and decorated with @frappe.whitelist."""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == fn_name:
            for dec in node.decorator_list:
                # @frappe.whitelist or @frappe.whitelist()
                name = None
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                    name = dec.func.attr
                elif isinstance(dec, ast.Attribute):
                    name = dec.attr
                if name == "whitelist":
                    return True, node
    return False, None


def test_map_relations_endpoints_whitelisted():
    tree = _parse("api/map_relations.py")
    ok, node = _has_whitelisted(tree, "get_entity_network")
    assert ok, "get_entity_network must be @frappe.whitelist"
    args = [a.arg for a in node.args.args]
    assert "doctype" in args and "name" in args, "endpoint must take doctype, name"


def test_entity_profile_endpoint_whitelisted():
    tree = _parse("api/entity_profile.py")
    ok, node = _has_whitelisted(tree, "get_entity_profile")
    assert ok, "get_entity_profile must be @frappe.whitelist"
    args = [a.arg for a in node.args.args]
    assert "doctype" in args and "name" in args


def test_relationship_profile_endpoint_whitelisted():
    tree = _parse("api/relationship_profile.py")
    ok, node = _has_whitelisted(tree, "get_relationship_profile")
    assert ok, "get_relationship_profile must be @frappe.whitelist"
    args = [a.arg for a in node.args.args]
    assert "name" in args, "endpoint must take 'name'"


def test_audit_endpoint_whitelisted():
    """Regression: @frappe.whitelisted is a list, not the decorator.

    Using it as a decorator raises TypeError at import time and takes the
    whole bench test run down before any test executes.
    """
    tree = _parse("api/audit.py")
    ok, node = _has_whitelisted(tree, "document_history")
    assert ok, "document_history must be @frappe.whitelist (not .whitelisted)"
    args = [a.arg for a in node.args.args]
    assert "doctype" in args and "name" in args


def test_record_icons_tools_extended():
    # Must define the 23 new tool glyphs for goal 1.
    src = (APP / "record_icons.py").read_text()
    # Crude check: each key is present somewhere in TOOLS = { ... }
    required = [
        "ego", "link_add", "link_chain", "path", "hop1", "hop2", "hop3",
        "isolate", "pin_sel", "arrow", "inferred", "halo", "edge_filter",
        "edges_off", "edge_expand", "undo", "time", "funnel", "help",
        "list", "card", "eraser", "back",
    ]
    missing = [k for k in required if f"'{k}'" not in src and f'"{k}"' not in src]
    assert not missing, f"missing tool keys in record_icons.py: {missing}"


def test_hooks_js_bundle_order_explicit():
    """The audit script must load after the main bundle it enhances.

    JS ships as one esbuild bundle (hooks.py documents the rewrite); the
    legacy per-module names (siraj-record-meta.js, siraj-map/*.js) no
    longer exist and asserting them would pin a dead architecture.
    """
    src = (APP / "hooks.py").read_text()
    assert "app_include_js = [" in src
    bundle = src.find('"siraj.bundle.js"')
    audit = src.find('"siraj-audit.js"')
    assert bundle != -1 and audit != -1, "both scripts must be registered"
    assert bundle < audit, "siraj.bundle.js must load before siraj-audit.js"
    # Map/toolbar CSS keeps its cache-busting version suffix.
    assert "siraj-map-toolbar.css" in src
    assert "_CSS_VER" in src


def test_api_init_exists():
    assert (APP / "api/__init__.py").exists(), "api/ package needs __init__.py"


if __name__ == "__main__":
    tests = [v for k,v in list(globals().items()) if k.startswith("test_") and callable(v)]
    fails = 0
    for t in tests:
        try:
            t()
            print("PASS", t.__name__)
        except AssertionError as e:
            fails += 1
            print("FAIL", t.__name__, e)
    sys.exit(1 if fails else 0)
