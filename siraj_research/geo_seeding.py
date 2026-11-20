"""Resumable, batch-oriented seeding for the administrative hierarchy.

This module is the operational layer used by the ``bench geo`` commands:

``seed-levels``   Admin Level catalogue + per-country Country Level Config rows
``seed-core``     level catalogue → countries → reference hierarchy → ancestry
``import-csv``    custom local CSV/GeoJSON rows in parent-to-child order
``audit``         structural audit with a rejection report
``backfill-ancestry``  recompute ``ancestry_path`` for existing rows

Design rules
------------
* **Parent-first.** Levels are always processed 1 → 5; a child is never
  written before its parent exists.
* **Idempotent.** Existing rows are counted, not duplicated. Codes are unique.
* **Resumable.** Every batch commits and writes a checkpoint (JSON) with the
  processed offset; pass ``offset=`` to continue an interrupted run.
* **Honest.** Rows that cannot be linked are *rejected with a reason*
  (``orphaned_parent``, ``duplicate_code``, ``invalid_geometry`` …), written to
  a CSV report, and counted in the final summary.
* **Pure where possible.** CSV/GeoJSON parsing, validation and the report
  writer do not import Frappe, so they are covered by the pure-Python suite.
"""

from __future__ import annotations

import csv
import io
import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any

try:  # pragma: no cover - exercised inside a bench
    import frappe
except Exception:  # pragma: no cover - pure-Python tests
    frappe = None  # type: ignore[assignment]

from siraj_research.geo_levels import (
    DEFAULT_LEVELS,
    default_rows,
    level_spec,
    normalise_rows,
)

REFERENCE_LEVEL_CONFIGS = Path(__file__).parent / "setup" / "reference_data" / "level_configs.json"
REPORT_HEADERS = ("row", "level", "code", "reason", "detail")
MAX_CODE_LENGTH = 140
_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,139}$")

HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "code": ("code", "pcode", "id", "p_code"),
    "name_en": ("name_en", "label_en", "name", "english_name", "name_english"),
    "name_local": ("name_local", "label_ar", "name_ar", "local_name", "arabic_name"),
    "parent_code": ("parent_code", "parent", "parent_pcode", "parent_id"),
    "latitude": ("latitude", "lat", "centroid_lat"),
    "longitude": ("longitude", "lng", "lon", "long", "centroid_lng"),
    "source": ("source", "source_kind", "provenance"),
    "admin_level_type": ("admin_level_type", "type", "level_type"),
    "is_active": ("is_active", "active", "enabled"),
}


# ---------------------------------------------------------------------------
# Pure parsing / validation
# ---------------------------------------------------------------------------

def _first(row: dict[str, Any], names: tuple[str, ...]) -> str:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _parse_float(value: str, limit: float) -> float | None:
    if value in ("", None):
        return None
    try:
        number = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        raise ValueError("not_a_number")
    if number < -limit or number > limit:
        raise ValueError("out_of_range")
    return number


