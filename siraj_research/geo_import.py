"""Boundary / gazetteer import pipeline (Phase 2).

Background job that reads a zipped shapefile / GeoJSON / GeoPackage the
admin uploads, normalises field names to a known mapping, reprojects to
EPSG:4326, calls shapely.make_valid, writes full-resolution and
simplified WKB to Admin Boundary (or Gazetteer Place), upserts by
pcode, reports progress via the Boundary Dataset row, and finally
bumps index_version so worker STRtree caches are invalidated.

Geospatial dependencies (pyogrio, shapely, pyproj) are OPTIONAL at
import time — the module loads fine without them, but
`start_import` returns a clear "install packages" message so the admin
knows what to do.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Optional

import frappe

# ---------------------------------------------------------------------------
# Optional dependency handling
# ---------------------------------------------------------------------------

_MISSING = []
try:
    import shapely
    import shapely.wkb
    import shapely.wkt
    from shapely.geometry import mapping, shape
    from shapely.ops import transform as sh_transform
    from shapely.validation import make_valid
except Exception:  # pragma: no cover
    shapely = None
    _MISSING.append("shapely")

try:
    import pyproj
except Exception:  # pragma: no cover
    pyproj = None
    _MISSING.append("pyproj")

try:
    import pyogrio
    _IO_BACKEND = "pyogrio"
except Exception:
    pyogrio = None
    try:
        import fiona
        _IO_BACKEND = "fiona"
    except Exception:
        fiona = None
        _IO_BACKEND = None
        _MISSING.append("pyogrio (preferred) or fiona")


def deps_ok() -> tuple[bool, list[str]]:
    return (not _MISSING), list(_MISSING)


# ---------------------------------------------------------------------------
# Upload handling
# ---------------------------------------------------------------------------

UPLOAD_SUBDIR = "siraj_boundary_uploads"


def _save_upload(filedata: bytes, filename: str) -> Path:
    """Write the uploaded bytes to the site's private directory and return
    the path. Caller is responsible for cleanup.
    """
    import frappe.utils.file_manager as fm
    # The simplest safe path: private/files/<boundary-dataset>/<name>
    private = Path(frappe.get_site_path("private"))
    root = private / UPLOAD_SUBDIR
    root.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", filename)
    out = root / safe_name
    out.write_bytes(filedata)
    return out


def _extract_if_zip(path: Path, workdir: Path) -> list[Path]:
    """If `path` is a zip, extract its shapefile/geojson/gpkg components
    into workdir and return the path(s) of the main data file. Otherwise
    return [path].
    """
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            zf.extractall(workdir)
        # Look for a primary data file inside the extracted tree.
        patterns = ("*.gpkg", "*.geojson", "*.json", "*.shp")
        found = []
        for pat in patterns:
            found.extend(sorted(workdir.rglob(pat)))
        # Filter out non-shapefile-related .shp sidecars (Fiona/pyogrio pick the .shp).
        return found or [path]
    return [path]


# ---------------------------------------------------------------------------
# Field-name heuristics
# ---------------------------------------------------------------------------

# Each entry: a canonical internal name (used when writing to Admin Boundary
# or Gazetteer Place), plus a list of lower-case aliases seen in common
# datasets (geoBoundaries, OCHA COD-AB Iraq/Afghanistan, GeoNames, OSM).
POLYGON_FIELDS = {
    "pcode":      ["pcode", "adm{pcode}_pcode".format(pcode="{level}"),  "shape_pcode", "ocd_id", "ref_pcode"],
    "name_en":    ["name_en", "engtype", "name", "nam", "admin{pcode}_name".format(pcode="{level}"), "shape_en"],
    "name_ar":    ["name_ar", "ar_name", "arname", "admin{pcode}_ar".format(pcode="{level}"), "shape_ar"],
    "parent_pcode":["parent_pcode", "par_pcode", "adm{pcode}_pcode".format(pcode="{parent}"), "parent_adm", "par_id"],
    "source_id":  ["id", "fid", "objectid", "shape_id", "ogc_fid"],
}
GAZETTEER_FIELDS = {
    "name_en":     ["name", "name_en", "asciiname", "placename", "full_name", "poi_name"],
    "name_ar":     ["name_ar", "ar_name", "arabic_name"],
    "asciiname":   ["asciiname", "name_ascii", "ascii"],
    "feature_code":["feature_code", "feat_code", "fclass", "fcode"],
    "pcode":       ["pcode", "adm0_pcode", "adm1_pcode", "adm2_pcode", "geonameid", "feature_id"],
    "admin1_pcode":["admin1_pcode", "adm1_pcode", "admin1_id", "cc1"],
    "admin2_pcode":["admin2_pcode", "adm2_pcode", "admin2_id"],
    "latitude":    ["latitude", "lat", "y", "latitude_d"],
    "longitude":   ["longitude", "lon", "lng", "x", "longitude_d"],
    "elevation_m": ["elevation", "dem", "elev", "gtopo30"],
    "population":  ["population", "pop", "population_ppl"],
    "country":     ["country", "iso", "iso_a2", "cc", "country_code"],
    "cc2":         ["cc2", "adm0_a2"],
    "timezone":    ["timezone", "tz", "tzid"],
    "modification_date": ["modification_date", "last_modified", "updated_at", "updated_date"],
    "source_id":   ["id", "geonameid", "fid", "objectid", "ogc_fid"],
}


def _pick_field(columns: dict, aliases: Iterable[str], *, level: int = 0) -> str | None:
    """Return the first column whose name matches one of the aliases,
    substituting {level} / {parent} into alias templates.
    """
    lower = {c.lower(): c for c in columns}
    parent = level - 1
    for alias in aliases:
        for variant in (
            alias,
            alias.replace("{level}", str(level)),
            alias.replace("{pcode}", str(level)),
            alias.replace("{parent}", str(parent)),
            "adm" + str(level) + "_pcode",
            "admin" + str(level) + "pcode",
            "adm" + str(level) + "_name",
        ):
            if variant in lower:
                return lower[variant]
    # Last-ditch: pick a column whose name ends with _pcode matching level.
    for lc, orig in lower.items():
        if level and (lc.endswith(f"adm{level}_pcode") or lc.endswith(f"admin{level}pcode")):
            return orig
    return None


# ---------------------------------------------------------------------------
# Feature iteration (abstracts over pyogrio vs fiona)
# ---------------------------------------------------------------------------

def _iter_features(file_path: Path, encoding: str = "utf-8", batch_size: int = 500) -> Iterable[dict]:
    """Yield dicts with keys: properties (dict), geometry (shapely geom).

    ``batch_size`` controls pyogrio's ``max_features`` window so a country-
    sized shapefile never has to be decoded into worker memory at once.
    """
    if _IO_BACKEND == "pyogrio":
        return _iter_pyogrio(file_path, encoding, batch_size)
    if _IO_BACKEND == "fiona":
        return _iter_fiona(file_path, encoding)
    raise RuntimeError(
        "No vector-IO library installed. Install with: "
        "./env/bin/pip install pyogrio shapely pyproj"
    )


def _iter_pyogrio(file_path: Path, encoding: str, batch_size: int = 500):
	"""Stream raw pyogrio features in bounded batches (no geopandas).

	``pyogrio.raw.read`` supports ``skip_features`` / ``max_features`` in
	modern releases. We call it repeatedly with a small window so memory
	usage stays flat even for a whole-country GADM layer. Older pyogrio
	versions fall back to one-shot decoding, which still works but is only
	recommended for small files.
	"""
	import numpy as np
	import pyogrio as _pyogrio

	total = 0
	try:
		info = _pyogrio.read_info(str(file_path), encoding=encoding)
		total = int(info.get("features") or 0)
	except Exception:
		pass

	offset = 0
	one_shot = False
	transformer = None
	field_names: list[str] = []
	while True:
		kwargs = dict(encoding=encoding, read_geometry=True)
		if one_shot:
			pass
		else:
			kwargs.update(skip_features=offset, max_features=max(1, batch_size))
		try:
			meta, flds, geom_wkb = _pyogrio.raw.read(str(file_path), **kwargs)
		except TypeError:
			# pyogrio < 0.5 has no slice arguments.
			one_shot = True
			meta, flds, geom_wkb = _pyogrio.raw.read(str(file_path), encoding=encoding,
			                                         read_geometry=True)
		if transformer is None and not field_names:
			crs_info = meta.get("crs") or ""
			if pyproj and crs_info and "EPSG:4326" not in str(crs_info).upper() \
					and "WGS 84" not in str(crs_info).upper():
				try:
					from_srs = pyproj.CRS.from_user_input(crs_info)
					to_srs = pyproj.CRS.from_epsg(4326)
					transformer = pyproj.Transformer.from_crs(
						from_srs, to_srs, always_xy=True).transform
				except Exception:
					transformer = None
			field_names = list(meta.get("fields") or [])

		count = len(geom_wkb)
		if count == 0:
			break
		for i in range(count):
			props = {}
			for col_idx, name in enumerate(field_names):
				val = flds[col_idx][i] if col_idx < len(flds) else None
				if isinstance(val, np.integer):
					val = int(val)
				elif isinstance(val, np.floating):
					val = float(val) if np.isfinite(val) else None
				elif isinstance(val, bytes):
					try:
						val = val.decode(encoding or "utf-8", errors="replace")
					except Exception:
						val = None
				props[name] = val
			wkb = geom_wkb[i] if i < count else None
			geom = None
			if wkb is not None and len(wkb) > 0:
				try:
					geom = shapely.wkb.loads(bytes(wkb))
					if transformer is not None:
						geom = sh_transform(transformer, geom)
				except Exception:
					geom = None
			yield {"properties": props, "geometry": geom}

		offset += count
		if one_shot or (total and offset >= total):
			break


def _iter_fiona(file_path: Path, encoding: str):
    import fiona as _fiona
    with _fiona.open(str(file_path), encoding=encoding) as src:
        src_crs = src.crs or {}
        transformer = None
        if src_crs and pyproj and str(src_crs.get("init", "epsg:4326")).lower() not in ("epsg:4326",):
            try:
                from_srs = pyproj.CRS.from_user_input(src_crs)
                to_srs = pyproj.CRS.from_epsg(4326)
                transformer = pyproj.Transformer.from_crs(from_srs, to_srs, always_xy=True).transform
            except Exception:
                transformer = None
        for feat in src:
            geom_raw = feat.get("geometry")
            if not geom_raw:
                continue
            try:
                geom = shape(geom_raw)
            except Exception:
                continue
            if transformer is not None and shapely is not None:
                try:
                    geom = sh_transform(transformer, geom)
                except Exception:
                    pass
            yield {"properties": dict(feat.get("properties") or {}), "geometry": geom}


# ---------------------------------------------------------------------------
# Upsert helpers
# ---------------------------------------------------------------------------

def _upsert_admin_boundary(dataset: str, level: int, record: dict, store_geojson: bool = True) -> None:
    """Insert or update a single Admin Boundary row and its geometry child."""
    pcode = record.get("pcode")
    if not pcode:
        return  # can't link without pcode
    existing = frappe.db.get_value("Admin Boundary",
                                   {"dataset": dataset, "pcode": pcode}, "name")
    doc = frappe.get_doc("Admin Boundary", existing) if existing else frappe.new_doc("Admin Boundary")
    doc.dataset = dataset
    doc.level = level
    doc.pcode = pcode
    doc.name_en = record.get("name_en") or doc.get("name_en")
    doc.name_ar = record.get("name_ar")
    doc.parent_pcode = record.get("parent_pcode")
    doc.country = record.get("country")
    doc.source_id = str(record.get("source_id") or "")[:120]
    doc.centroid_lat = record.get("centroid_lat")
    doc.centroid_lon = record.get("centroid_lon")
    doc.bbox = record.get("bbox")
    for field in ("bbox_min_lon", "bbox_min_lat", "bbox_max_lon", "bbox_max_lat"):
        if hasattr(doc, field) and record.get(field) is not None:
            doc.set(field, record[field])
    doc.area_m2 = record.get("area_m2")
    hierarchy_doctype = {
        1: "Governorate", 2: "District", 3: "Municipality",
        4: "Village", 5: "Community",
    }.get(int(level))
    if hierarchy_doctype and hasattr(doc, "linked_hierarchy_doctype") \
            and not doc.get("linked_hierarchy") \
            and frappe.db.exists(hierarchy_doctype, pcode):
        doc.linked_hierarchy_doctype = hierarchy_doctype
        doc.linked_hierarchy = pcode
    if shapely and record.get("geom_full") is not None:
        # Replace geometries child rows (full + simplified).
        doc.set("geometries", [])
        for label, geom in (("full", record["geom_full"]),
                            ("simplified", record.get("geom_simplified"))):
            if geom is None:
                continue
            child = {
                "precision": label,
                "srid": 4326,
                "point_count": (sum(1 for _ in getattr(geom, 'exterior', []).coords)
                                if geom.geom_type == "Polygon"
                                else 0),
                "geom_wkb_hex": shapely.wkb.dumps(geom, hex=True).decode("ascii"),
            }
            try:
                geom_meta = frappe.get_meta("Admin Boundary Geom")
                supports_geojson = geom_meta.has_field("geom_geojson")
            except Exception:
                supports_geojson = False
            if store_geojson and supports_geojson and (
                    label == "simplified" or record.get("geom_simplified") is None):
                child["geom_geojson"] = json.dumps(
                    shapely.geometry.mapping(geom), separators=(",", ":"), ensure_ascii=False)
            doc.append("geometries", child)
    doc.flags.ignore_permissions = True
    doc.save(ignore_permissions=True)


def _upsert_gazetteer(dataset: str, record: dict) -> None:
    lat = record.get("latitude")
    lon = record.get("longitude")
    if lat is None or lon is None:
        return
    key = {"dataset": dataset, "latitude": lat, "longitude": lon, "name_en": record.get("name_en")}
    existing = frappe.db.exists("Gazetteer Place", key)
    doc = frappe.get_doc("Gazetteer Place", existing) if existing else frappe.new_doc("Gazetteer Place")
    doc.dataset = dataset
    for k in ("feature_code", "pcode", "name_en", "name_ar", "asciiname",
              "admin1_pcode", "admin2_pcode", "latitude", "longitude",
              "elevation_m", "population", "cc2", "timezone",
              "modification_date", "source_id"):
        if record.get(k) is not None:
            setattr(doc, k, record[k])
    doc.flags.ignore_permissions = True
    doc.save(ignore_permissions=True)


# ---------------------------------------------------------------------------
# Main background job
# ---------------------------------------------------------------------------

def _set_status(doc, **kw):
    for k, v in kw.items():
        setattr(doc, k, v)
    doc.db_update()
    frappe.db.commit()


def import_boundary_job(dataset_name: str, file_path_str: str, is_gazetteer: bool = False):
    """Long-running RQ worker entry point.

    Parameters
    ----------
    dataset_name : str
        Name of the Boundary Dataset DocType (already saved with
        import_status='Queued').
    file_path_str : str
        Absolute path to the saved upload on disk.
    is_gazetteer : bool
        If True the file is treated as a point gazetteer (Gazetteer Place);
        otherwise it is polygon/multipolygon (Admin Boundary).
    """
    ok, missing = deps_ok()
    if not ok:
        doc = frappe.get_doc("Boundary Dataset", dataset_name)
        _set_status(doc, import_status="Failed",
                    import_log="Missing Python packages: " + ", ".join(missing)
                    + ". Install with ./env/bin/pip install pyogrio shapely pyproj")
        return
    file_path = Path(file_path_str)
    doc = frappe.get_doc("Boundary Dataset", dataset_name)
    try:
        _set_status(doc, import_status="Running", import_progress=0, import_log="")
        workdir = file_path.parent / "_extract"
        workdir.mkdir(exist_ok=True)
        data_files = _extract_if_zip(file_path, workdir)
        if not data_files:
            raise RuntimeError("No .shp / .geojson / .gpkg found inside the archive.")
        data_file = data_files[0]
        encoding = doc.encoding or "utf-8"
        level = int(doc.level or 1)
        tolerance_m = float(doc.simplification_tolerance_m or 0)
        batch_size = max(50, int(doc.import_batch_size or 500))
        store_geojson = bool(getattr(doc, "store_geojson", 1))
        total_estimate = 0
        count = 0
        for feat in _iter_features(data_file, encoding, batch_size):
            props = {k.lower(): v for k, v in (feat["properties"] or {}).items()}
            geom = feat["geometry"]
            if is_gazetteer:
                record = {}
                for canon, aliases in GAZETTEER_FIELDS.items():
                    col = _pick_field({c: 1 for c in props.keys()}, aliases)
                    if col:
                        record[canon] = props[col]
                if record.get("latitude") is not None:
                    try:
                        record["latitude"] = float(record["latitude"])
                        record["longitude"] = float(record["longitude"])
                    except Exception:
                        continue
                _upsert_gazetteer(dataset_name, record)
            else:
                if not shapely:
                    raise RuntimeError("shapely required for polygon import")
                if geom is None:
                    continue
                if not geom.is_valid:
                    geom = make_valid(geom)
                if geom.is_empty:
                    continue
                # Only keep Polygon / MultiPolygon
                if geom.geom_type not in ("Polygon", "MultiPolygon"):
                    continue
                record = {}
                for canon, aliases in POLYGON_FIELDS.items():
                    col = _pick_field({c: 1 for c in props.keys()}, aliases, level=level)
                    if col is not None:
                        val = props[col]
                        if isinstance(val, bytes):
                            val = val.decode(encoding, errors="replace")
                        record[canon] = val
                # Centroid & bbox in WGS 84
                c = geom.representative_point()
                record["centroid_lat"] = c.y
                record["centroid_lon"] = c.x
                b = geom.bounds
                record["bbox"] = ",".join(f"{v:.6f}" for v in b) if b else None
                if b:
                    record.update({
                        "bbox_min_lon": b[0], "bbox_min_lat": b[1],
                        "bbox_max_lon": b[2], "bbox_max_lat": b[3],
                    })
                # Area in m² using a rough AEQD centered on centroid. Skip
                # if pyproj not available.
                if pyproj:
                    try:
                        aeqd = pyproj.Proj(proj="aeqd", lat_0=c.y, lon_0=c.x, datum="WGS84", units="m")
                        projected = sh_transform(
                            pyproj.Transformer.from_proj(pyproj.CRS.from_epsg(4326), aeqd, always_xy=True).transform,
                            geom)
                        record["area_m2"] = projected.area
                    except Exception:
                        record["area_m2"] = None
                record["geom_full"] = geom
                if tolerance_m > 0:
                    record["geom_simplified"] = geom.simplify(tolerance_m / 111320.0, preserve_topology=True)
                _upsert_admin_boundary(dataset_name, level, record, store_geojson)
            count += 1
            if count % batch_size == 0:
                _set_status(doc, import_progress=min(99, int(count / max(total_estimate or 1, 1) * 100)),
                            feature_count=count, last_processed_offset=count)
                # Free the savepoint cache periodically so long imports never
                # accumulate one giant transaction.
                frappe.db.commit()
        # Done: bump index_version so STRtree caches invalidate.
        doc.reload()
        doc.db_set("import_status", "Complete", update_modified=False)
        doc.db_set("feature_count", count, update_modified=False)
        doc.db_set("import_progress", 100, update_modified=False)
        doc.db_set("imported_at", frappe.utils.now(), update_modified=False)
        doc.db_set("index_version", (doc.index_version or 0) + 1, update_modified=False)
        doc.db_set("import_log", f"Imported {count} features from {data_file.name}", update_modified=False)
        doc.db_set("last_processed_offset", count, update_modified=False)
        frappe.db.commit()
    except Exception as e:
        frappe.db.rollback()
        try:
            doc = frappe.get_doc("Boundary Dataset", dataset_name)
            _set_status(doc, import_status="Failed", import_log=f"{type(e).__name__}: {e}")
        except Exception:
            pass
        raise
    finally:
        # Best-effort cleanup of extracted temp files.
        try:
            if file_path.exists() and file_path.name.endswith((".zip", ".gpkg")):
                # Keep the original file for audit (it lives under private
                # already). Only remove the unzip workdir.
                import shutil
                shutil.rmtree(workdir, ignore_errors=True)
        except Exception:
            pass
