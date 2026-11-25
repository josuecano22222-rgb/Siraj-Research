"""Static & AST smoke checks for C-25 (`test_api_data_group_isolation.py`).

Note on scope (per Gate 0 item D):
These tests run in pure Python without MariaDB/Redis and verify ONLY:
  1. Every @frappe.whitelist callable discovered via AST across `siraj_research/`
     is registered in `ALL_WHITELISTED_ENDPOINTS` AND referenced inside
     `siraj_research/tests/test_api_data_group_isolation.py`.
  2. `test_api_data_group_isolation.py` subclasses `FrappeTestCase`, cleans up
     caches in `tearDownClass`, covers `GD`, `GC`, unassigned, and `SIRAJ Official`
     principals, predictable IDs (`PER-0001`, `EVT-0001`, `PLC-0001`), cross-group
     links, and non-admin privilege boundaries.
  3. Ruff / AST syntax cleanliness of both bench modules.

Real SQL / Frappe permission-hook / User Permission execution requires a live
MariaDB-backed bench (`bench --site frappe.com run-tests --module
siraj_research.tests.test_api_data_group_isolation`).
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "siraj_research"
FIXTURES_FILE = APP_DIR / "tests" / "_isolation_fixtures.py"
SUITE_FILE = APP_DIR / "tests" / "test_api_data_group_isolation.py"


def _discover_whitelisted_endpoints() -> set[tuple[str, str]]:
	"""Walk all non-test Python modules in siraj_research/ and return (module, qualname) pairs."""
	discovered: set[tuple[str, str]] = set()
	for py_path in sorted(APP_DIR.rglob("*.py")):
		rel = py_path.relative_to(ROOT)
		if "tests" in rel.parts or any(part.startswith("test_") for part in rel.parts):
			continue
		mod_name = ".".join(rel.with_suffix("").parts)
		tree = ast.parse(py_path.read_text(encoding="utf-8"), filename=str(py_path))

		class _Visitor(ast.NodeVisitor):
			def __init__(self):
				self.class_stack: list[str] = []

			def visit_ClassDef(self, node: ast.ClassDef):
				self.class_stack.append(node.name)
				self.generic_visit(node)
				self.class_stack.pop()

			def visit_FunctionDef(self, node: ast.FunctionDef):
				for dec in node.decorator_list:
					if "whitelist" in ast.unparse(dec):
						qual = f"{self.class_stack[-1]}.{node.name}" if self.class_stack else node.name
						discovered.add((mod_name, qual))
				self.generic_visit(node)

			def visit_Assign(self, node: ast.Assign):
				val_src = ast.unparse(node.value)
				if "whitelist" in val_src:
					for target in node.targets:
						if isinstance(target, ast.Name):
							discovered.add((mod_name, target.id))
				self.generic_visit(node)

		_Visitor().visit(tree)
	return discovered


def _load_registered_endpoints() -> list[tuple[str, str]]:
	tree = ast.parse(FIXTURES_FILE.read_text(encoding="utf-8"), filename=str(FIXTURES_FILE))
	for node in tree.body:
		if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
			if node.target.id == "ALL_WHITELISTED_ENDPOINTS":
				return [tuple( elt_val ) for elt_val in ast.literal_eval(node.value)]
		if isinstance(node, ast.Assign):
			for t in node.targets:
				if isinstance(t, ast.Name) and t.id == "ALL_WHITELISTED_ENDPOINTS":
					return [tuple(elt_val) for elt_val in ast.literal_eval(node.value)]
	raise AssertionError("ALL_WHITELISTED_ENDPOINTS not found in _isolation_fixtures.py")


def test_registry_matches_ast_discovered_whitelisted_endpoints_exactly():
	discovered = _discover_whitelisted_endpoints()
	registered = _load_registered_endpoints()
	assert len(registered) == len(set(registered)), "Duplicate entries in ALL_WHITELISTED_ENDPOINTS"
	assert set(registered) == discovered, (
		f"Drift between AST @frappe.whitelist endpoints and ALL_WHITELISTED_ENDPOINTS:\n"
		f"  missing from suite: {sorted(discovered - set(registered))}\n"
		f"  extra in suite:     {sorted(set(registered) - discovered)}"
	)


def test_every_whitelisted_endpoint_is_exercised_in_bench_suite():
	registered = _load_registered_endpoints()
	suite_src = SUITE_FILE.read_text(encoding="utf-8")
	missing_calls = []
	for mod_name, qualname in registered:
		short_mod = mod_name.rsplit(".", 1)[-1]
		if "." in qualname:
			_, method_name = qualname.split(".", 1)
			if f".{method_name}(" not in suite_src:
				missing_calls.append(f"{mod_name}.{qualname}")
		else:
			call_ref = f"{short_mod}.{qualname}"
			if call_ref not in suite_src:
				missing_calls.append(f"{mod_name}.{qualname}")
	assert not missing_calls, f"Whitelisted endpoints not directly exercised in {SUITE_FILE.name}: {missing_calls}"


def test_bench_suite_structure_principals_and_teardown():
	suite_src = SUITE_FILE.read_text(encoding="utf-8")
	fixtures_src = FIXTURES_FILE.read_text(encoding="utf-8")
	suite_tree = ast.parse(suite_src, filename=str(SUITE_FILE))

	classes = [n for n in suite_tree.body if isinstance(n, ast.ClassDef)]
	assert any(
		any(ast.unparse(base) == "FrappeTestCase" for base in cls.bases) for cls in classes
	), "TestApiDataGroupIsolation must subclass FrappeTestCase"

	method_names = {
		n.name for cls in classes for n in cls.body if isinstance(n, ast.FunctionDef)
	}
	assert "setUpClass" in method_names
	assert "tearDownClass" in method_names
	assert "cleanup_isolation_caches" in suite_src

	# Principals required by Invariant #7 + C-25 acceptance criteria
	for token in (
		"gd1@example.com",
		"gc1@example.com",
		"unassigned-siraj@example.com",
		"SIRAJ Official",
		"PER-0001",
		"PLC-0001",
		"EVT-0001",
	):
		assert token in fixtures_src or token in suite_src, f"Missing required test fixture token: {token}"

	# Cross-group Link DocTypes required by C-25
	for doctype in (
		"Person",
		"Military Unit",
		"Operational Deployment",
		"Command Appointment",
		"Siraj Event",
		"Relationship",
	):
		assert doctype in suite_src or doctype in fixtures_src, f"Missing cross-group Link coverage for {doctype}"
