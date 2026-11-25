"""Unit tests for C-08 (HD-5): map_relations _().format, diagnostics get_app_path, visualization permlevel + valid_dimensions."""
from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest


class _PermissionError(Exception):
	pass


class _ValidationError(Exception):
	pass


def test_map_relations_formats_missing_seed_error_message(monkeypatch):
	fake = types.ModuleType("frappe")
	fake.PermissionError = _PermissionError
	fake.ValidationError = _ValidationError

	def _translate(text):
		# Frappe's real _(msg, lang=None, context=None) accepts at most 3 args,
		# where arg 2 is lang! Calling _("...: {0} {1}", doctype, name) either
		# fails or leaves "{0} {1}" unformatted.
		if not isinstance(text, str):
			raise TypeError("msg must be str")
		return text

	fake._ = _translate
	fake.whitelist = lambda *a, **k: (lambda fn: fn)
	fake.has_permission = lambda doctype, ptype="read", doc=None: True
	fake.get_meta = lambda doctype: types.SimpleNamespace(fields=[], get_field=lambda fn: None)
	fake.db = types.SimpleNamespace(exists=lambda dt, nm: True)
	fake.get_cached_value = lambda *a, **k: None

	def _throw(msg, exc=_ValidationError):
		raise exc(msg)

	fake.throw = _throw

	monkeypatch.setitem(sys.modules, "frappe", fake)
	import siraj_research.api.map_relations as mr

	importlib.reload(mr)

	with pytest.raises(_ValidationError) as exc_info:
		mr.get_entity_network("Person", "PER-9999")
	assert "Person" in str(exc_info.value)
	assert "PER-9999" in str(exc_info.value)
	assert "{0}" not in str(exc_info.value)


def test_diagnostics_asset_hashes_resolves_via_get_app_path(monkeypatch, tmp_path):
	app_public = tmp_path / "custom_app_pkg" / "public"
	(app_public / "js").mkdir(parents=True)
	sample_js = app_public / "js" / "siraj.bundle.js"
	sample_js.write_bytes(b"console.log('c08');")

	fake = types.ModuleType("frappe")
	fake.whitelist = lambda *a, **k: (lambda fn: fn)
	fake.local = types.SimpleNamespace(site="test.local", sites_path=str(tmp_path / "sites"))

	called_args = []

	def _get_app_path(app_name, *parts):
		called_args.append((app_name, *parts))
		p = tmp_path / "custom_app_pkg"
		for part in parts:
			p = p / part
		return str(p)

	fake.get_app_path = _get_app_path
	monkeypatch.setitem(sys.modules, "frappe", fake)

	import siraj_research.api.diagnostics as diag

	importlib.reload(diag)
	hashes = diag.asset_hashes()
	assert ("siraj_research", "public") in called_args
	assert hashes["/assets/siraj_research/js/siraj.bundle.js"] is not None
	assert len(hashes["/assets/siraj_research/js/siraj.bundle.js"]) == 16


def test_visualization_structure_data_raises_on_unreadable_permlevel_and_passes_valid_dimensions():
	sys.path.insert(0, str(Path(__file__).resolve().parent))
	from test_visualization import FakeFrappe, load_visualization

	# 1. Unreadable permlevel dimension raises PermissionError (fail-closed per HD-5).
	f_hidden = FakeFrappe({"Person": [{"name": "p1", "nationality": "Palestine", "classification": "A", "workflow_state": "Draft"}]})
	f_hidden.hidden_fields.add("nationality")
	v_hidden = load_visualization(f_hidden)
	with pytest.raises(PermissionError):
		v_hidden.structure_data("people")

	# 2. Pre-check via meta.get_permitted_fieldnames raises PermissionError even when 0 rows exist!
	f_empty_permlevel = FakeFrappe({"Person": []})
	f_empty_permlevel.get_meta = lambda doctype: types.SimpleNamespace(
		get_field=lambda field: types.SimpleNamespace(
			label=field, permlevel=1 if field == "nationality" else 0
		),
		get_permitted_fieldnames=lambda permission_type="read": ["classification", "workflow_state"],
	)
	v_empty = load_visualization(f_empty_permlevel)
	with pytest.raises(PermissionError):
		v_empty.structure_data("people")

	# 3. Schema-drifted dimension dropped from valid_dimensions must also be passed consistently
	#    to _structure_children so child field labels align with valid_dimensions (no off-by-one).
	f_drift = FakeFrappe(
		{
			"Person": [
				{
					"name": "p1",
					"display_name": "Alpha",
					"classification": "Civil",
					"workflow_state": "Draft",
				}
			]
		}
	)
	f_drift.get_meta = lambda doctype: types.SimpleNamespace(
		get_field=lambda field: None if field == "nationality" else types.SimpleNamespace(label=field)
	)
	v_drift = load_visualization(f_drift)
	res = v_drift.structure_data("people")
	assert res["dimensions"] == ["classification", "workflow_state"]
	assert res["children"][0]["field"] == "classification"
	assert res["children"][0]["children"][0]["field"] == "workflow_state"
