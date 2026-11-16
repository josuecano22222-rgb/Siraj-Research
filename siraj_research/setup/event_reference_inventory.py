"""Read-only, best-effort inventory of metadata-defined references to Event.

Administrator-run, potentially expensive on large sites. This does not perform
or authorize migration and does not inspect arbitrary code, text, or external
systems. Do not publish its output without reviewing operational metadata.

Scans references to BOTH the Frappe core calendar "Event" and the SIRAJ
"Research Event" doctype so the operator can distinguish calendar links from
research-record links without guessing.
"""

import frappe

TARGETS = ("Event", "Research Event")


def inspect_metadata_event_references():
	"""Count fixed and dynamic references to each Event-like doctype.

	A dynamic selector is counted even if its associated target is empty;
	this conservatively reports possible references, not ownership. Counts
	are per (field, target) and can overlap. Unknown/skipped fields are never
	treated as zero.
	"""
	results, skipped = [], []
	checked_fields = 0
	doctypes = frappe.get_all(
		"DocType", fields=["name", "issingle", "is_virtual"], order_by="name asc", limit_page_length=0
	)
	for row in doctypes:
		name = row["name"]
		if row.get("issingle") or row.get("is_virtual"):
			skipped.append({"doctype": name, "reason": "single or virtual DocType"})
			continue
		if not frappe.db.table_exists(name):
			skipped.append({"doctype": name, "reason": "table absent"})
			continue
		try:
			meta = frappe.get_meta(name)
			fields = list(meta.fields or [])
		except Exception:
			# Keep the report usable while surfacing incompleteness. Do not
			# return tracebacks, which may contain sensitive metadata.
			skipped.append({"doctype": name, "reason": "metadata unavailable"})
			continue

		# Collect Link/Dynamic-Link fields per target.
		per_target_direct = {t: set() for t in TARGETS}
		selectors = set()
		for df in fields:
			field = df.get("fieldname")
			kind, options = df.get("fieldtype"), df.get("options") or ""
			if not field:
				continue
			if kind == "Link" and options in per_target_direct:
				per_target_direct[options].add(field)
			if (kind == "Link" and options == "DocType") or (
				kind == "Select" and any(t in options.splitlines() for t in TARGETS)
			):
				selectors.add(field)
			if kind == "Dynamic Link" and options:
				selectors.add(options)

		# Direct Link counts per target
		for target in TARGETS:
			for field in sorted(per_target_direct[target]):
				if not frappe.db.has_column(name, field):
					skipped.append(
						{"doctype": name, "field": field, "target": target, "reason": "column absent"}
					)
					continue
				try:
					count = frappe.db.count(name, {field: ["is", "set"]})
				except Exception:
					skipped.append(
						{"doctype": name, "field": field, "target": target, "reason": "count unavailable"}
					)
					continue
				checked_fields += 1
				if count:
					results.append(
						{"doctype": name, "field": field, "kind": "direct", "target": target, "count": count}
					)

		# Selector fields (DocType-link or Select containing Event targets)
		for field in sorted(selectors):
			if not frappe.db.has_column(name, field):
				skipped.append({"doctype": name, "field": field, "reason": "column absent"})
				continue
			for target in TARGETS:
				try:
					count = frappe.db.count(name, {field: target})
				except Exception:
					skipped.append(
						{"doctype": name, "field": field, "target": target, "reason": "count unavailable"}
					)
					continue
				checked_fields += 1
				if count:
					results.append(
						{
							"doctype": name,
							"field": field,
							"kind": "selector",
							"target": target,
							"count": count,
						}
					)

	return {
		"targets": TARGETS,
		"checked_fields": checked_fields,
		"nonzero_counts": results,
		"skipped": skipped,
		"note": (
			"Best-effort metadata scan, not proof of safety or ownership. Zeros are omitted; "
			"skipped entries are unknown. Counts may overlap across targets/fields, and selectors "
			"can be set to a target string without a valid row. Single and virtual doctypes, free "
			"text, scripts, unmodeled tables, external systems and other dependencies require "
			"separate review."
		),
	}
