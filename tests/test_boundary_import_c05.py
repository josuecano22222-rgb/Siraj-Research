"""Unit tests for C-05: boundary_import admin gates, path confinement, upload cap, and zip safety."""
from __future__ import annotations

import base64
import importlib
import io
import stat
import sys
import types
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest


class _PermissionError(Exception):
	pass


class _ValidationError(Exception):
	pass


def _make_fake_frappe(site_private: Path, is_admin: bool = True):
	fake = types.ModuleType("frappe")
	fake.PermissionError = _PermissionError
	fake.ValidationError = _ValidationError
	fake._ = lambda msg: msg
	fake.session = types.SimpleNamespace(user="siraj.admin@example.com")
	fake.get_roles = lambda user=None: ["SIRAJ Administrator"] if is_admin else ["SIRAJ Viewer"]

	def _whitelist(*args, **kwargs):
		if args and callable(args[0]) and len(args) == 1 and not kwargs:
			return args[0]
		return lambda fn: fn

	fake.whitelist = _whitelist

	def _throw(msg, exc=_ValidationError):
		raise exc(msg)

	fake.throw = _throw
	fake.has_permission = lambda doctype, ptype="read": bool(is_admin)

	def _get_site_path(*parts):
		p = site_private.parent
		for part in parts:
			p = p / part
		return str(p)

	fake.get_site_path = _get_site_path
	fake.db = types.SimpleNamespace(commit=MagicMock())
	fake.enqueue = MagicMock()

	fake_doc = MagicMock()
	fake_doc.import_status = "Idle"
	fake.get_doc = MagicMock(return_value=fake_doc)

	utils_pkg = types.ModuleType("frappe.utils")
	fm_mod = types.ModuleType("frappe.utils.file_manager")
	utils_pkg.file_manager = fm_mod
	fake.utils = utils_pkg

	return fake, utils_pkg, fm_mod


@pytest.fixture
def boundary_env(monkeypatch, tmp_path):
	site_private = tmp_path / "site" / "private"
	site_private.mkdir(parents=True, exist_ok=True)
	state = {"is_admin": True, "roles": ["SIRAJ Administrator"], "user": "siraj.admin@example.com"}
	fake, utils_pkg, fm_mod = _make_fake_frappe(site_private, is_admin=True)
	fake.has_permission = lambda doctype, ptype="read": bool(state["is_admin"])
	fake.get_roles = lambda user=None: (
		list(state["roles"])
		if state["is_admin"]
		else [r for r in state["roles"] if r not in ("System Manager", "SIRAJ Administrator")]
	)
	fake.session = types.SimpleNamespace(user=state["user"])

	monkeypatch.setitem(sys.modules, "frappe", fake)
	monkeypatch.setitem(sys.modules, "frappe.utils", utils_pkg)
	monkeypatch.setitem(sys.modules, "frappe.utils.file_manager", fm_mod)

	import siraj_research.geo_import as gi

	importlib.reload(gi)
	import siraj_research.api.boundary_import as bi

	importlib.reload(bi)
	return bi, gi, fake, state, site_private


def test_dependencies_requires_admin(boundary_env):
	bi, _gi, fake, state, _site_private = boundary_env
	state["is_admin"] = False
	with pytest.raises(fake.PermissionError):
		bi.dependencies()

	state["is_admin"] = True
	res = bi.dependencies()
	assert "ok" in res and "missing" in res


def test_start_import_confines_file_path_and_blocks_symlink_escape(boundary_env, tmp_path):
	bi, gi, fake, state, site_private = boundary_env
	state["is_admin"] = True
	upload_dir = site_private / gi.UPLOAD_SUBDIR
	upload_dir.mkdir(parents=True, exist_ok=True)

	outside_secret = tmp_path / "outside_secret.geojson"
	outside_secret.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")

	# Direct path outside upload_dir -> PermissionError
	with pytest.raises(fake.PermissionError):
		bi.start_import("ISO-TEST-BND", str(outside_secret))

	# Traversal segments -> PermissionError
	with pytest.raises(fake.PermissionError):
		bi.start_import("ISO-TEST-BND", str(upload_dir / ".." / ".." / "outside_secret.geojson"))

	# Symlink inside upload_dir pointing outside upload_dir -> PermissionError
	symlink_escape = upload_dir / "escape_link.geojson"
	symlink_escape.symlink_to(outside_secret)
	with pytest.raises(fake.PermissionError):
		bi.start_import("ISO-TEST-BND", str(symlink_escape))

	# Legitimate uploaded file inside upload_dir -> allowed and canonical path passed to enqueue
	valid_file = upload_dir / "valid.geojson"
	valid_file.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
	res = bi.start_import("ISO-TEST-BND", str(valid_file))
	assert res == {"queued": True}
	assert fake.enqueue.call_count == 1
	assert fake.enqueue.call_args.kwargs["file_path_str"] == str(valid_file.resolve())


def test_upload_file_enforces_size_cap(boundary_env, monkeypatch):
	bi, _gi, fake, state, _site_private = boundary_env
	state["is_admin"] = True
	monkeypatch.setattr(bi, "MAX_UPLOAD_BYTES", 64)

	small_b64 = base64.b64encode(b"{}" * 10).decode("ascii")
	saved = bi.upload_file("ok.geojson", small_b64)
	assert saved["size"] == 20

	oversized_b64 = base64.b64encode(b"x" * 65).decode("ascii")
	with pytest.raises(fake.ValidationError):
		bi.upload_file("huge.geojson", oversized_b64)


