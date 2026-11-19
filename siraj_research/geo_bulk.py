"""Scalable bulk seeding for the global administrative hierarchy.

The app ships a curated reference layer (249 countries, ~4k first-level
units, plus sampled lower levels). Larger open datasets are imported in
bounded batches so a single RQ job never has to hold a country-sized file in
memory:

============  ======================================  =========================
Source        Format                                  Entry point
============  ======================================  =========================
SIRAJ ref.    ``setup/reference_data/*.json``         ``import_reference_hierarchy``
GADM          GeoPackage / shapefile / GeoJSON        ``import_gadm``
GeoNames      ``cities15000.zip`` / ``admin*.txt``    ``import_geonames``
OSM           Geofabrik PBF → GeoJSON via osmium      ``import_osm``
============  ======================================  =========================

Every importer writes through a ``Boundary Dataset`` row, reports progress
on that row, commits once per batch and bumps ``index_version`` at the end
so the in-worker STRtree cache rebuilds. Failed batches are inspectable and
safe to resume: set the dataset's ``last_processed_offset`` to the last
successful batch and rerun with that offset.
"""

from __future__ import annotations

import csv
import io
import json
import subprocess
import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

try:  # pragma: no cover - bench only
    import frappe
except Exception:  # pragma: no cover - pure-Python tests
    frappe = None  # type: ignore[assignment]

from siraj_research.geo_hierarchy import LEVELS, make_code, normalize_code, upsert_level


def _ensure_dataset(code: str, *, label_en: str, source: str, level: int = 0,
                    license_id: str = "ODbL-1.0", url: str = "",
                    is_gazetteer: bool = False) -> str:
    if frappe is None:
        return code
    if frappe.db.exists("Boundary Dataset", code):
        return code
    doc = frappe.get_doc({
        "doctype": "Boundary Dataset",
        "code": code,
        "label_en": label_en,
        "label_ar": label_en,
        "source": source,
        "license_id": license_id,
        "url": url,
        "level": int(level),
        "import_status": "Pending",
        "import_progress": 0,
        "feature_count": 0,
        "last_processed_offset": 0,
    })
    doc.insert(ignore_permissions=True)
    return code


def _progress(dataset: str, *, count: int, offset: int, total: int | None = None) -> None:
    if frappe is None:
        return
    values = {
        "feature_count": count,
        "last_processed_offset": offset,
        "import_progress": min(99, int(count / max(total or 1, 1) * 100)),
    }
    frappe.db.set_value("Boundary Dataset", dataset, values, update_modified=False)
    frappe.db.commit()


def _finish(dataset: str, count: int, note: str) -> dict:
    if frappe is None:
        return {"dataset": dataset, "count": count, "note": note, "complete": True}
    values = frappe.db.get_value("Boundary Dataset", dataset,
                                 ["index_version", "import_log"], as_dict=True) or {}
    previous = getattr(values, "import_log", "") or ""
    frappe.db.set_value("Boundary Dataset", dataset, {
        "import_status": "Complete",
        "import_progress": 100,
        "feature_count": count,
        "last_processed_offset": count,
        "imported_at": frappe.utils.now(),
        "index_version": int(getattr(values, "index_version", 0) or 0) + 1,
        "import_log": (previous + "\n" if previous else "") + note,
    }, update_modified=False)
    frappe.db.commit()
    return {"dataset": dataset, "count": count, "note": note, "complete": True}


def _country_cache() -> dict[str, str]:
    if frappe is None:
        return {}
    rows = frappe.get_all("Country", fields=["name", "code"], limit_page_length=0)
    return {str(r["code"]).upper(): r["name"] for r in rows if r.get("code")}


# ---------------------------------------------------------------------------
# Curated reference layer
# ---------------------------------------------------------------------------

def import_reference_hierarchy() -> dict:
    """Rerun the additive core seeding; safe on an existing site."""
    from siraj_research.setup.master_data import seed_master_data
    return seed_master_data()


# ---------------------------------------------------------------------------
# GeoNames point gazetteer
# ---------------------------------------------------------------------------

