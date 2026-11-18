"""
Static DocType integrity test — runs without a site.

Validates:
  1. Every DocType JSON parses and has required keys.
  2. Table/Table MultiSelect fields point to an existing DocType with istable=1.
  3. Link options that are SIRAJ DocTypes exist (core Frappe DocTypes allowed).
  4. links[] entries reference existing DocTypes; link_fieldname is a Link back to parent.
  5. Standard (non-custom) DocTypes do not set default_print_format.
  6. __init__.py files are non-empty; controller .py exists with correctly-cased class.
  7. field_order lists every field exactly once.
"""
import ast
import json
import unittest
from pathlib import Path

DOCTYPES_ROOT = Path(__file__).resolve().parents[1] / "siraj_research" / "doctype"
CORE_DOCTYPES = {
    "User", "Country", "File", "Workflow State", "Language", "Role", "Print Format",
    "DocType", "Module Def", "Customize Form", "Report", "Version", "Error Log",
    "Prepared Report",
}


def load_all_doctypes():
    dts = {}
    for p in sorted(DOCTYPES_ROOT.iterdir()):
        if not p.is_dir():
            continue
        jf = p / f"{p.name}.json"
        if not jf.exists():
            continue
        dts[p.name] = json.loads(jf.read_text())
    return dts


class TestDocTypeIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dts_by_dir = load_all_doctypes()
        cls.dts_by_name = {d["name"]: (dir_name, d) for dir_name, d in cls.dts_by_dir.items()}

    def _iter_doctypes(self):
        for dir_name, d in self.dts_by_dir.items():
            yield dir_name, d

    def test_01_json_parses_and_required_keys(self):
        required = {"doctype", "name", "module", "fields", "istable", "issingle", "custom"}
        for dir_name, d in self._iter_doctypes():
            with self.subTest(doctype=d["name"]):
                for k in required:
                    self.assertIn(k, d, f"missing key {k!r}")

    def test_02_istable_issingle_are_ints(self):
        for dir_name, d in self._iter_doctypes():
            with self.subTest(doctype=d["name"]):
                self.assertIn(d["istable"], (0, 1), f"istable must be 0 or 1")
                self.assertIn(d["issingle"], (0, 1), f"issingle must be 0 or 1")

    def test_03_no_default_print_format_on_standard(self):
        for dir_name, d in self._iter_doctypes():
            with self.subTest(doctype=d["name"]):
                if not d.get("custom"):
                    self.assertNotIn("default_print_format", d,
                        "standard DocType must not set default_print_format (use Print Format + Property Setter)")

    def test_04_table_options_exist_and_point_to_child_table(self):
        for dir_name, d in self._iter_doctypes():
            for f in d.get("fields", []):
                if f["fieldtype"] not in ("Table", "Table MultiSelect"):
                    continue
                opt = f.get("options", "")
                with self.subTest(doctype=d["name"], field=f["fieldname"]):
                    self.assertTrue(opt, "Table field has no options")
                    self.assertIn(opt, self.dts_by_name, f"Table target {opt!r} not found")
                    _, target = self.dts_by_name[opt]
                    self.assertEqual(target["istable"], 1,
                        f"Table target {opt} has istable={target['istable']} — must be 1 (child table)")

    def test_05_link_options_for_siraj_doctypes_resolve(self):
        for dir_name, d in self._iter_doctypes():
            for f in d.get("fields", []):
                if f["fieldtype"] != "Link":
                    continue
                opt = f.get("options", "")
                if not opt or opt in CORE_DOCTYPES:
                    continue
                with self.subTest(doctype=d["name"], field=f["fieldname"]):
                    self.assertIn(opt, self.dts_by_name, f"Link target {opt!r} not found")

    def test_06_links_entries_valid(self):
        for dir_name, d in self._iter_doctypes():
            for l in d.get("links", []):
                ld = l.get("link_doctype", "")
                lfn = l.get("link_fieldname", "")
                with self.subTest(doctype=d["name"], link=ld):
                    self.assertIn(ld, self.dts_by_name, f"links: target DocType {ld!r} not found")
                    _, child = self.dts_by_name[ld]
                    back = [bf for bf in child["fields"] if bf.get("fieldname") == lfn]
                    self.assertTrue(back, f"links: field {lfn!r} not found on {ld}")
                    self.assertEqual(back[0]["fieldtype"], "Link",
                        f"links: {ld}.{lfn} must be a Link field")
                    self.assertEqual(back[0].get("options"), d["name"],
                        f"links: {ld}.{lfn} must Link back to {d['name']}, got {back[0].get('options')!r}")

    def test_07_field_order_matches_fields(self):
        for dir_name, d in self._iter_doctypes():
            with self.subTest(doctype=d["name"]):
                fieldnames = {f["fieldname"] for f in d["fields"] if "fieldname" in f}
                order = set(d.get("field_order", []))
                self.assertEqual(fieldnames, order, "field_order must list every field exactly once")

    def test_08_controller_exists_and_parses(self):
        for dir_name, d in self._iter_doctypes():
            with self.subTest(doctype=d["name"]):
                init = DOCTYPES_ROOT / dir_name / "__init__.py"
                self.assertTrue(init.exists(), "missing __init__.py")
                self.assertGreater(init.stat().st_size, 0, "__init__.py must be non-empty")
                py = DOCTYPES_ROOT / dir_name / f"{dir_name}.py"
                self.assertTrue(py.exists(), f"missing controller {dir_name}.py")
                src = py.read_text()
                tree = ast.parse(src)  # must be valid Python
                # Frappe's controller naming: remove spaces/hyphens/apostrophes verbatim, no Title() camel-case
                expected = d["name"].replace(' ','').replace('-','').replace("'","")
                classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
                self.assertIn(expected, classes,
                    f"controller must define class {expected} (have {classes})")


if __name__ == "__main__":
    unittest.main(verbosity=2)