def parse_hierarchy_csv(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse a hierarchy CSV into ``(rows, rejections)``.

    Headers are matched case-insensitively through :data:`HEADER_ALIASES`, so
    exports from OCHA COD, GADM, GeoNames or a hand-made spreadsheet work
    without renaming columns. A UTF-8 BOM and semicolon/comma delimiters are
    accepted.
    """
    text = (text or "").lstrip("\ufeff")
    sample = text[:4096]
    delimiter = ","
    if sample:
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
        except csv.Error:
            if sample.count(";") > sample.count(","):
                delimiter = ";"
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        return [], [{"row": 0, "reason": "empty_file", "detail": "no header row"}]
    normalised_headers = {
        (name or "").strip().lower().replace(" ", "_"): name for name in reader.fieldnames
    }
    rows: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for index, raw in enumerate(reader, start=2):
        if not any(str(value or "").strip() for value in raw.values()):
            continue
        mapped: dict[str, str] = {}
        for key, aliases in HEADER_ALIASES.items():
            for alias in aliases:
                if alias in normalised_headers:
                    value = raw.get(normalised_headers[alias])
                    if value not in (None, ""):
                        mapped[key] = str(value).strip()
                    break
        code = mapped.get("code", "")
        name_en = mapped.get("name_en", "")
        if not code:
            rejections.append({"row": index, "code": "", "reason": "missing_code",
                               "detail": "a stable code/pcode is required"})
            continue
        if not _CODE_RE.match(code):
            rejections.append({"row": index, "code": code, "reason": "invalid_code",
                               "detail": "use letters/digits and . _ : - only"})
            continue
        if code.upper() in seen_codes:
            rejections.append({"row": index, "code": code, "reason": "duplicate_code",
                               "detail": "row repeated within the file"})
            continue
        seen_codes.add(code.upper())
        if not name_en:
            rejections.append({"row": index, "code": code, "reason": "missing_name_en",
                               "detail": "name_en / label_en / name is required"})
            continue
        try:
            lat = _parse_float(mapped.get("latitude", ""), 90)
            lng = _parse_float(mapped.get("longitude", ""), 180)
        except ValueError as exc:
            rejections.append({"row": index, "code": code, "reason": "invalid_coordinates",
                               "detail": str(exc)})
            continue
        if (lat is None) != (lng is None):
            rejections.append({"row": index, "code": code, "reason": "invalid_coordinates",
                               "detail": "provide both latitude and longitude or neither"})
            continue
        rows.append(
            {
                "row": index,
                "code": code,
                "name_en": name_en,
                "name_local": mapped.get("name_local", ""),
                "parent_code": mapped.get("parent_code", ""),
                "latitude": lat,
                "longitude": lng,
                "source": mapped.get("source", "") or "manual",
                "admin_level_type": mapped.get("admin_level_type", ""),
                "is_active": mapped.get("is_active", "").strip().lower() not in ("0", "false", "no"),
            }
        )
    return rows, rejections


def parse_hierarchy_geojson(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse a GeoJSON FeatureCollection of Points into the same row shape.

    Properties use the same aliases as the CSV importer. Non-point features are
    rejected (polygons belong in ``Boundary Dataset`` imports).
    """
    try:
        payload = json.loads(text or "{}")
    except json.JSONDecodeError as exc:
        return [], [{"row": 0, "reason": "invalid_geojson", "detail": str(exc)}]
    features = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(features, list):
        return [], [{"row": 0, "reason": "invalid_geojson", "detail": "expected a FeatureCollection"}]
    rows: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, feature in enumerate(features, start=1):
        properties = {str(k).lower(): v for k, v in (feature.get("properties") or {}).items()}
        geometry = feature.get("geometry") or {}
        if geometry.get("type") != "Point":
            rejections.append({"row": index, "reason": "unsupported_geometry",
                               "detail": geometry.get("type") or "missing"})
            continue
        coordinates = geometry.get("coordinates") or []
        if len(coordinates) < 2:
            rejections.append({"row": index, "reason": "invalid_geometry", "detail": "Point needs two coordinates"})
            continue
        properties.setdefault("longitude", coordinates[0])
        properties.setdefault("latitude", coordinates[1])
        mapped = {
            key: _first(properties, aliases)
            for key, aliases in HEADER_ALIASES.items()
        }
        code = mapped.get("code", "")
        if not code or not mapped.get("name_en"):
            rejections.append({"row": index, "code": code, "reason": "missing_code_or_name",
                               "detail": "properties must carry code and name_en"})
            continue
        if code.upper() in seen:
            rejections.append({"row": index, "code": code, "reason": "duplicate_code", "detail": "within file"})
            continue
        seen.add(code.upper())
        try:
            lat = _parse_float(mapped.get("latitude", ""), 90)
            lng = _parse_float(mapped.get("longitude", ""), 180)
        except ValueError as exc:
            rejections.append({"row": index, "code": code, "reason": "invalid_coordinates", "detail": str(exc)})
            continue
        rows.append(
            {
                "row": index,
                "code": code,
                "name_en": mapped.get("name_en"),
                "name_local": mapped.get("name_local", ""),
                "parent_code": mapped.get("parent_code", ""),
                "latitude": lat,
                "longitude": lng,
                "source": mapped.get("source", "") or "manual",
                "admin_level_type": mapped.get("admin_level_type", ""),
                "is_active": mapped.get("is_active", "").strip().lower() not in ("0", "false", "no"),
            }
        )
    return rows, rejections


class SeedSession:
    """Counters, rejections and a resumable checkpoint for one seeding run."""

    def __init__(self, name: str, report_dir: str | Path | None = None):
        self.name = name
        self.report_dir = Path(report_dir) if report_dir else None
        self.started = time.time()
        self.created = Counter()
        self.existing = Counter()
        self.rejected = Counter()
        self.processed = Counter()
        self.rejections: list[dict[str, Any]] = []
        self.notes: list[str] = []
        self.checkpoint: dict[str, Any] = {"offset": 0, "updated_at": None}

    def note(self, message: str) -> None:
        self.notes.append(str(message))
        print(f"[{self.name}] {message}")

    def count(self, key: str, created: int = 0, existing: int = 0) -> None:
        if created:
            self.created[key] += int(created)
        if existing:
            self.existing[key] += int(existing)
        self.processed[key] += int(created) + int(existing)

    def reject(self, row: Any, reason: str, detail: str = "", level: int | str | None = None,
               code: str | None = None) -> None:
        index = row.get("row") if isinstance(row, dict) else row
        code = code or (row.get("code") if isinstance(row, dict) else None)
        self.rejected[str(reason)] += 1
        if len(self.rejections) < 10000:
            self.rejections.append(
                {
                    "row": index or "",
                    "level": level if level is not None else (row.get("level") if isinstance(row, dict) else ""),
                    "code": code or "",
                    "reason": reason,
                    "detail": detail,
                }
            )

    def summary(self) -> dict[str, Any]:
        return {
            "session": self.name,
            "duration_s": round(time.time() - self.started, 2),
            "processed": dict(self.processed),
            "created": dict(self.created),
            "existing": dict(self.existing),
            "rejected": dict(self.rejected),
            "rejections_total": sum(self.rejected.values()),
            "checkpoint": dict(self.checkpoint),
            "notes": list(self.notes),
            "rejection_report": str(self.report_path) if self.report_path else None,
        }

    @property
    def report_path(self) -> Path | None:
        if self.report_dir is None:
            return None
        self.report_dir.mkdir(parents=True, exist_ok=True)
        return self.report_dir / f"{self.name}-rejections.csv"

    def write_report(self) -> str | None:
        path = self.report_path
        if path is None:
            return None
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(REPORT_HEADERS))
            writer.writeheader()
            for row in self.rejections:
                writer.writerow({key: row.get(key, "") for key in REPORT_HEADERS})
        return str(path)

    # -- checkpoint ---------------------------------------------------------
    def checkpoint_path(self) -> Path | None:
        if self.report_dir is None:
            return None
        return self.report_dir / f"{self.name}-checkpoint.json"

    def save_checkpoint(self, **values: Any) -> str | None:
        self.checkpoint.update(values)
        self.checkpoint["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        path = self.checkpoint_path()
        if path is None:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.checkpoint, indent=2), encoding="utf-8")
        return str(path)

    @staticmethod
    def load_checkpoint(path: str | Path) -> dict[str, Any]:
        p = Path(path)
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}


