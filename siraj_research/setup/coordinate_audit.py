"""Read-only, aggregate coordinate migration inventory for administrator use.

Not whitelisted
 do not call on a production site without operational approval.
This does not change data or establish a transactionally consistent snapshot.
"""

from collections import Counter

import frappe

from siraj_research.utils.coordinates import bounded_coordinate

# Fixed committed legacy names. The unreleased Event split needs separate review.
TYPES = ("Person", "Institution", "Place", "Research Event", "Military Unit", "Operational Deployment")


def _classify(value, maximum):
	return bounded_coordinate(value, maximum)


def summarize(rows):
	"""Count categories without returning identifiers or coordinate values."""
	count = Counter(
		{
			key: 0
			for key in (
				"rows",
				"both_blank",
				"incomplete",
				"invalid_latitude",
				"invalid_longitude",
				"complete_valid",
				"ambiguous_zero_pair",
			)
		}
	)
	for row in rows:
		count["rows"] += 1
		a, av = _classify(row.get("latitude"), 90)
		b, bv = _classify(row.get("longitude"), 180)
		count["invalid_latitude"] += a == "invalid"
		count["invalid_longitude"] += b == "invalid"
		if a == b == "blank":
			count["both_blank"] += 1
		elif (a == "blank") != (b == "blank"):
			count["incomplete"] += 1
		elif a == b == "valid":
			count["complete_valid"] += 1
			count["ambiguous_zero_pair"] += av == 0 and bv == 0
	return dict(count)


def _column_descriptions(doctype):
	"""Use bound parameters and a fixed table name for the active database/schema."""
	dialect = frappe.db.db_type
	if dialect == "mariadb":
		schema = "table_schema = DATABASE()"
	elif dialect == "postgres":
		schema = "table_schema = current_schema()"
	else:
		return None
	rows = frappe.db.sql(
		"SELECT column_name, data_type, numeric_precision, numeric_scale, "
		"character_maximum_length, is_nullable, column_default FROM information_schema.columns "
		f"WHERE {schema} AND table_name = %s AND column_name IN (%s, %s)",
		("tab" + doctype, "latitude", "longitude"),
		as_dict=True,
	)
	return {
		row["column_name"]: {
			key: row.get(key)
			for key in (
				"data_type",
				"numeric_precision",
				"numeric_scale",
				"character_maximum_length",
				"is_nullable",
			)
		}
		| {"has_default": row.get("column_default") is not None}
		for row in rows
	}


def inspect_coordinate_migration():
	"""Inspect fixed legacy doctypes and counts, with no writes or record output.

	       This uses privileged `get_all` intentionally and may read all rows
	it is a
	       bench-only administrator diagnostic, not a permission-filtered API. Counts
	       and schema can be sensitive. Concurrent edits can change scan results.
	"""
	report = {"database_type": frappe.db.db_type, "doctypes": {}}
	for doctype in TYPES:
		if not frappe.db.exists("DocType", doctype):
			report["doctypes"][doctype] = {"status": "doctype_missing"}
			continue
		meta = frappe.get_meta(doctype)
		fields = {name: meta.get_field(name) for name in ("latitude", "longitude")}
		columns = _column_descriptions(doctype)
		entry = {
			"metadata_module": getattr(meta, "module", None),
			"metadata": {
				name: (
					{"fieldtype": field.fieldtype, "precision": field.precision, "length": field.length}
					if field
					else None
				)
				for name, field in fields.items()
			},
			"columns": columns,
		}
		report["doctypes"][doctype] = entry
		if not all(fields.values()) or columns is None or not all(name in columns for name in fields):
			entry["status"] = "missing_fields_or_unrecognized_database"
			continue

		def rows():
			last = None
			while True:
				page = frappe.get_all(
					doctype,
					fields=["name", "latitude", "longitude"],
					filters={"name": [">", last]} if last is not None else {},
					order_by="name asc",
					limit_page_length=200,
				)
				if not page:
					return
				yield from page
				last = page[-1]["name"]
				if len(page) < 200:
					return

		entry.update(status="scanned", counts=summarize(rows()))
	return report
