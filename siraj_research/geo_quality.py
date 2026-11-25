"""Coordinate-quality reporting.

Whitelisted helpers that surface records whose coordinates are suspect so
analysts can triage them (null island, swapped lat/lon, out-of-range, records
that have no location but should, etc.). Read-only; never modifies data.
"""
from __future__ import annotations

import itertools

import frappe

from siraj_research.report_access import readable_rows

# DocTypes that are expected to carry coordinates once Workstream B lands.
# Today only these six have latitude/longitude Float fields.
LOCATED_DOCTYPES: tuple[str, ...] = (
	"Person",
	"Institution",
	"Place",
	"Research Event",
	"Military Unit",
	"Operational Deployment",
)

MAX_QUALITY_ROWS = 5000


def _query_fields_for(doctype: str) -> tuple[list[str], str]:
	meta = frappe.get_meta(doctype)
	title_field = meta.get_title_field() or "name"
	fields: list[str] = []
	for candidate in (title_field, "display_name", "label", "title", "latitude", "longitude", "geo_precision"):
		if candidate != "name" and meta.has_field(candidate) and candidate not in fields:
			fields.append(candidate)
	return fields, title_field


@frappe.whitelist()
def quality_report(doctype: str | None = None) -> dict:
	"""Return counts and a paginated sample of suspect coordinates.

	Categories:
	* missing          -- record has no lat or no lon
	* null_island      -- lat = 0 AND lon = 0 (almost always an unset placeholder)
	* out_of_range     -- lat outside [-90,90] or lon outside [-180,180]
	* swapped          -- abs(lat) <= 90 AND abs(lon) <= 180 BUT lon is outside
	                      typical latitude band while lat is within the band
	                      (heuristic; never auto-fixes, only flags)
	* no_precision     -- located but no geo_precision set

	Returned dicts are plain lists of {name, label, latitude, longitude, reasons};
	respects DocType and per-document Data Group read permissions via ``readable_rows``.
	"""
	if doctype:
		if doctype not in LOCATED_DOCTYPES:
			return {"totals": {}, "samples": {}}
		doctypes: tuple[str, ...] = (doctype,)
	else:
		doctypes = LOCATED_DOCTYPES

	totals: dict[str, dict] = {}
	samples: dict[str, list[dict]] = {}

	for dt in doctypes:
		if not frappe.has_permission(dt, "read"):
			continue

		fields, title_field = _query_fields_for(dt)
		visible_records = list(itertools.islice(readable_rows(dt, fields), MAX_QUALITY_ROWS))
		total = len(visible_records)
		cats = {k: 0 for k in ("missing", "null_island", "out_of_range", "swapped", "no_precision")}
		bad: list[dict] = []

		for r in visible_records:
			lat = r.get("latitude")
			lon = r.get("longitude")
			label = (
				r.get(title_field)
				or r.get("display_name")
				or r.get("label")
				or r.get("title")
				or r.get("name")
			)
			reasons = []
			try:
				lat_f = float(lat) if lat not in (None, "") else None
				lon_f = float(lon) if lon not in (None, "") else None
			except (TypeError, ValueError):
				reasons.append("out_of_range")
				lat_f = lon_f = None

			if lat_f is None or lon_f is None:
				reasons.append("missing")
			else:
				if lat_f == 0.0 and lon_f == 0.0:
					reasons.append("null_island")
				if not (-90.0 <= lat_f <= 90.0) or not (-180.0 <= lon_f <= 180.0):
					reasons.append("out_of_range")
				else:
					# Heuristic swap: latitude in (±90) but value looks like a longitude
					# (|lat| > 60 AND |lon| < 60 for Iraq/Syria data is impossible since
					# lat there is ~30-38). Flag for review; never auto-fix.
					if abs(lat_f) > 55 and abs(lon_f) <= 55 and not (55 <= abs(lat_f) <= 70 and 8 <= abs(lon_f) <= 30):
						reasons.append("swapped")
				if not r.get("geo_precision"):
					reasons.append("no_precision")

			if reasons:
				for x in set(reasons):
					cats[x] += 1
				if len(bad) < 50:
					bad.append({
						"name": r["name"], "label": label,
						"latitude": lat, "longitude": lon,
						"reasons": sorted(set(reasons)),
					})

		totals[dt] = {"total": total, **cats}
		samples[dt] = bad

	return {"totals": totals, "samples": samples}
