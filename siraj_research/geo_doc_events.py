"""Document hooks that keep the six-level hierarchy in sync on every save.

Registered for every coordinate-bearing DocType in ``hooks.py``. The hook is
deliberately defensive: a missing dataset, a permission restriction or a
network outage must never stop a researcher from saving a record. It only
fills empty fields, so human-entered hierarchy values always win — with one
exception: a value that merely mirrors a live site/user *default* was never
human input. When coordinates are present those default-stamped levels are
cleared first so the derived chain can override them (and an open-water point
stays empty instead of inheriting a global default).
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

try:  # pragma: no cover - pure tests run without a bench
	import frappe
except Exception:  # pragma: no cover
	frappe = None  # type: ignore[assignment]

from siraj_research.record_icons import COORDINATE_DOCS


def defaulted_level_fields(values: Mapping[str, Any],
 defaults: Mapping[str, Any]) -> list[str]:
	"""Fieldnames whose current value merely mirrors a live default.

	Pure helper: a value counts as default-stamped when it equals the
	system/user default for that fieldname (scalar or multi-value default).
	Only non-empty values are considered; a missing default never matches.
	"""
	matched: list[str] = []
	for fieldname, value in values.items():
		if value in (None, "", [], ()):
			continue
		default = defaults.get(fieldname)
		if default is None:
			continue
		candidates = default if isinstance(default, list | tuple) else (default,)
		if value in candidates or str(value) in {str(item) for item in candidates}:
			matched.append(fieldname)
	return matched


def _live_defaults() -> dict:
	"""Session-merged system + user defaults; never raise into a save."""
	if frappe is None:  # pragma: no cover - pure tests
		return {}
	try:
		import frappe.defaults as frappe_defaults

		return dict(frappe_defaults.get_defaults() or {})
	except Exception:  # pragma: no cover - defensive in production
		return {}


def auto_fill_hierarchy(doc, method=None):
	if getattr(doc, "flags", None) and getattr(doc.flags, "siraj_hierarchy_resolved", False):
		return
	cfg = dict(COORDINATE_DOCS.get(getattr(doc, "doctype", "")) or {})
	if not cfg:
		return
	level_fields = [
		fieldname for key, fieldname in (cfg.get("admin_fields") or {}).items()
		if key != "place_name" and fieldname
	]
	lat = getattr(doc, cfg.get("lat_field") or "latitude", None)
	lon = getattr(doc, cfg.get("lon_field") or "longitude", None)
	if lat in (None, "") or lon in (None, ""):
		return
	try:
		latitude, longitude = float(lat), float(lon)
	except (TypeError, ValueError):
		return
	# A legacy (0,0) pair often means "unset". Do not resolve a misleading
	# hierarchy for it unless the researcher explicitly confirmed the origin.
	origin_field = cfg.get("origin_confirmed_field") or "coordinate_origin_confirmed"
	confirmed = getattr(doc, origin_field, None) in (1, True, "1")
	if latitude == 0 and longitude == 0 and not confirmed:
		return
	# Coordinates are supplied: a level value that only mirrors a live
	# site/user default is not research input. Clear it before the
	# "already populated" check so the derived chain can override it —
	# and so an over-water point stays empty instead of inheriting the
	# default. Genuine human input (any other value) is never touched.
	defaults = _live_defaults()
	if defaults and level_fields:
		current = {fieldname: getattr(doc, fieldname, None) for fieldname in level_fields}
		for fieldname in defaulted_level_fields(current, defaults):
			setattr(doc, fieldname, None)
	# If every hierarchy Link is already populated there is nothing to do;
	# resolving again on every save was a major Desk latency regression.
	# (Checked *after* the default strip above: default-stamped levels must
	# not short-circuit resolution on a record that has coordinates.)
	if level_fields and all(
		not hasattr(doc, fieldname) or getattr(doc, fieldname) not in (None, "")
		for fieldname in level_fields
	):
		return
	try:
		from siraj_research.geo_hierarchy_ui import apply_to_doc

		result = apply_to_doc(doc, create_missing=True, use_online=False)
		if result.get("updated"):
			doc.flags.siraj_hierarchy_resolved = True
	except Exception as exc:  # pragma: no cover - defensive in production
		try:
			frappe.log_error(
				title="SIRAJ hierarchy auto-fill failed",
				message=f"{getattr(doc, 'doctype', '?')} {getattr(doc, 'name', '?')}: {exc}",
			)
		except Exception:
			pass