# ---------------------------------------------------------------------------
# Frappe-side seeding
# ---------------------------------------------------------------------------

def _require_frappe() -> None:
    if frappe is None:
        raise RuntimeError("siraj_research.geo_seeding requires a Frappe bench for seeding")


def _country_name(value: str | None) -> str | None:
    """Resolve an ISO code or country name to the Frappe Country document name."""
    if not value:
        return None
    text = str(value).strip()
    found = frappe.db.exists("Country", {"code": text.upper()}) or frappe.db.exists("Country", text)
    if found:
        return found
    # Country names are unique in Frappe, but a case mismatch is common.
    found = frappe.db.get_value("Country", {"country_name": text})
    return found


def seed_admin_levels() -> dict[str, Any]:
    """Create the six ``Admin Level`` rows (idempotent)."""
    _require_frappe()
    session = SeedSession("admin-levels")
    for spec in DEFAULT_LEVELS:
        level = int(spec["level"])
        existing = frappe.db.exists("Admin Level", {"level": level})
        if existing:
            session.count("Admin Level", existing=1)
            continue
        doc = frappe.get_doc(
            {
                "doctype": "Admin Level",
                "level": level,
                "level_key": spec["key"],
                "doctype_name": spec["doctype"],
                "prefix": spec["prefix"],
                "default_label_en": spec["label_en"],
                "default_label_ar": spec["label_ar"],
                "parent_level": level - 1 if level else None,
                "sort_order": level * 10,
                "is_optional": 1 if level else 0,
                "description": f"Canonical level {level}: {spec['label_en']}",
            }
        )
        doc.insert(ignore_permissions=True)
        session.count("Admin Level", created=1)
    return session.summary()


