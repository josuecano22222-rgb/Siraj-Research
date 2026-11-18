"""Install source reference values without overwriting site-managed records.

This module is intentionally not a whitelisted API. It runs after installation
or explicitly through ``bench execute``. All writes use Frappe documents.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import frappe

DATA = Path(__file__).parent / "reference_data"
DOMAIN_TYPES = {
	"authentication_level": "Authentication Level",
	"documentation_level": "Documentation Level",
	"person_status": "Person Status",
	"person_classification": "Person Classification",
	"place_type": "Place Type",
	"institution_type": "Institution Type",
	"institution_subcategory": "Institution Subcategory",
	"relationship_type": "Relationship Type",
	"source_type": "Source Type",
	"source_reliability": "Source Reliability",
	"event_type": "Event Type",
	"governance_system": "Governance System",
	"person_category": "Person Category",
	"military_service_status": "Military Service Status",
	"military_branch": "Military Branch",
	"leadership_quality": "Leadership Quality",
	"leadership_level": "Leadership Level",
}
# Original color tokens translated into valid Frappe Color values.
COLORS = {
	"gray": "#6b7280",
	"slate": "#64748b",
	"amber": "#d97706",
	"orange": "#ea580c",
	"red": "#dc2626",
	"rose": "#e11d48",
	"blue": "#2563eb",
	"indigo": "#4f46e5",
	"violet": "#7c3aed",
	"green": "#16a34a",
	"teal": "#0d9488",
}
STATES = ("Draft", "In Review", "Verified", "Published", "Needs Update", "Disputed", "Archived", "Rejected")


def _load(filename):
	return json.loads((DATA / filename).read_text(encoding="utf-8"))


class SeedReport:
	def __init__(self):
		self.created = Counter()
		self.existing = Counter()
		self.skipped = Counter()
		self.examples = []

	def skip(self, doctype, code, reason):
		self.skipped[doctype] += 1
		if len(self.examples) < 25:
			self.examples.append({"doctype": doctype, "code": code, "reason": reason})

	def result(self):
		return {
			"created": dict(self.created),
			"existing": dict(self.existing),
			"skipped": dict(self.skipped),
			"skip_examples": self.examples,
		}


def _insert(doctype, values, report):
	doc = frappe.get_doc({"doctype": doctype, **values})
	doc.insert(ignore_permissions=True)
	report.created[doctype] += 1
	return doc


def _seed_lookups(data, report):
	for domain, doctype in DOMAIN_TYPES.items():
		resolved, created = {}, {}
		for code, label_en, label_ar, order, meta, color in data["domains"][domain]:
			name = frappe.db.exists(doctype, {"code": code})
			if name:
				resolved[code] = name
				report.existing[doctype] += 1
				continue
			# Name is derived from label_en. Do not overwrite or associate an
			# existing record that has a different code with this source value.
			if frappe.db.exists(doctype, label_en):
				report.skip(doctype, code, "name already belongs to a different code")
				continue
			values = {
				"code": code,
				"label_en": label_en,
				"label_ar": label_ar,
				"sort_order": order,
				"disabled": 0,
				"is_system": int(domain not in ("leadership_quality", "leadership_level")),
			}
			if color in COLORS:
				values["color"] = COLORS[color]
			if domain == "relationship_type":
				values["is_symmetric"] = int(bool((meta or {}).get("symmetric")))
			doc = _insert(doctype, values, report)
			resolved[code] = doc.name
			created[code] = (doc, meta or {})
		# A Link cannot be validated until the inverse has been inserted.
		# Only touch rows created in this run, never an existing customised row.
		if domain == "relationship_type":
			for code, (doc, meta) in created.items():
				inverse = meta.get("inverse")
				if inverse and resolved.get(inverse):
					doc.inverse_type = resolved[inverse]
					doc.save(ignore_permissions=True)
				elif inverse:
					report.skip(doctype, code, "inverse type could not be resolved")


def _seed_workflow_states(report):
	for name in STATES:
		if frappe.db.exists("Workflow State", name):
			report.existing["Workflow State"] += 1
		else:
			_insert("Workflow State", {"workflow_state_name": name}, report)


def _country_index(report):
	groups = defaultdict(list)
	for row in frappe.get_all("Country", fields=["name", "code"], limit_page_length=0):
		if row.get("code"):
			groups[str(row["code"]).upper()].append(row["name"])
	# An ambiguous ISO code is not resolved by guessing a country.
	return {code: names[0] for code, names in groups.items() if len(names) == 1}


def _existing_geo(doctype, parent_field):
	rows = frappe.get_all(doctype, fields=["name", "code", parent_field], limit_page_length=0)
	result = defaultdict(list)
	for row in rows:
		if row.get("code"):
			result[str(row["code"]).casefold()].append(row)
	return result


def _seed_geo_level(doctype, parent_field, rows, parent_map, report):
	existing = _existing_geo(doctype, parent_field)
	resolved = {}
	for row in rows:
		code, parent_code = row["code"], row["parent"]
		parent = parent_map.get(parent_code)
		if not parent:
			report.skip(doctype, code, "parent is missing or ambiguous: " + parent_code)
			continue
		matches = existing.get(code.casefold(), [])
		if matches:
			if len(matches) != 1 or matches[0].get(parent_field) != parent["name"]:
				report.skip(doctype, code, "existing record has a conflicting parent or code")
				continue
			name = matches[0]["name"]
			report.existing[doctype] += 1
		else:
			# Frappe names these geographic DocTypes by code.
			if frappe.db.exists(doctype, code):
				report.skip(doctype, code, "name already exists with a different code")
				continue
			values = {
				"code": code,
				"label_en": row["label_en"],
				"label_ar": row["label_ar"],
				"sort_order": int(row.get("sort") or 100),
				"disabled": 0,
				"is_system": 0,
				parent_field: parent["name"],
			}
			# Fetch-from fields are normally populated by the form; populate
			# them explicitly for server-side inserts without changing a parent.
			values.update(parent.get("ancestors", {}))
			doc = _insert(doctype, values, report)
			name = doc.name
			existing[code.casefold()].append({"name": name, "code": code, parent_field: parent["name"]})
		resolved[code] = {
			"name": name,
			"ancestors": {**parent.get("ancestors", {}), parent_field: parent["name"]},
		}
	return resolved


def _seed_geography(data, report):
	country_map = {code: {"name": name, "ancestors": {}} for code, name in _country_index(report).items()}
	governorates = [{**g, "parent": g["country"]} for g in _load("governorates.json")]
	gov_map = _seed_geo_level("Governorate", "country", governorates, country_map, report)
	districts = [
		{"code": code, "parent": parent, "label_en": en, "label_ar": ar, "sort": order}
		for code, parent, en, ar, order in data["legacy_districts"]
	]
	districts.extend({**d, "parent": d["governorate"]} for d in _load("districts.json"))
	dist_map = _seed_geo_level("District", "governorate", districts, gov_map, report)
	admin = _load("admin_units.json")
	municipalities = [row for row in admin if row["level"] == "municipality"]
	villages = [row for row in admin if row["level"] == "village"]
	communities = [row for row in admin if row["level"] == "community"]
	muni_map = _seed_geo_level("Municipality", "district", municipalities, dist_map, report)
	village_map = _seed_geo_level("Village", "municipality", villages, muni_map, report)
	_seed_geo_level("Community", "village", communities, village_map, report)


def seed_master_data():
	"""Add missing original reference values; return a report for operators.

	No commits, destructive updates, fictional samples, or permission bypassing
	endpoints. Frappe controls the surrounding install/bench transaction.
	"""
	data = _load("lookups.json")
	report = SeedReport()
	_seed_workflow_states(report)
	_seed_lookups(data, report)
	_seed_geography(data, report)
	result = report.result()
	if result["skipped"]:
		print("SIRAJ master data: some entries were skipped; inspect the following report:", result)
	return result
