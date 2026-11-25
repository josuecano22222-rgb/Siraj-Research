"""Static AST check: every DocType test_*.py module defines all names it uses."""

from __future__ import annotations

import ast
import builtins
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCTYPE_TESTS = sorted(ROOT.glob("siraj_research/siraj_research/doctype/*/test_*.py"))


def _defined_names(tree: ast.Module) -> set[str]:
	defined: set[str] = set(dir(builtins)) | {"__name__", "__file__", "__package__", "__doc__"}
	for node in ast.walk(tree):
		if isinstance(node, ast.Import):
			for alias in node.names:
				defined.add(alias.asname or alias.name.split(".")[0])
		elif isinstance(node, ast.ImportFrom):
			for alias in node.names:
				if alias.name != "*":
					defined.add(alias.asname or alias.name)
		elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
			defined.add(node.name)
			if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
				for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs):
					defined.add(arg.arg)
				if node.args.vararg:
					defined.add(node.args.vararg.arg)
				if node.args.kwarg:
					defined.add(node.args.kwarg.arg)
		elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
			defined.add(node.id)
		elif isinstance(node, ast.ExceptHandler) and node.name:
			defined.add(node.name)
	return defined


class DocTypeTestImportsTest(unittest.TestCase):
	def test_all_doctype_tests_import_frappe_and_have_no_undefined_names(self):
		self.assertGreaterEqual(len(DOCTYPE_TESTS), 48)
		for path in DOCTYPE_TESTS:
			rel = path.relative_to(ROOT).as_posix()
			with self.subTest(file=rel):
				tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
				defined = _defined_names(tree)
				undefined = sorted(
					{
						node.id
						for node in ast.walk(tree)
						if isinstance(node, ast.Name)
						and isinstance(node.ctx, ast.Load)
						and node.id not in defined
					}
				)
				self.assertEqual(undefined, [], f"{rel} has undefined names: {undefined}")
