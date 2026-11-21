"""Translation audits: reference-data Arabic quality + app locale CSV contract.

Pure functions (no frappe import) so CI can run them without a bench:

    from siraj_research.setup.translation_audit import (
        audit_reference_data, audit_locale_csv, extract_app_sources,
    )

`python -m siraj_research.setup.translation_audit` prints a report.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent

# Arabic script ranges (incl. presentation forms / supplementary)
ARABIC_RE = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]"
)
# Classic double-encoding mojibake of Arabic (UTF-8 read as Latin-1)
MOJIBAKE_RE = re.compile(r"(?:\u00D8[\u0080-\u00FF]){2,}|(?:\u00C3[\u0080-\u00FF]){2,}")
BIDI_RE = re.compile(r"[\u202A-\u202E\u2066-\u2069\u200E\u200F]")
PLACEHOLDER_RE = re.compile(r"\{\d+\}")
# Rows whose source IS the value (autoname masks, standards identifiers) —
# they must stay untranslated and are exempt from the Arabic checks.
CODELIKE_RE = re.compile(
    r"^(?=.*[#\d])([A-Za-z0-9\-./# ]+)$"  # PER-.####, MIL-UNIT-.YYYY-.####
    r"|^ISBN / ISSN$"
    r"|^[.\-\u2026 ]+$"  # punctuation-only ('...')
)


def needs_translation(source: str) -> bool:
    """Whether a source string must have an ar.csv row.

    Exempt: punctuation-only, single letters, snake_case ids (layer/field
    identifiers shown to power users), and code masks (CODELIKE_RE).
    """
    s = (source or "").strip()
    if not s or re.fullmatch(r"[\W_]+", s):
        return False
    if len(re.findall(r"[A-Za-z\u0600-\u06FF]", s)) < 2:
        return False
    if " " not in s and "_" in s:
        return False
    if CODELIKE_RE.match(s):
        return False
    return True


def audit_reference_data(base_dir: Path | None = None) -> list[tuple]:
    """Scan seed reference data for label_ar quality problems.

    Returns findings as (kind, file, code, value, expected_en).
    Kinds: missing, not_arabic, identical_to_en, mojibake, bidi_control,
    duplicate_ar_within_parent.
    """
    base = base_dir or (APP_DIR / "setup" / "reference_data")
    findings: list[tuple] = []
    for name in ("countries", "governorates", "districts", "admin_units"):
        path = base / f"{name}.json"
        if not path.exists():
            continue
        rows = json.loads(path.read_text(encoding="utf-8"))
        seen: dict[tuple, str] = {}
        for row in rows:
            code = row.get("code") or row.get("name") or "?"
            ar = (row.get("label_ar") or "").strip()
            en = (row.get("label_en") or "").strip()
            if not ar:
                findings.append(("missing", name, code, "", en))
                continue
            if not ARABIC_RE.search(ar):
                findings.append(("not_arabic", name, code, ar, en))
            if ar == en:
                findings.append(("identical_to_en", name, code, ar, en))
            if MOJIBAKE_RE.search(ar) or "\ufffd" in ar:
                findings.append(("mojibake", name, code, ar, en))
            if BIDI_RE.search(ar):
                findings.append(("bidi_control", name, code, repr(ar), en))
            parent = (
                row.get("country")
                or row.get("governorate")
                or row.get("parent")  # admin_units hierarchy
                or (row.get("code") or "").split("-")[0]
            )
            key = (parent, ar)
            if ar and key in seen:
                findings.append(
                    ("duplicate_ar_within_parent", name, f"{seen[key]},{code}", ar, en)
                )
            elif ar:
                seen[key] = code
    return findings


def extract_app_sources(app_dir: Path | None = None) -> set[str]:
    """Every translatable source string the app defines: __(...) in JS,
    _("...") in Python, plus DocType / report names and the module name."""
    root = app_dir or APP_DIR
    sources: set[str] = set()

    js_pats = [
        re.compile(r"__\(\s*'((?:[^'\\]|\\.)*)'"),
        re.compile(r'__\(\s*"((?:[^"\\]|\\.)*)"'),
        re.compile(r"__\(\s*`((?:[^`\\$]|\\.)*)`"),
    ]
    for path in root.rglob("*.js"):
        if "node_modules" in str(path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pat in js_pats:
            for raw in pat.findall(text):
                s = raw.replace("\\n", "\n").strip()
                if s and "${" not in s:
                    sources.add(s)

    py_pat = re.compile(
        r"(?<![\w_])_\(\s*\"((?:[^\"\\]|\\.)*)\""
        r"|(?<![\w_])_\(\s*'((?:[^'\\]|\\.)*)'"
    )
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in py_pat.finditer(text):
            s = (m.group(1) or m.group(2) or "").strip()
            if s:
                sources.add(s)

    for pattern, key in (
        ("doctype/*/*.json", "name"),
        ("report/*/*.json", "name"),
    ):
        for path in root.rglob(pattern):
            doc = json.loads(path.read_text(encoding="utf-8"))
            if doc.get(key):
                sources.add(doc[key])

    # DocType field labels / descriptions / select options / doctype descriptions
    for path in root.rglob("doctype/*/*.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(doc.get("description"), str) and doc["description"].strip():
            sources.add(doc["description"].strip())
        for field in doc.get("fields") or []:
            for key in ("label", "description"):
                value = field.get(key)
                if isinstance(value, str) and value.strip():
                    sources.add(value.strip())
            if field.get("fieldtype") == "Select" and field.get("options"):
                for option in str(field["options"]).split("\n"):
                    if option.strip():
                        sources.add(option.strip())

    # Insight widgets, onboarding, pages, workspace labels
    for path in root.rglob("number_card/*/*.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("label"):
            sources.add(doc["label"])
    for path in root.rglob("dashboard_chart/*/*.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(doc.get("chart_name"), str) and doc["chart_name"].strip():
            sources.add(doc["chart_name"].strip())
    for path in root.rglob("onboarding_step/*/*.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for key in ("name", "title", "description"):
            if isinstance(doc.get(key), str) and doc[key].strip():
                sources.add(doc[key].strip())
    for path in root.rglob("module_onboarding/*/*.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("name"):
            sources.add(doc["name"])
    for path in root.rglob("page/*/*.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("title"):
            sources.add(doc["title"])
    for path in root.rglob("workspace/*/*.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for link in doc.get("links") or []:
            if link.get("label"):
                sources.add(link["label"])
        for shortcut in doc.get("shortcuts") or []:
            if isinstance(shortcut, dict) and shortcut.get("label"):
                sources.add(shortcut["label"])

    sources.add("SIRAJ Research")  # module
    return {s for s in sources if needs_translation(s)}


def read_locale_csv(path: Path) -> list[tuple[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [
            (row[0], row[1])
            for row in csv.reader(f)
            if len(row) >= 2 and row[0].strip()
        ]


def audit_locale_csv(path: Path | None = None) -> list[tuple]:
    """Contract checks for <app>/translations/ar.csv.

    Kinds: empty_translation, no_arabic, identical, placeholder_mismatch,
    duplicate_source.
    """
    path = path or (APP_DIR / "translations" / "ar.csv")
    findings: list[tuple] = []
    seen: set[str] = set()
    for source, translation in read_locale_csv(path):
        if source in seen:
            findings.append(("duplicate_source", source, translation))
        seen.add(source)
        if not translation.strip():
            findings.append(("empty_translation", source, ""))
            continue
        if source == translation and not CODELIKE_RE.match(source):
            findings.append(("identical", source, translation))
        if not ARABIC_RE.search(translation) and not CODELIKE_RE.match(source):
            findings.append(("no_arabic", source, translation))
        if PLACEHOLDER_RE.findall(source) != PLACEHOLDER_RE.findall(translation):
            findings.append(("placeholder_mismatch", source, translation))
        if MOJIBAKE_RE.search(translation) or "\ufffd" in translation:
            findings.append(("mojibake", source, translation))
        if BIDI_RE.search(translation):
            findings.append(("bidi_control", source, translation))
    return findings


def coverage_gaps(app_dir: Path | None = None) -> set[str]:
    """Extracted sources with no row in ar.csv."""
    root = app_dir or APP_DIR
    locale = root / "translations" / "ar.csv"
    translated = {s for s, _ in read_locale_csv(locale)}
    return extract_app_sources(root) - translated


def audit_workspace_content(app_dir: Path | None = None) -> list[tuple]:
    """EditorJS header/paragraph blocks render raw (no __()), so every one
    must be bilingual (contain Arabic) for the workspace to read in Arabic."""
    root = app_dir or APP_DIR
    findings: list[tuple] = []
    for path in root.rglob("workspace/*/*.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        raw = doc.get("content") or ""
        if not isinstance(raw, str) or not raw.strip():
            continue
        try:
            blocks = json.loads(raw)
        except ValueError:
            findings.append(("content_not_json", path.name))
            continue
        for block in blocks if isinstance(blocks, list) else []:
            if not isinstance(block, dict):
                continue
            if block.get("type") not in ("header", "paragraph"):
                continue
            text = (block.get("data") or {}).get("text") or ""
            plain = re.sub(r"<[^>]+>", " ", text)
            if plain.strip() and not ARABIC_RE.search(plain):
                findings.append(("content_not_bilingual", path.name, plain[:70]))
    return findings


def main() -> int:
    ref = audit_reference_data()
    csv_issues = audit_locale_csv()
    gaps = coverage_gaps()
    content = audit_workspace_content()
    print(f"reference-data findings : {len(ref)}")
    for f in ref:
        print("   ", f)
    print(f"locale CSV findings      : {len(csv_issues)}")
    for f in csv_issues:
        print("   ", f)
    print(f"untranslated sources    : {len(gaps)}")
    for s in sorted(gaps):
        print("   ", repr(s))
    print(f"workspace content       : {len(content)}")
    for f in content:
        print("   ", f)
    return 0 if not (ref or csv_issues or gaps or content) else 1


if __name__ == "__main__":
    raise SystemExit(main())