GEONAMES_COLUMNS = (
    "geonameid", "name", "asciiname", "alternatenames", "latitude", "longitude",
    "feature_class", "feature_code", "country_code", "cc2", "admin1_code",
    "admin2_code", "admin3_code", "admin4_code", "population", "elevation",
    "dem", "timezone", "modification_date",
)


def parse_geonames_line(line: str) -> dict | None:
    """Parse one tab-separated GeoNames export line (no external deps)."""
    parts = line.rstrip("\n").split("\t")
    if len(parts) < 19:
        return None
    try:
        lat, lon = float(parts[4]), float(parts[5])
    except ValueError:
        return None
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return None
    row = dict(zip(GEONAMES_COLUMNS, parts, strict=False))
    cc = str(row.get("country_code") or "").upper()
    a1 = str(row.get("admin1_code") or "").strip()
    a2 = str(row.get("admin2_code") or "").strip()
    a3 = str(row.get("admin3_code") or "").strip()
    a4 = str(row.get("admin4_code") or "").strip()
    a1_code = f"{cc}.{a1}" if a1 else None
    a2_code = f"{a1_code}.{a2}" if a1_code and a2 else None
    # GeoNames frequently leaves a higher code empty while filling a lower
    # one. Build the deepest chain available instead of dropping the row.
    a3_code = None
    if a3:
        a3_code = f"{a2_code}.{a3}" if a2_code else (f"{a1_code}.{a3}" if a1_code else a3)
    a4_code = None
    if a4:
        for base in (a3_code, a2_code, a1_code):
            if base:
                a4_code = f"{base}.{a4}"
                break
        a4_code = a4_code or a4
    return {
        "source_id": str(row.get("geonameid") or "")[:120],
        "name_en": (row.get("name") or "")[:140],
        "asciiname": (row.get("asciiname") or "")[:140],
        "feature_code": (row.get("feature_code") or "")[:16],
        "latitude": lat,
        "longitude": lon,
        "elevation_m": _int_or_none(row.get("elevation")),
        "population": _int_or_none(row.get("population")),
        "cc2": (row.get("cc2") or "")[:140],
        "timezone": (row.get("timezone") or "")[:64],
        "modification_date": (row.get("modification_date") or "")[:10] or None,
        "country_code": cc,
        "admin1_pcode": a1_code,
        "admin2_pcode": a2_code,
        "admin3_pcode": a3_code,
        "admin4_pcode": a4_code,
    }


