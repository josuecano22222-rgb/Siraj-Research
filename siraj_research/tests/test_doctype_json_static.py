"""Static, framework-independent tests for DocType JSON schema validity.

These run in the pure-Python gate (no Frappe site, no bench) so that structural
defects in the app's DocType JSON definitions are caught before they ever reach
``bench --site test_site run-tests``.

The motivating defect: ``search_fields`` in a DocType JSON must be a comma
separated *string* (e.g. ``"name, status, source"``). Frappe expects a string and
a list value (e.g. ``["name", "status"]``) blows up at import/sync time with a
``ValidationError``/``TypeError`` during site sync, which only surfaced on the
Server CI job. By asserting the type statically here, this whole class of defect
fails fast in the pure-Python gate instead of at test-run time.
"""

from __future__ import annotations

import json
import os
import unittest

# Resolve the app root without importing frappe. This file lives at
# <repo>/siraj_research/tests/<name>.py, so the app package root is one level up.
# DocType definitions live under siraj_research/siraj_research/doctype/<name>/.
_HERE = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.abspath(os.path.join(_HERE, os.pardir))
_DOCTYPE_DIR = os.path.join(_APP_ROOT, "siraj_research", "doctype")


def _doctype_json_files():
    """Return every ``<name>.json`` DocType definition under the doctype dir."""
    if not os.path.isdir(_DOCTYPE_DIR):
        return []
    found = []
    for name in sorted(os.listdir(_DOCTYPE_DIR)):
        d = os.path.join(_DOCTYPE_DIR, name)
        if not os.path.isdir(d):
            continue
        # DocType JSON is conventionally <name>.json inside its own directory.
        candidate = os.path.join(d, name + ".json")
        if os.path.isfile(candidate):
            found.append(candidate)
    return found


class TestDocTypeSearchFieldsStatic(unittest.TestCase):
    """Static gate: every DocType JSON's search_fields, if present, is a string."""

    def test_doctype_json_files_exist(self):
        """Sanity: the static scan actually discovered DocType JSONs."""
        files = _doctype_json_files()
        self.assertTrue(
            files,
            f"No DocType JSON files found under {_DOCTYPE_DIR} — path resolution broken?",
        )

    def test_search_fields_is_string_when_present(self):
        """``search_fields``, when present, must be a string (not a list)."""
        checked = 0
        for path in _doctype_json_files():
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
            if "search_fields" not in doc:
                continue
            checked += 1
            sf = doc["search_fields"]
            self.assertIsInstance(
                sf,
                str,
                msg=(
                    f"{os.path.relpath(path, _APP_ROOT)}: 'search_fields' must be a "
                    f"comma-separated string, got {type(sf).__name__} ({sf!r}). "
                    "Frappe expects a string; a list value fails site sync."
                ),
            )
        # Guard against the scan silently matching nothing meaningful.
        self.assertGreater(
            checked,
            0,
            "No DocType JSON carried 'search_fields' — scan may be too narrow.",
        )

    def test_search_fields_string_is_non_empty_when_present(self):
        """A string ``search_fields`` must not be empty/whitespace-only."""
        for path in _doctype_json_files():
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
            sf = doc.get("search_fields")
            if isinstance(sf, str):
                self.assertTrue(
                    sf.strip(),
                    msg=f"{os.path.relpath(path, _APP_ROOT)}: 'search_fields' is an empty string.",
                )


if __name__ == "__main__":
    unittest.main()
