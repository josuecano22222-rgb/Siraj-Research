"""Document hooks that keep the six-level hierarchy in sync on every save.

Registered for every coordinate-bearing DocType in ``hooks.py``. The hook is
deliberately defensive: a missing dataset, a permission restriction or a
network outage must never stop a researcher from saving a record. It only
fills empty fields, so human-entered hierarchy values always win.
"""
from __future__ import annotations

try:  # pragma: no cover - pure tests run without a bench
	import frappe
except Exception:  # pragma: no cover
	frappe = None  # type: ignore[assignment]

from siraj_research.record_icons import COORDINATE_DOCS


def auto_fill_hierarchy(doc, method=None):
	if getattr(doc, "flags", None) and getattr(doc.flags, "siraj_hierarchy_resolved", False):
		return
	cfg = dict(COORDINATE_DOCS.get(getattr(doc, "doctype", "")) or {})
	if not cfg:
		return
	lat = getattr(doc, cfg.get("lat_field") or "latitude", None)
	lon = getattr(doc, cfg.get("lon_field") or "longitude", None)
	if lat in (None, "") or lon in (None, ""):
		return
	try:
		float(lat), float(lon)
	except (TypeError, ValueError):
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
