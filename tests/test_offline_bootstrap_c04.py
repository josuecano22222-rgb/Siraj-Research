"""Unit tests for C-04 (HD-2): offline_bootstrap admin gate, max_zoom clamp, long-queue job_id, and concurrency guard."""

from __future__ import annotations

import importlib
import sys
import types
from types import SimpleNamespace
from unittest.mock import patch

import pytest


class _PermissionError(Exception):
	pass


class _ValidationError(Exception):
	pass


def _install_frappe_stub():
	frappe = types.ModuleType("frappe")
	frappe.PermissionError = _PermissionError
	frappe.ValidationError = _ValidationError
	frappe._ = lambda msg: msg
	frappe.session = SimpleNamespace(user="viewer@example.com")
	frappe.local = SimpleNamespace(site="test.site")
	frappe.get_roles = lambda user=None: ["SIRAJ Viewer"]
	frappe.get_site_path = lambda *parts: "/tmp/siraj-test-site/" + "/".join(parts)

	def _throw(msg, exc=_ValidationError, **kwargs):
		raise exc(msg)

	frappe.throw = _throw
	def _whitelist(*a, **kw):
		def _wrap(fn):
			fn._whitelisted = True
			return fn

		if a and callable(a[0]):
			return _wrap(a[0])
		return _wrap

	frappe.whitelist = _whitelist
	state = {
		"active_boundary_dataset": "ISO-TEST-BND",
		"online_setup_enabled": 1,
		"bootstrap_running": 0,
		"bootstrap_stop_requested": 0,
		"bootstrap_last_status": "",
	}
	frappe.db = SimpleNamespace(
		get_value=lambda dt, dn, field: state.get(field),
		set_value=lambda dt, dn, field, value=None, **kw: (
			state.update(field) if isinstance(field, dict) else state.__setitem__(field, value)
		),
		commit=lambda: None,
	)
	frappe.get_single = lambda dt: SimpleNamespace(**state)
	frappe.enqueue = lambda *a, **kw: None

	utils_mod = types.ModuleType("frappe.utils")
	utils_mod.cint = lambda v: int(v or 0)
	bg_mod = types.ModuleType("frappe.utils.background_jobs")
	bg_mod.is_job_enqueued = lambda job_id: False
	bg_mod.get_job_status = lambda job_id: None
	bg_mod.create_job_id = lambda job_id: f"test.site::{job_id}"

	sys.modules["frappe"] = frappe
	sys.modules["frappe.utils"] = utils_mod
	sys.modules["frappe.utils.background_jobs"] = bg_mod
	return frappe, state, bg_mod


def test_c04_offline_bootstrap_admin_gate_zoom_clamp_and_concurrency_refusal():
	frappe, state, bg_mod = _install_frappe_stub()
	import siraj_research.offline_bootstrap as ob

	importlib.reload(ob)

	# 1) Non-admin refused for all three endpoints (even when flags.in_test would be True in Frappe!).
	frappe.session.user = "viewer@example.com"
	frappe.get_roles = lambda user=None: ["Group Member", "SIRAJ Viewer"]
	for fn in (ob.request_stop, ob.clear_stop, ob.run_online_setup):
		with pytest.raises(_PermissionError):
			fn()

	# 2) Admin user: max_zoom=20 clamped to 14, enqueued on 'long' with job_id, concurrent run refused.
	frappe.session.user = "admin@example.com"
	frappe.get_roles = lambda user=None: ["Group Member", "SIRAJ Administrator"]
	enqueued = []
	with patch.object(frappe, "enqueue", side_effect=lambda m, **kw: enqueued.append((m, kw))):
		out = ob.run_online_setup(dataset="ISO-TEST-BND", max_zoom=20)
		assert out["queued"] is True
		assert out["max_zoom"] == 14
		assert out["job_id"] == ob.BOOTSTRAP_JOB_ID
		assert len(enqueued) == 1
		assert enqueued[0][1]["queue"] == "long"
		assert enqueued[0][1]["job_id"] == ob.BOOTSTRAP_JOB_ID
		assert enqueued[0][1]["max_zoom"] == 14
		assert state["bootstrap_running"] == 1

	# Second run while RQ job status is 'queued' or 'started' is refused.
	for live_status in ("queued", "started"):
		with patch.object(bg_mod, "get_job_status", return_value=live_status):
			with pytest.raises(_ValidationError):
				ob.run_online_setup(dataset="ISO-TEST-BND", max_zoom=5)

	# 3) Stale bootstrap_running=1 in DB with no live RQ job (status None / 'failed' / 'finished')
	#    does NOT block a new run — flag is treated as stale and new run queues cleanly!
	state["bootstrap_running"] = 1
	state["bootstrap_last_status"] = "running"
	enqueued_after_stale = []
	with (
		patch.object(bg_mod, "get_job_status", return_value="failed"),
		patch.object(frappe, "enqueue", side_effect=lambda m, **kw: enqueued_after_stale.append((m, kw))),
	):
		recovered = ob.run_online_setup(dataset="ISO-TEST-BND", max_zoom=7)
		assert recovered["queued"] is True
		assert len(enqueued_after_stale) == 1
		assert state["bootstrap_running"] == 1
		assert state["bootstrap_last_status"] == "queued"

	# 4) If frappe.enqueue raises, bootstrap_running is reset to 0!
	with (
		patch.object(bg_mod, "get_job_status", return_value=None),
		patch.object(frappe, "enqueue", side_effect=RuntimeError("Redis queue unreachable")),
	):
		with pytest.raises(RuntimeError, match="Redis queue unreachable"):
			ob.run_online_setup(dataset="ISO-TEST-BND", max_zoom=6)
		assert state["bootstrap_running"] == 0
		assert state["bootstrap_last_status"] == "enqueue failed"

	# 5) prepare_offline_site clears bootstrap_running=0 in finally even on unhandled exception.
	state["bootstrap_running"] = 1
	with patch.object(ob, "_step", side_effect=KeyError("unexpected stage crash")):
		with pytest.raises(KeyError, match="unexpected stage crash"):
			ob.prepare_offline_site(dataset="ISO-TEST-BND", max_zoom=2)
	assert state["bootstrap_running"] == 0
	assert state["bootstrap_last_status"] == "failed"