def test_extract_if_zip_rejects_symlink_member(boundary_env, tmp_path):
	_bi, gi, fake, _state, _site_private = boundary_env
	zip_path = tmp_path / "symlink_member.zip"
	workdir = tmp_path / "extract_sym"
	workdir.mkdir()

	buf = io.BytesIO()
	with zipfile.ZipFile(buf, "w") as zf:
		zi = zipfile.ZipInfo("evil_link.geojson")
		zi.create_system = 3  # Unix
		zi.external_attr = (stat.S_IFLNK | 0o777) << 16
		zf.writestr(zi, "/etc/passwd")
	zip_path.write_bytes(buf.getvalue())

	with pytest.raises(fake.ValidationError):
		gi._extract_if_zip(zip_path, workdir)


def test_extract_if_zip_rejects_too_many_members(boundary_env, monkeypatch, tmp_path):
	_bi, gi, fake, _state, _site_private = boundary_env
	monkeypatch.setattr(gi, "MAX_ZIP_MEMBERS", 3)

	zip_path = tmp_path / "many_members.zip"
	workdir = tmp_path / "extract_many"
	workdir.mkdir()

	with zipfile.ZipFile(zip_path, "w") as zf:
		for idx in range(4):
			zf.writestr(f"part_{idx}.json", "{}")

	with pytest.raises(fake.ValidationError):
		gi._extract_if_zip(zip_path, workdir)


def test_extract_if_zip_rejects_excessive_uncompressed_size(boundary_env, monkeypatch, tmp_path):
	_bi, gi, fake, _state, _site_private = boundary_env
	monkeypatch.setattr(gi, "MAX_ZIP_UNCOMPRESSED_BYTES", 1024)

	zip_path = tmp_path / "zip_bomb.zip"
	workdir = tmp_path / "extract_bomb"
	workdir.mkdir()

	with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
		zf.writestr("bomb.geojson", b"0" * 4096)

	with pytest.raises(fake.ValidationError):
		gi._extract_if_zip(zip_path, workdir)


def test_extract_if_zip_extracts_clean_archive(boundary_env, tmp_path):
	_bi, gi, _fake, _state, _site_private = boundary_env
	zip_path = tmp_path / "clean.zip"
	workdir = tmp_path / "extract_clean"
	workdir.mkdir()

	with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
		zf.writestr("layer.geojson", '{"type":"FeatureCollection","features":[]}')

	extracted = gi._extract_if_zip(zip_path, workdir)
	assert len(extracted) == 1
	assert extracted[0].name == "layer.geojson"


def test_max_upload_bytes_lowered_to_100_mib_g5(boundary_env):
	bi, gi, _fake, _state, _site_private = boundary_env
	assert gi.MAX_UPLOAD_BYTES == 100 * 1024 * 1024
	assert bi.MAX_UPLOAD_BYTES == 100 * 1024 * 1024


def test_upload_file_rejects_dot_and_dotdot_filenames_g5(boundary_env):
	bi, _gi, fake, state, _site_private = boundary_env
	state["is_admin"] = True
	payload = base64.b64encode(b"{}").decode("ascii")
	for bad_name in ("..", ".", "../..", "dir/..", "dir/.", ""):
		with pytest.raises(fake.ValidationError):
			bi.upload_file(bad_name, payload)


def test_same_name_uploads_do_not_overwrite_g5(boundary_env):
	bi, gi, _fake, state, site_private = boundary_env
	state["is_admin"] = True
	upload_root = (site_private / gi.UPLOAD_SUBDIR).resolve()

	first = bi.upload_file("boundaries.geojson", base64.b64encode(b'{"id": 1}').decode("ascii"))
	second = bi.upload_file("boundaries.geojson", base64.b64encode(b'{"id": 2}').decode("ascii"))

	p1 = Path(first["path"]).resolve()
	p2 = Path(second["path"]).resolve()
	assert p1 != p2
	assert p1.is_relative_to(upload_root)
	assert p2.is_relative_to(upload_root)
	assert p1.name.endswith("_boundaries.geojson")
	assert p2.name.endswith("_boundaries.geojson")
	assert p1.read_bytes() == b'{"id": 1}'
	assert p2.read_bytes() == b'{"id": 2}'


def test_boundary_import_aligns_admin_roles_and_rejects_siraj_reviewer_g6(boundary_env):
	bi, _gi, fake, state, _site_private = boundary_env
	import siraj_research.offline_bootstrap as ob

	assert set(bi.BOUNDARY_IMPORT_ADMIN_ROLES) == set(ob.BOOTSTRAP_ADMIN_ROLES) == {
		"System Manager",
		"SIRAJ Administrator",
	}

	# Even if Boundary Dataset DocPerm grants write=1 to SIRAJ Reviewer, _assert_admin must reject Reviewer.
	state["is_admin"] = True
	fake.has_permission = lambda doctype, ptype="read": True
	fake.get_roles = lambda user=None: ["SIRAJ Reviewer"]
	fake.session.user = "reviewer@example.com"
	for call in (
		lambda: bi.dependencies(),
		lambda: bi.upload_file("probe.geojson", base64.b64encode(b"{}").decode("ascii")),
		lambda: bi.start_import("ISO-TEST-BND", "/tmp/probe.geojson"),
		lambda: bi.status("ISO-TEST-BND"),
	):
		with pytest.raises(fake.PermissionError):
			call()

	# System Manager and SIRAJ Administrator both pass _assert_admin.
	for admin_role in ("System Manager", "SIRAJ Administrator"):
		fake.get_roles = lambda user=None, r=admin_role: [r]
		res = bi.dependencies()
		assert "ok" in res