def load_level_config_reference() -> list[dict[str, Any]]:
    """Read the shipped per-country level configuration reference file."""
    if not REFERENCE_LEVEL_CONFIGS.exists():
        return []
    payload = json.loads(REFERENCE_LEVEL_CONFIGS.read_text(encoding="utf-8"))
    return list(payload.get("countries") or [])


def seed_country_level_configs(
    reference: list[dict[str, Any]] | None = None,
    *,
    overwrite: bool = False,
    report_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Create per-country configurations from the reference file.

    Existing configurations are preserved unless ``overwrite=True`` — operator
    edits always win over the shipped defaults.
    """
    _require_frappe()
    session = SeedSession("country-level-configs", report_dir)
    for entry in reference if reference is not None else load_level_config_reference():
        code = entry.get("country_code") or entry.get("country")
        country = _country_name(code)
        if not country:
            session.reject({"row": code, "code": code}, "unknown_country", str(code))
            continue
        existing = frappe.db.exists("Country Level Config", {"country": country})
        if existing and not overwrite:
            session.count("Country Level Config", existing=1)
            continue
        rows = default_rows()
        depth = entry.get("hierarchy_depth")
        overrides = normalise_rows(entry.get("levels"))
        for row in rows:
            override = overrides.get(int(row["level"]), {})
            row["label_en"] = override.get("label_en") or row["label_en"]
            row["label_ar"] = override.get("label_ar") or row["label_ar"]
            row["is_active"] = int(override.get("is_active", 1))
            row["skip_reason"] = override.get("skip_reason", "")
            if depth is not None and int(row["level"]) > int(depth):
                row["is_active"] = 0
        if existing:
            doc = frappe.get_doc("Country Level Config", existing)
            doc.levels = []
        else:
            doc = frappe.new_doc("Country Level Config")
        doc.country = country
        doc.hierarchy_depth = int(depth) if depth is not None else 5
        doc.source_reference = entry.get("reference") or "SIRAJ level configs v1"
        doc.notes = entry.get("notes") or ""
        for row in rows:
            doc.append("levels", row)
        if existing:
            doc.save(ignore_permissions=True)
            session.count("Country Level Config", existing=1)
        else:
            doc.insert(ignore_permissions=True)
            session.count("Country Level Config", created=1)
    report = session.write_report()
    summary = session.summary()
    summary["rejection_report"] = report
    return summary


def seed_core(
    country: str | None = None,
    *,
    with_reference: bool = True,
    report_dir: str | Path | None = None,
) -> dict[str, Any]:
    """The "core data" install: levels → configurations → reference hierarchy.

    Order matters: level definitions and country configurations exist before
    any hierarchy rows are validated against them. ``country`` limits the
    reference hierarchy seed only; the catalogue and configurations are
    global.
    """
    _require_frappe()
    session = SeedSession("seed-core", report_dir)
    session.note("1/4 Admin Level catalogue")
    levels = seed_admin_levels()
    session.note(f"    created {levels['created']} / existing {levels['existing']}")

    session.note("2/4 Country Level Configurations")
    configs = seed_country_level_configs(report_dir=report_dir)
    session.note(f"    created {configs['created']} / existing {configs['existing']}")

    if with_reference:
        session.note("3/4 Reference hierarchy (countries, governorates, districts, admin units)")
        from siraj_research.setup.master_data import seed_master_data

        reference = seed_master_data()
        session.created["master_data"] = sum(reference.get("created", {}).values())
        session.existing["master_data"] = sum(reference.get("existing", {}).values())
        for example in reference.get("skip_examples") or []:
            session.reject(
                {"row": example.get("code"), "code": example.get("code")},
                example.get("reason") or "skipped",
                level=example.get("doctype"),
            )
    else:
        session.note("3/4 Reference hierarchy skipped (--no-reference)")

    session.note("4/4 Ancestry backfill")
    ancestry = backfill_ancestry()
    session.note(f"    updated {ancestry.get('updated', 0)} rows")

    report = session.write_report()
    summary = session.summary()
    summary["rejection_report"] = report
    summary["steps"] = {"levels": levels, "configs": configs, "ancestry": ancestry}
    return summary


def _resolve_parent(
    level: int,
    row: dict[str, Any],
    country_name: str | None,
    created_by_code: dict[str, str],
) -> tuple[str | None, str | None, str | None]:
    """Return ``(parent_name, parent_doctype, reason)`` for a CSV row."""
    if level == 1:
        if not country_name:
            return None, "Country", "orphaned_parent: country missing"
        return country_name, "Country", None
    parent_spec = level_spec(level - 1)
    parent_doctype = str(parent_spec["doctype"])
    code = str(row.get("parent_code") or "").strip()
    if not code:
        return None, parent_doctype, "orphaned_parent: parent_code required"
    name = created_by_code.get(code.upper())
    if not name:
        name = frappe.db.get_value(parent_doctype, {"code": code}, "name")
    if not name:
        return None, parent_doctype, f"orphaned_parent: {parent_doctype} {code} not found"
    if country_name:
        parent_country = frappe.db.get_value(parent_doctype, name, "country")
        if parent_country and parent_country != country_name:
            return None, parent_doctype, (
                f"orphaned_parent: {parent_doctype} {code} belongs to {parent_country}"
            )
    return name, parent_doctype, None


def import_hierarchy_rows(
    rows: list[dict[str, Any]],
    level: int,
    *,
    country: str | None = None,
    source_kind: str = "Imported",
    source_dataset: str | None = None,
    batch_size: int = 500,
    offset: int = 0,
    dry_run: bool = False,
    report_dir: str | Path | None = None,
    session_name: str = "hierarchy-import",
) -> dict[str, Any]:
    """Insert parsed rows for one level, parent-first, in bounded batches."""
    _require_frappe()
    spec = level_spec(level)
    if not spec or int(spec["level"]) < 1:
        raise ValueError("level must be 1…5")
    level = int(spec["level"])
    doctype = str(spec["doctype"])
    parent_field = str(spec["parent_field"])
    country_name = _country_name(country) if country else None
    if level == 1 and not country_name:
        raise ValueError("country is required for level 1")
    if country and not country_name:
        raise ValueError(f"unknown country: {country}")

    session = SeedSession(session_name, report_dir)
    created_by_code: dict[str, str] = {}
    batch = 0
    processed = 0
    for row in rows[offset:]:
        parent_name, _parent_doctype, reason = _resolve_parent(level, row, country_name, created_by_code)
        if reason:
            session.reject(row, reason.split(":")[0], reason, level=level, code=row.get("code"))
            continue
        code = row["code"]
        if frappe.db.exists(doctype, {"code": code}):
            existing = frappe.db.get_value(doctype, {"code": code}, "name")
            created_by_code[code.upper()] = existing
            session.count(doctype, existing=1)
            processed += 1
            continue
        values = {
            "doctype": doctype,
            "code": code,
            "label_en": row["name_en"],
            "label_ar": row.get("name_local") or row["name_en"],
            "pcode": code,
            "sort_order": 100,
            "disabled": 0,
            "is_active": 1 if row.get("is_active", True) else 0,
            "source_kind": source_kind,
            parent_field: parent_name,
        }
        if country_name:
            values["country"] = country_name
        if row.get("latitude") is not None:
            values["latitude"] = row["latitude"]
            values["longitude"] = row["longitude"]
        if row.get("admin_level_type"):
            values["admin_level_type"] = row["admin_level_type"]
        if source_dataset:
            values["source_dataset"] = source_dataset
        if dry_run:
            session.count(doctype, created=1)
            processed += 1
            continue
        try:
            doc = frappe.get_doc(values)
            doc.insert(ignore_permissions=True)
            created_by_code[code.upper()] = doc.name
            session.count(doctype, created=1)
        except Exception as exc:
            frappe.db.rollback()
            session.reject(row, "insert_failed", str(exc)[:500], level=level, code=code)
            continue
        processed += 1
        batch += 1
        if batch >= max(1, int(batch_size)):
            frappe.db.commit()
            batch = 0
            session.save_checkpoint(offset=offset + processed, level=level, doctype=doctype)
            session.note(f"{doctype}: {processed} rows processed")
    if not dry_run:
        frappe.db.commit()
    session.save_checkpoint(offset=offset + processed, level=level, doctype=doctype, done=True)
    report = session.write_report()
    summary = session.summary()
    summary["rejection_report"] = report
    summary["doctype"] = doctype
    summary["level"] = level
    summary["dry_run"] = bool(dry_run)
    return summary


def import_hierarchy_file(
    path: str,
    level: int,
    *,
    country: str | None = None,
    fmt: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Import a CSV or GeoJSON file of one level (``bench geo import-csv``)."""
    _require_frappe()
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    text = p.read_text(encoding="utf-8-sig")
    fmt = (fmt or p.suffix.lstrip(".")).lower()
    if fmt in ("geojson", "json"):
        rows, rejections = parse_hierarchy_geojson(text)
    else:
        rows, rejections = parse_hierarchy_csv(text)
    report_dir = kwargs.pop("report_dir", None)
    summary = import_hierarchy_rows(
        rows,
        level,
        country=country,
        report_dir=report_dir,
        session_name=f"import-{p.stem}",
        **kwargs,
    )
    if rejections:
        session = SeedSession(f"import-{p.stem}-parse", report_dir)
        for rejection in rejections:
            session.reject(rejection, rejection.get("reason", "parse_error"), rejection.get("detail", ""), level=level)
        session.write_report()
        summary["parse_rejections"] = len(rejections)
        summary["parse_rejection_report"] = str(session.report_path) if session.report_path else None
    return summary


# ---------------------------------------------------------------------------
# Ancestry backfill and audit
# ---------------------------------------------------------------------------

def _label_maps() -> dict[str, dict[str, dict[str, str]]]:
    """Load ``{doctype: {name: {label_en, label_ar}}}`` for all levels."""
    maps: dict[str, dict[str, dict[str, str]]] = {}
    for spec in DEFAULT_LEVELS[1:]:
        doctype = str(spec["doctype"])
        rows = frappe.get_all(
            doctype,
            fields=["name", "label_en", "label_ar"],
            limit_page_length=0,
        )
        maps[doctype] = {row["name"]: row for row in rows}
    return maps


def backfill_ancestry(batch_size: int = 500, levels: list[int] | None = None) -> dict[str, Any]:
    """Recompute ``ancestry_path``/``ancestry_labels``/``hierarchy_level``.

    Runs parent-first so a child reads its parent's already-updated labels.
    Uses ``db.set_value`` (not ``doc.save``) so legacy rows with historical
    inconsistencies can still get an accurate denormalised path; the audit is
    the place that reports those inconsistencies.
    """
    _require_frappe()
    from siraj_research.geo_lineage import build_ancestry

    wanted = levels or [1, 2, 3, 4, 5]
    maps = _label_maps()
    updated = 0
    scanned = 0
    for level in wanted:
        spec = level_spec(level)
        if not spec:
            continue
        doctype = str(spec["doctype"])
        parent_fields = [str(level_spec(i)["field"]) for i in range(0, level)]
        fields = ["name", "country", "label_en", "label_ar", *parent_fields]
        fields = list(dict.fromkeys(fields))
        rows = frappe.get_all(doctype, fields=fields, limit_page_length=0)
        for index, row in enumerate(rows, start=1):
            values = {field: row.get(field) for field in parent_fields}
            labels = {
                field: maps.get(str(level_spec(i)["doctype"]), {}).get(row.get(field), {})
                for i, field in enumerate(parent_fields)
                if i > 0
            }
            labels[str(level_spec(level)["field"])] = {
                "en": row.get("label_en"),
                "ar": row.get("label_ar"),
            }
            ancestry = build_ancestry(doctype, values, labels=labels)
            frappe.db.set_value(
                doctype,
                row["name"],
                {
                    "ancestry_path": ancestry["path"],
                    "ancestry_labels": ancestry["labels"],
                    "hierarchy_level": ancestry["level"],
                },
                update_modified=False,
            )
            updated += 1
            scanned += 1
            if index % max(1, int(batch_size)) == 0:
                frappe.db.commit()
        frappe.db.commit()
    return {"updated": updated, "scanned": scanned, "levels": wanted}


def audit_hierarchy(
    country: str | None = None,
    *,
    report_dir: str | Path | None = None,
    session_name: str = "hierarchy-audit",
) -> dict[str, Any]:
    """Structural audit with a CSV rejection report.

    Checks skipped levels, chain holes, parent/child country mismatches and
    malformed boundary geometry. Read-only: nothing is repaired here.
    """
    _require_frappe()
    from siraj_research.geo_levels import country_config, validate_chain

    session = SeedSession(session_name, report_dir)
    country_name = _country_name(country) if country else None
    if country and not country_name:
        session.reject({"row": country, "code": country}, "unknown_country", str(country))
    configs: dict[str, dict[str, Any]] = {}

    for level in (1, 2, 3, 4, 5):
        spec = level_spec(level)
        doctype = str(spec["doctype"])
        parent_fields = [str(level_spec(i)["field"]) for i in range(0, level)]
        fields = list(dict.fromkeys(["name", "code", "country", "disabled", "label_en", *parent_fields]))
        filters = {"country": country_name} if country_name else None
        rows = frappe.get_all(doctype, filters=filters, fields=fields, limit_page_length=0)
        for row in rows:
            session.count(doctype, existing=1)
            values = {field: row.get(field) for field in parent_fields}
            config = configs.get(str(row.get("country")))
            if config is None:
                config = country_config(row.get("country"))
                configs[str(row.get("country"))] = config
            for error in validate_chain(config["levels"], values, own_field=str(spec["field"])):
                session.reject(
                    row,
                    error["code"],
                    error["message"],
                    level=level,
                    code=row.get("code") or row["name"],
                )

    # Geometry sanity: hex payloads that cannot be decoded are reported once
    # per child row rather than crashing an import later.
    if frappe.db.exists("DocType", "Admin Boundary Geom"):
        geoms = frappe.get_all(
            "Admin Boundary Geom",
            fields=["parent", "precision", "geom_wkb_hex"],
            limit_page_length=0,
        )
        for geom in geoms:
            payload = str(geom.get("geom_wkb_hex") or "")
            if payload and not re.fullmatch(r"[0-9A-Fa-f]+", payload):
                session.reject(
                    {"row": geom.get("parent"), "code": geom.get("parent")},
                    "invalid_geometry",
                    f"{geom.get('precision')} WKB is not hexadecimal",
                )

    report = session.write_report()
    summary = session.summary()
    summary["rejection_report"] = report
    summary["country"] = country_name
    summary["passed"] = not session.rejected
    return summary


def seed_geographic_administration(limit: int = 500, report_dir: str | Path | None = None) -> dict[str, Any]:
    """Create ``Geographic Administration`` rows for existing hierarchical records.

    Safe to re-run: rows are keyed by a deterministic code. Used by the demo
    seed and by operators who retro-fit the Link target on an existing site.
    """
    _require_frappe()
    from siraj_research.geo_admin import ensure_for_values

    session = SeedSession("geographic-administration", report_dir)
    for level in (1, 2, 3, 4, 5):
        spec = level_spec(level)
        doctype = str(spec["doctype"])
        parent_fields = [str(level_spec(i)["field"]) for i in range(0, level)]
        rows = frappe.get_all(
            doctype,
            fields=list(dict.fromkeys(["name", "code", "country", "source_kind", *parent_fields])),
            limit_page_length=max(1, int(limit)),
        )
        for row in rows:
            values = {field: row.get(field) for field in parent_fields}
            try:
                result = ensure_for_values(
                    values,
                    source="core" if row.get("source_kind") else "manual",
                )
            except Exception as exc:  # pragma: no cover - defensive
                session.reject(row, "ensure_failed", str(exc)[:300], level=level, code=row.get("code"))
                continue
            session.count("Geographic Administration", created=int(bool(result.get("created"))),
                          existing=int(not result.get("created")))
    report = session.write_report()
    summary = session.summary()
    summary["rejection_report"] = report
    return summary