def _int_or_none(value: Any) -> int | None:
    try:
        return int(float(value)) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _iter_geonames_lines(source: Path, member_hint: str = "cities") -> Iterable[tuple[str, str]]:
    """Stream GeoNames text lines from a zip **or a plain directory**.

    A directory avoids needing ``zip``/``unzip`` on a minimal bench and lets
    operators keep ``allCountries.txt``, ``admin1CodesASCII.txt`` and
    ``admin2Codes.txt`` side by side. A zip still works for single-file
    exports such as ``cities15000.zip``.
    """
    path = Path(source)
    if path.is_dir():
        candidates = sorted(p for p in path.glob("*.txt") if p.is_file())
        if member_hint:
            preferred = [p for p in candidates if member_hint.lower() in p.name.lower()]
            candidates = preferred or candidates
        for member in candidates:
            with member.open("r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    yield member.name, line
        return
    with zipfile.ZipFile(path) as zf:
        candidates = [n for n in zf.namelist() if n.lower().endswith(".txt")]
        if member_hint:
            preferred = [n for n in candidates if member_hint.lower() in n.lower()]
            candidates = preferred or candidates
        for name in candidates:
            with zf.open(name) as fh:
                wrapper = io.TextIOWrapper(fh, encoding="utf-8", errors="replace")
                for line in wrapper:
                    yield name, line


def _bulk_insert_gazetteer(dataset: str, rows: list[dict]) -> int:
	if not rows or frappe is None:
		return 0
	import hashlib

	now = frappe.utils.now()
	user = frappe.session.user or "Administrator"
	columns = [
		"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx",
		"dataset", "source_id", "name_en", "asciiname", "feature_code",
		"latitude", "longitude", "elevation_m", "population", "cc2",
		"timezone", "modification_date", "country", "admin1_pcode", "admin2_pcode",
	]
	values = []
	for row in rows:
		key = ":".join(str(row.get(k) or "") for k in
		               ("source_id", "name_en", "latitude", "longitude"))
		values.append([
			f"GEO-{hashlib.sha1(key.encode('utf-8')).hexdigest()[:20]}",
			user, now, now, user, 0, 0,
			*[row.get(col) for col in columns[7:]],
		])
	frappe.db.bulk_insert("Gazetteer Place", columns, values, ignore_duplicates=True)
	return len(rows)


def import_geonames(zip_path: str, dataset_code: str = "GEONAMES-CITIES", *,
                    country_codes: Iterable[str] | None = None,
                    batch_size: int = 1000, offset: int = 0,
                    member_hint: str = "cities") -> dict:
    """Stream a GeoNames zip into ``Gazetteer Place`` rows.

    ``zip_path`` may also be a directory of plain ``*.txt`` GeoNames files.
    ``country_codes`` accepts ISO-2 codes. ``offset`` skips that many valid
    lines so a failed run can resume without re-reading the whole archive.
    """
    path = Path(zip_path)
    if not path.exists():
        raise FileNotFoundError(str(path))
    _ensure_dataset(dataset_code, label_en="GeoNames populated places",
                    source="GeoNames (geonames.org)", license_id="CC-BY-4.0",
                    url="https://www.geonames.org/export/", is_gazetteer=True)
    wanted = {str(c).upper() for c in country_codes} if country_codes else None
    countries = _country_cache()
    batch: list[dict] = []
    seen: set[str] = set()
    count = skipped = 0
    for _member, line in _iter_geonames_lines(path, member_hint):
        if line.startswith("#") or not line.strip():
            continue
        row = parse_geonames_line(line)
        if not row:
            continue
        if wanted and row["country_code"] not in wanted:
            continue
        key = f"{dataset_code}:{row['source_id'] or row['name_en']}:{row['latitude']}:{row['longitude']}"
        if key in seen:
            continue
        seen.add(key)
        if skipped < offset:
            skipped += 1
            continue
        row["dataset"] = dataset_code
        row["country"] = countries.get(row.pop("country_code"))
        batch.append(row)
        if len(batch) >= batch_size:
            count += _bulk_insert_gazetteer(dataset_code, batch)
            batch = []
            seen = set()
            _progress(dataset_code, count=count, offset=count + skipped)
    if batch:
        count += _bulk_insert_gazetteer(dataset_code, batch)
    return _finish(dataset_code, count, f"GeoNames {path.name} (members: {member_hint})")


# ---------------------------------------------------------------------------
# GeoNames administrative divisions → editable hierarchy
# ---------------------------------------------------------------------------

GEONAMES_ADMIN_LEVELS = {
	"admin1": (1, "Governorate", "country"),
	"admin2": (2, "District", "governorate"),
	"admin3": (3, "Municipality", "district"),
	"admin4": (4, "Village", "municipality"),
	"admin5": (5, "Community", "village"),
}
GEONAMES_ADMIN_FEATURE_LEVELS = {"ADM3": 3, "ADM4": 4, "ADM5": 5}


def parse_geonames_admin_line(line: str, *, level: int) -> dict | None:
	"""Parse ``admin1CodesASCII.txt`` / ``admin2Codes.txt`` rows."""
	parts = line.rstrip("\n").split("\t")
	if len(parts) < 4:
		return None
	code = parts[0].strip()
	if not code or "." not in code:
		return None
	return {
		"pcode": code,
		"name_en": (parts[1] or parts[2] or code)[:140],
		"source_id": str(parts[3] or "")[:120],
		"level": level,
		"country_code": code.split(".")[0].upper(),
	}


def choose_admin_parent(level: int, parent_pcode: str | None,
                        name_by_pcode: dict[str, str],
                        countries: dict[str, str]) -> tuple[str | None, str, int]:
    """Pick the nearest available parent when an intermediate level is absent.

    GeoNames often fills ``admin4_code`` while leaving ``admin3_code`` empty.
    Rather than dropping the village, we attach it to the deepest known
    ancestor (district, governorate, or country). This keeps the hierarchy
    honest: a skipped level is represented by a missing Link, not a fake row.
    """
    if level == 1:
        code = str(parent_pcode or "").split(".")[0].upper()
        return countries.get(code), "country", 0
    if not parent_pcode:
        return None, str(LEVELS[max(0, level - 1)]["field"]), level - 1
    parts = str(parent_pcode).split(".")
    for ancestor_level in range(level - 1, 0, -1):
        if len(parts) < ancestor_level + 1:
            continue
        candidate = ".".join(parts[: ancestor_level + 1])
        name = name_by_pcode.get(normalize_code(candidate))
        if name:
            return name, str(LEVELS[ancestor_level]["field"]), ancestor_level
    return countries.get(parts[0].upper()), "country", 0


def import_geonames_admin(zip_path: str, dataset_code: str = "GEONAMES-ADMIN", *,
                          country_codes: Iterable[str] | None = None,
                          batch_size: int = 500,
                          include_all_countries: bool = True) -> dict:
	"""Create hierarchy rows from GeoNames admin1/2 codes and ADM3/4/5 features.

	This is the step that fills the levels the curated reference layer only
	samples. ``admin1CodesASCII.txt`` and ``admin2Codes.txt`` provide level 1/2;
	``allCountries.txt`` feature codes ``ADM3``, ``ADM4`` and ``ADM5`` provide
	the lower levels. Parent rows that are missing are skipped rather than
	invented, and the skipped count is reported.

	Use ``country_codes`` to process one or a few countries when a full global
	allCountries archive is too large for the worker.
	"""
	path = Path(zip_path)
	if not path.exists():
		raise FileNotFoundError(str(path))
	_ensure_dataset(dataset_code, label_en="GeoNames administrative divisions",
	                source="GeoNames (geonames.org) admin codes", license_id="CC-BY-4.0",
	                url="https://www.geonames.org/export/", level=0)
	wanted = {str(c).upper() for c in country_codes} if country_codes else None
	countries = _country_cache()
	name_by_pcode: dict[str, str] = {}
	count = 0
	processed = 0
	missing_parents = 0
	levels_seen: set[int] = set()
	feature_seen: dict[str, int] = {}

	def _put(level: int, pcode: str, parent_pcode: str | None,
	         name_en: str, source_id: str | None = None) -> bool:
		nonlocal count, processed, missing_parents
		spec = LEVELS[level]
		parent_name, parent_field, parent_level = choose_admin_parent(
			level, parent_pcode, name_by_pcode, countries)
		if not parent_name:
			missing_parents += 1
			return False
		ancestors = {"country": countries.get(str(pcode).split(".")[0].upper())}
		ancestors = {k: v for k, v in ancestors.items() if v}
		if parent_pcode:
			parts = str(parent_pcode).split(".")
			for ancestor_level in range(1, parent_level + 1):
				candidate = ".".join(parts[: ancestor_level + 1])
				ancestor_name = name_by_pcode.get(normalize_code(candidate))
				if ancestor_name:
					ancestors[str(LEVELS[ancestor_level]["field"])] = ancestor_name
		normalised = normalize_code(pcode)
		entry = {
			"doctype": spec["doctype"],
			"level": level,
			"field": spec["field"],
			"pcode": pcode,
			"code": make_code(pcode, name_en, normalize_code(parent_pcode), level),
			"label_en": name_en,
			"parent_code": normalize_code(parent_pcode),
			"parent_field": parent_field,
			"ancestor_codes": ancestors,
			"source": "geonames_admin",
			"admin_level_type": f"GeoNames level {level}",
		}
		result = upsert_level(entry, parent_name, dataset=dataset_code)
		if result.get("name"):
			name_by_pcode[normalised] = result["name"]
			levels_seen.add(level)
			processed += 1
			count += 1
			return True
		missing_parents += 1
		return False

	for admin_name, level in (("admin1CodesASCII", 1), ("admin2Codes", 2)):
		for _member, line in _iter_geonames_lines(path, admin_name):
			if line.startswith("#") or not line.strip():
				continue
			row = parse_geonames_admin_line(line, level=level)
			if not row:
				continue
			cc = row["country_code"]
			if wanted and cc not in wanted:
				continue
			if cc not in countries:
				missing_parents += 1
				continue
			if level == 1:
				# Pass the code itself so choose_admin_parent can read the ISO prefix.
				name_by_pcode[normalize_code(countries[cc])] = countries[cc]
				parent_pcode = row["pcode"]
			else:
				parent_pcode = row["pcode"].rsplit(".", 1)[0]
			_put(level, row["pcode"], parent_pcode, row["name_en"], row["source_id"])
			if processed % batch_size == 0 and processed:
				_progress(dataset_code, count=processed, offset=processed)

	if include_all_countries:
		for _member, line in _iter_geonames_lines(path, "allCountries"):
			if line.startswith("#") or not line.strip():
				continue
			row = parse_geonames_line(line)
			if not row:
				continue
			level = GEONAMES_ADMIN_FEATURE_LEVELS.get(row["feature_code"])
			if not level:
				continue
			cc = row["country_code"]
			if wanted and cc not in wanted:
				continue
			feature_seen[row["feature_code"]] = feature_seen.get(row["feature_code"], 0) + 1
			if level == 3:
				pcode = row["admin3_pcode"]
				parent_pcode = row["admin2_pcode"] or row["admin1_pcode"]
			elif level == 4:
				pcode = row["admin4_pcode"]
				parent_pcode = (row["admin3_pcode"] or row["admin2_pcode"]
				                or row["admin1_pcode"])
			else:
				pcode = row["source_id"]
				parent_pcode = (row["admin4_pcode"] or row["admin3_pcode"]
				                or row["admin2_pcode"] or row["admin1_pcode"])
			if not pcode or not parent_pcode:
				missing_parents += 1
				continue
			_put(level, pcode, parent_pcode, row["name_en"], row["source_id"])
			if processed % batch_size == 0 and processed:
				_progress(dataset_code, count=processed, offset=processed)

	return {**_finish(dataset_code, processed, f"GeoNames admin divisions from {path.name}"),
	        "levels": sorted(levels_seen), "missing_parents": missing_parents,
	        "admin_features_seen": feature_seen}


def enqueue_geonames_admin(zip_path: str, dataset_code: str = "GEONAMES-ADMIN",
                           *, country_codes: Iterable[str] | None = None,
                           batch_size: int = 500) -> dict:
    """Run :func:`import_geonames_admin` in the long worker for global files."""
    if frappe is None:
        return {"queued": False, "reason": "frappe unavailable"}
    frappe.enqueue(
        import_geonames_admin, queue="long", timeout=6 * 60 * 60,
        zip_path=zip_path, dataset_code=dataset_code,
        country_codes=list(country_codes or []), batch_size=batch_size,
        job_id=f"siraj-geonames-admin:{dataset_code}",
    )
    return {"queued": True, "dataset": dataset_code}


# ---------------------------------------------------------------------------
# GADM / OSM polygon datasets
# ---------------------------------------------------------------------------

def import_gadm(dataset_code: str, file_path: str, level: int,
                *, enqueue: bool = True, sync_hierarchy: bool = True,
                license_id: str = "CC-BY-NC-SA-4.0") -> dict:
    """Queue a GADM layer, then create hierarchy rows from its polygons."""
    _ensure_dataset(dataset_code, label_en=f"GADM level {level}",
                    source="GADM (gadm.org)", level=int(level), license_id=license_id,
                    url="https://gadm.org/data.html")
    return _queue_polygon_import(dataset_code, file_path, level, enqueue=enqueue,
                                 sync_hierarchy=sync_hierarchy)


def import_osm(dataset_code: str, file_path: str, level: int,
               *, enqueue: bool = True, sync_hierarchy: bool = True) -> dict:
    """Queue an OSM-derived boundary layer, then sync hierarchy rows.

    Raw ``.osm.pbf`` files must first be converted with :func:`osm_commands`.
    """
    _ensure_dataset(dataset_code, label_en=f"OSM administrative level {level}",
                    source="OpenStreetMap contributors", level=int(level),
                    license_id="ODbL-1.0", url="https://www.openstreetmap.org/copyright")
    return _queue_polygon_import(dataset_code, file_path, level, enqueue=enqueue,
                                 sync_hierarchy=sync_hierarchy)


def import_and_sync_boundary_job(dataset_name: str, file_path_str: str, level: int,
                                 *, sync_hierarchy: bool = True,
                                 levels: Iterable[int] | None = None) -> dict:
    """Long-worker entry point: import polygons, then materialise DocTypes."""
    from siraj_research.geo_import import import_boundary_job
    import_boundary_job(dataset_name, file_path_str, is_gazetteer=False)
    if not sync_hierarchy:
        return {"dataset": dataset_name, "imported": True, "synced": False}
    from siraj_research.geo_hierarchy import sync_hierarchy_from_boundaries
    return sync_hierarchy_from_boundaries(
        dataset_name, levels=levels or [int(level)], create_missing=True)


def sync_boundary_hierarchy(dataset_code: str, *, levels: Iterable[int] | None = None,
                            create_missing: bool = True, batch_size: int = 200) -> dict:
    """Create hierarchy rows from an already-imported Boundary Dataset."""
    from siraj_research.geo_hierarchy import sync_hierarchy_from_boundaries
    return sync_hierarchy_from_boundaries(
        dataset_code, levels=levels, create_missing=create_missing,
        batch_size=batch_size)


def _queue_polygon_import(dataset: str, file_path: str, level: int, *, enqueue: bool,
                          sync_hierarchy: bool = True) -> dict:
    if frappe is None:
        return {"queued": False, "dataset": dataset, "file": file_path}
    frappe.db.set_value("Boundary Dataset", dataset, {
        "import_status": "Queued", "import_progress": 0,
        "last_processed_offset": 0, "level": int(level),
        "import_log": "Queued - waiting for worker.",
    }, update_modified=False)
    frappe.db.commit()
    kwargs = {
        "dataset_name": dataset,
        "file_path_str": file_path,
        "level": int(level),
        "sync_hierarchy": bool(sync_hierarchy),
        "levels": [int(level)],
    }
    if not enqueue:
        import_and_sync_boundary_job(**kwargs)
        return {"queued": False, "dataset": dataset, "imported": True,
                "synced": bool(sync_hierarchy)}
    frappe.enqueue(
        import_and_sync_boundary_job, queue="long", timeout=6 * 60 * 60,
        job_id=f"siraj-bulk-boundary:{dataset}", **kwargs,
    )
    return {"queued": True, "dataset": dataset, "synced": bool(sync_hierarchy)}


def osm_commands(input_path: str, output_dir: str) -> list[list[str]]:
    """Return the two ``osmium`` commands needed to prepare boundary polygons.

    Commands are returned as argument lists (never shell strings), so file
    names with spaces are safe. Review them before running; a country PBF can
    take several minutes on a modest worker.
    """
    src = Path(input_path)
    out = Path(output_dir)
    filtered = out / f"{src.stem}-boundaries.osm.pbf"
    geojson = out / f"{src.stem}-boundaries.geojson"
    return [
        ["osmium", "tags-filter", str(src), "r/boundary=administrative",
         "w/boundary=administrative", "-o", str(filtered)],
        ["osmium", "export", "--geometry=multipolygon", "--overwrite",
         "-f", "geojson", str(filtered), "-o", str(geojson)],
    ]


def prepare_osm(input_path: str, output_dir: str, *, run: bool = False) -> dict:
    """Build (or merely describe) the osmium preparation step for OSM data."""
    commands = osm_commands(input_path, output_dir)
    if not run:
        return {"commands": commands, "ran": False}
    for command in commands:
        subprocess.run(command, check=True)
    return {"commands": commands, "ran": True,
            "output": commands[-1][-1]}


# ---------------------------------------------------------------------------
# Coordinate batch linking
# ---------------------------------------------------------------------------

def link_coordinates(points: list[list[float]], *, create_missing: bool = True,
                     use_online: bool = False, batch_size: int = 50) -> list[dict]:
    """Resolve and link many coordinates, committing once per batch."""
    from siraj_research.geo_hierarchy import resolve_and_link
    results = []
    for index, pair in enumerate(points, start=1):
        try:
            results.append(resolve_and_link(pair[0], pair[1],
                                            create_missing=create_missing,
                                            use_online=use_online))
        except Exception as exc:  # one bad point must not abort the batch
            results.append({"error": f"{type(exc).__name__}: {exc}", "point": pair})
        if frappe and index % batch_size == 0:
            frappe.db.commit()
    if frappe:
        frappe.db.commit()
    return results
