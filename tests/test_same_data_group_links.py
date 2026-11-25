"""Unit tests for C-03a: validate_same_data_group_links in siraj_research.permissions."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from unittest.mock import patch

import pytest


class _PermissionError(Exception):
	pass


def _install_frappe_stub():
	frappe = types.ModuleType("frappe")
	frappe.PermissionError = _PermissionError
	frappe._ = lambda msg: msg
	frappe.session = SimpleNamespace(user="gd1@example.com")
	frappe.get_roles = lambda user=None: ["Group Member", "SIRAJ Researcher"]

	def _throw(msg, exc=Exception, **kwargs):
		raise exc(msg)

	frappe.throw = _throw
	frappe.db = SimpleNamespace(
		escape=lambda v: f"'{v}'",
		get_value=lambda *a, **kw: None,
	)
	frappe.get_all = lambda *a, **kw: []
	frappe.get_meta = lambda dt: None
	sys.modules["frappe"] = frappe
	return frappe


def _field(fieldname, fieldtype, options="", label=None):
	return SimpleNamespace(
		fieldname=fieldname,
		fieldtype=fieldtype,
		options=options,
		label=label or fieldname,
	)


class _Doc:
	def __init__(self, doctype, values, children=None):
		self.doctype = doctype
		self._values = dict(values)
		self._children = list(children or [])

	def get(self, key, default=None):
		return self._values.get(key, default)

	def get_all_children(self):
		return list(self._children)


def test_validate_same_data_group_links_batches_per_doctype_and_redacts_target_identity():
	frappe = _install_frappe_stub()
	import importlib

	import siraj_research.hooks as hooks_mod
	import siraj_research.permissions as perms

	importlib.reload(hooks_mod)
	importlib.reload(perms)

	assert hasattr(perms, "validate_same_data_group_links"), (
		"validate_same_data_group_links must be implemented in siraj_research.permissions"
	)

	metas = {
		"Person": SimpleNamespace(
			fields=[
				_field("birthplace", "Link", "Place", "Birthplace"),
				_field("marriage_place", "Link", "Place", "Marriage Place"),
				_field("nationality", "Link", "Country", "Nationality"),
				_field("data_group", "Link", "Data Group", "Data Group"),
				_field("evidence", "Table", "Evidence", "Evidence"),
			]
		),
		"Evidence": SimpleNamespace(
			fields=[
				_field("source", "Link", "Source", "Source"),
				_field("reviewer", "Link", "User", "Reviewer"),
			]
		),
		"Relationship": SimpleNamespace(
			fields=[
				_field("subject_type", "Link", "DocType", "Subject Type"),
				_field("subject", "Dynamic Link", "subject_type", "Subject"),
				_field("object_type", "Link", "DocType", "Object Type"),
				_field("object", "Dynamic Link", "object_type", "Object"),
			]
		),
	}

	get_all_calls = []

	def fake_get_all(doctype, filters=None, fields=None, **kwargs):
		get_all_calls.append((doctype, filters, fields))
		table = {
			"Place": {
				"PLC-GD-1": "GD",
				"PLC-GD-2": "GD",
				"PLC-GC-SECRET": "GC",
				"PLC-BLANK": None,
			},
			"Source": {
				"SRC-GD-1": "GD",
				"SRC-GC-SECRET": "GC",
			},
			"Person": {
				"PER-GD-1": "GD",
				"PER-GC-SECRET": "GC",
			},
		}.get(doctype, {})
		requested = filters["name"][1]
		return [
			{"name": name, "data_group": table.get(name)}
			for name in requested
			if name in table
		]

	with (
		patch.object(frappe, "get_meta", side_effect=lambda dt: metas[dt]),
		patch.object(frappe, "get_all", side_effect=fake_get_all),
	):
		# 1) Same-group + unscoped links (Country, Data Group, User) succeed;
		#    two Place links batch into a SINGLE read on 'Place'.
		child_ok = _Doc("Evidence", {"source": "SRC-GD-1", "reviewer": "gd1@example.com"})
		doc_ok = _Doc(
			"Person",
			{
				"data_group": "GD",
				"birthplace": "PLC-GD-1",
				"marriage_place": "PLC-GD-2",
				"nationality": "Iraq",
			},
			children=[child_ok],
		)
		perms.validate_same_data_group_links(doc_ok)
		queried_dts = [call[0] for call in get_all_calls]
		assert queried_dts.count("Place") == 1
		assert queried_dts.count("Source") == 1
		assert "Country" not in queried_dts
		assert "User" not in queried_dts
		assert "Data Group" not in queried_dts

		# 2) Cross-group Link raises PermissionError with NO target name in message.
		doc_bad_link = _Doc(
			"Person",
			{"data_group": "GD", "birthplace": "PLC-GC-SECRET"},
		)
		with pytest.raises(_PermissionError) as exc_info:
			perms.validate_same_data_group_links(doc_bad_link)
		assert "PLC-GC-SECRET" not in str(exc_info.value)

		# 3) Dynamic Link to foreign group raises PermissionError with NO target name.
		rel_bad = _Doc(
			"Relationship",
			{
				"data_group": "GD",
				"subject_type": "Person",
				"subject": "PER-GD-1",
				"object_type": "Person",
				"object": "PER-GC-SECRET",
			},
		)
		with pytest.raises(_PermissionError) as dyn_exc:
			perms.validate_same_data_group_links(rel_bad)
		assert "PER-GC-SECRET" not in str(dyn_exc.value)

		# 4) Child-row Link to foreign group uses parent data_group and redacts target name.
		child_bad = _Doc("Evidence", {"source": "SRC-GC-SECRET"})
		doc_bad_child = _Doc("Person", {"data_group": "GD"}, children=[child_bad])
		with pytest.raises(_PermissionError) as child_exc:
			perms.validate_same_data_group_links(doc_bad_child)
		assert "SRC-GC-SECRET" not in str(child_exc.value)

		# 5) Blank-group target from grouped source is rejected (fail-closed).
		doc_blank_target = _Doc(
			"Person",
			{"data_group": "GD", "birthplace": "PLC-BLANK"},
		)
		with pytest.raises(_PermissionError) as blank_exc:
			perms.validate_same_data_group_links(doc_blank_target)
		assert "PLC-BLANK" not in str(blank_exc.value)
