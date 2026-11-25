"""HTTP endpoints used by the Boundary Dataset form (upload + start + status).

All endpoints require SIRAJ Administrator (or System Manager) because
importing geometry is a privileged operation that rebuilds the server
index.
"""
from __future__ import annotations

from pathlib import Path

import frappe

from siraj_research.geo_import import (
	MAX_UPLOAD_BYTES,
	UPLOAD_SUBDIR,
	_save_upload,
	_upload_root,
	deps_ok,
	import_boundary_job,
)


def _assert_admin():
	if not (frappe.has_permission("Boundary Dataset", "write") or frappe.has_permission("Geo Settings", "write")):
		frappe.throw("Administrator role required to import boundary data.", frappe.PermissionError)


def _confine_upload_path(file_path: str) -> Path:
	if not file_path or not isinstance(file_path, str):
		frappe.throw("Uploaded file path must stay within boundary uploads.", frappe.PermissionError)
	upload_root = _upload_root()
	candidate = Path(file_path).resolve()
	if not candidate.is_relative_to(upload_root) or candidate == upload_root:
		frappe.throw("Uploaded file path must stay within boundary uploads.", frappe.PermissionError)
	return candidate


@frappe.whitelist()
def dependencies() -> dict:
	"""Return whether pyogrio / shapely / pyproj are installed, plus the
	list of any missing packages so the UI can tell the admin what to
	pip-install.
	"""
	_assert_admin()
	ok, missing = deps_ok()
	return {"ok": ok, "missing": missing}


@frappe.whitelist()
def upload_file(filename: str, filedata: str) -> dict:
	"""Upload an attachment filedata (base64) to the private directory and
	return a filesystem path the background job will read.
	"""
	_assert_admin()
	import base64
	if "," in filedata:
		filedata = filedata.split(",", 1)[1]
	# Pre-check base64 payload length before decoding huge buffers in memory.
	max_b64_chars = ((MAX_UPLOAD_BYTES + 2) // 3) * 4 + 4096
	if len(filedata) > max_b64_chars:
		frappe.throw("Uploaded boundary file exceeds maximum allowed size.", frappe.ValidationError)
	raw = base64.b64decode(filedata)
	if len(raw) > MAX_UPLOAD_BYTES:
		frappe.throw("Uploaded boundary file exceeds maximum allowed size.", frappe.ValidationError)
	path = _save_upload(raw, filename)
	return {"path": str(path), "size": len(raw)}


@frappe.whitelist()
def start_import(dataset: str, file_path: str, is_gazetteer: bool = False) -> dict:
	"""Kick off the import as a long-queue background job."""
	_assert_admin()
	confined_path = _confine_upload_path(file_path)
	doc = frappe.get_doc("Boundary Dataset", dataset)
	if doc.import_status == "Running":
		frappe.throw("An import is already running for this dataset.")
	if not confined_path.is_file():
		frappe.throw("Uploaded file not found. Upload it again.")
	doc.db_set("import_status", "Queued", update_modified=False)
	doc.db_set("import_progress", 0, update_modified=False)
	doc.db_set("import_log", "Queued — waiting for worker.", update_modified=False)
	frappe.db.commit()
	frappe.enqueue(
		import_boundary_job,
		queue="long",
		timeout=60 * 60,   # one hour ceiling for large datasets
		dataset_name=dataset,
		file_path_str=str(confined_path),
		is_gazetteer=bool(is_gazetteer),
		job_id=f"siraj-boundary-import:{dataset}",
	)
	return {"queued": True}


@frappe.whitelist()
def status(dataset: str) -> dict:
	"""Return the current Boundary Dataset status for the progress bar."""
	_assert_admin()
	doc = frappe.get_doc("Boundary Dataset", dataset)
	return {
		"import_status": doc.import_status,
		"import_progress": doc.import_progress or 0,
		"feature_count": doc.feature_count or 0,
		"index_version": doc.index_version or 0,
		"imported_at": doc.imported_at,
		"import_log": doc.import_log or "",
	}
