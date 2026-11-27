"""Unit tests for C-03b: OperationalDeployment, CommandAppointment, Person.validate_family, and MilitaryUnit whitelist."""

from __future__ import annotations

import datetime as dt
import importlib
import sys
import types
from types import SimpleNamespace
from unittest.mock import patch

import pytest


class _ValidationError(Exception):
	pass


def _install_frappe_stub():
	frappe = types.ModuleType("frappe")
	frappe.ValidationError = _ValidationError
	frappe._ = lambda msg: msg

	def _throw(msg, exc=_ValidationError, **kwargs):
		raise exc(msg)

	frappe.throw = _throw
	frappe.whitelist = lambda *a, **kw: (
		(lambda fn: setattr(fn, "_whitelisted", True) or fn)
		if not (a and callable(a[0]))
		else (setattr(a[0], "_whitelisted", True) or a[0])
	)
	frappe.db = SimpleNamespace(get_value=lambda *a, **kw: None, set_value=lambda *a, **kw: None, exists=lambda *a, **kw: False)
	frappe.get_list = lambda *a, **kw: []
	frappe.get_all = lambda *a, **kw: []
	frappe.has_permission = lambda *a, **kw: True

	model_mod = types.ModuleType("frappe.model")
	doc_mod = types.ModuleType("frappe.model.document")

	class Document:
		pass

	doc_mod.Document = Document
	utils_mod = types.ModuleType("frappe.utils")
	utils_mod.getdate = lambda v=None: dt.date(2026, 11, 24) if v is None else dt.date.fromisoformat(str(v))

	sys.modules["frappe"] = frappe
	sys.modules["frappe.model"] = model_mod
	sys.modules["frappe.model.document"] = doc_mod
	sys.modules["frappe.utils"] = utils_mod
	return frappe


def test_c03b_operational_deployment_command_appointment_person_and_whitelisted_inventory():
	frappe = _install_frappe_stub()

	import siraj_research.siraj_research.doctype.command_appointment.command_appointment as ca_mod
	import siraj_research.siraj_research.doctype.military_unit.military_unit as mu_mod
	import siraj_research.siraj_research.doctype.operational_deployment.operational_deployment as od_mod
	import siraj_research.siraj_research.doctype.person.person as person_mod
	import siraj_research.utils.military as mil_utils

	for mod in (mil_utils, mu_mod, od_mod, ca_mod, person_mod):
		importlib.reload(mod)

	# 1) Exact @frappe.whitelist inventory on MilitaryUnit and utils/military:
	mu_whitelisted = [
		name
		for name, obj in vars(mu_mod.MilitaryUnit).items()
		if callable(obj) and getattr(obj, "_whitelisted", False)
	]
	util_whitelisted = [
		name
		for name, obj in vars(mil_utils).items()
		if callable(obj) and getattr(obj, "_whitelisted", False)
	]
	assert mu_whitelisted == ["get_descendants"]
	assert util_whitelisted == []

	# 2) OperationalDeployment: validate_one_current does NOT call db.set_value;
	#    on_update writes current_deployment and on_trash clears it.
	set_calls = []
	with (
		patch.object(frappe.db, "get_value", return_value=None),
		patch.object(frappe.db, "set_value", side_effect=lambda *a, **kw: set_calls.append((a, kw))),
	):
		dep = od_mod.OperationalDeployment()
		dep.doctype = "Operational Deployment"
		dep.name = "DEP-0001"
		dep.unit = "MIL-UNIT-0001"
		dep.is_current = 1
		dep.get_doc_before_save = lambda: None
		dep.validate_one_current()
		assert set_calls == [], "validate_one_current must not mutate Military Unit before persistence"

		assert hasattr(dep, "on_update"), "OperationalDeployment must implement on_update"
		assert hasattr(dep, "on_trash"), "OperationalDeployment must implement on_trash"
		dep.on_update()
		assert set_calls[-1][0][:4] == ("Military Unit", "MIL-UNIT-0001", "current_deployment", "DEP-0001")

	with (
		patch.object(frappe.db, "get_value", return_value="DEP-0001"),
		patch.object(frappe.db, "set_value", side_effect=lambda *a, **kw: set_calls.append((a, kw))),
	):
		dep.on_trash()
		assert set_calls[-1][0][:4] == ("Military Unit", "MIL-UNIT-0001", "current_deployment", None)

	# 3) CommandAppointment.validate_overlap uses frappe.get_list with 'role' in fields.
	list_calls = []

	def fake_get_list(doctype, filters=None, fields=None, **kw):
		list_calls.append((doctype, filters, fields))
		return [
			SimpleNamespace(
				name="CA-0001",
				commander="PER-0001",
				role="Commanding Officer",
				assigned_date="2026-01-01",
				relieved_date=None,
			)
		]

	with patch.object(frappe, "get_list", side_effect=fake_get_list):
		appt = ca_mod.CommandAppointment()
		appt.doctype = "Command Appointment"
		appt.name = "CA-0002"
		appt.unit = "MIL-UNIT-0001"
		appt.role = "Commanding Officer"
		appt.assigned_date = "2026-02-01"
		appt.relieved_date = None
		with pytest.raises(_ValidationError) as overlap_exc:
			appt.validate_overlap()
		assert "Commanding Officer" in str(overlap_exc.value)
		assert len(list_calls) == 1
		assert "role" in list_calls[0][2]

	# 4) Person.validate_family checks frappe.has_permission("Person", "read", doc=row.person) before reading sibling_name.
	with (
		patch.object(frappe, "has_permission", return_value=False),
		patch.object(frappe.db, "get_value", return_value="GC Classified Commander"),
	):
		p = person_mod.Person()
		p.name = "PER-GD-1"
		p.marriage_date = None
		p.birth_date = None
		p.spouse_birth_date = None
		p.marital_status = "Single"
		p.spouse_name = None
		row = SimpleNamespace(idx=1, person="PER-GC-1", sibling_name=None)
		p.get = lambda k, default=None: [row] if k == "siblings" else default
		p.validate_family()
		assert row.sibling_name is None
