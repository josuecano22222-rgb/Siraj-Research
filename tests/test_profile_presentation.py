"""Pure-Python checks for the Explorer profile presentation/i18n layer."""

import copy
import unittest

from siraj_research.profile_presentation import (
	collect_strings,
	display_value,
	group_for_field,
	normalise_children,
	normalise_sections,
	organise_profile,
	strip_demo_tag,
)


def field(fieldname, label, value, fieldtype="Data", **extra):
	return dict(
		{
			"fieldname": fieldname,
			"label": label,
			"fieldtype": fieldtype,
			"options": extra.pop("options", ""),
			"value": value,
		},
		**extra,
	)


def raw_profile():
	"""Minimal mirror of the demo Person payload shown in the Explorer panel."""
	return {
		"sections": [
			{
				"heading": "sb_identity",
				"fields": [
					field("naming_series", "Series", "PER-.####", "Select"),
					field("display_name", "Display name", "Gen. Ari Saeed (DEMO) [DEMO]"),
					field("name_ar", "Name (Arabic)", "اللواء آري سعيد [DEMO]"),
				],
			},
			{
				"heading": "Birth",
				"fields": [
					field("birth_date_as_stated", "Date of birth (as stated)", "1969"),
					field("birth_date", "Date of birth (comparable)", "1969-01-01", "Date"),
					field("birth_date_precision", "Date of birth precision", "year", "Select"),
				],
			},
			{
				"heading": "Classification",
				"fields": [
					field(
						"person_status",
						"Current status",
						{"type": "link", "doctype": "Person Status", "name": "active", "title": "Active"},
						"Link",
					),
					field(
						"category",
						"Category",
						{
							"type": "link",
							"doctype": "Person Category",
							"name": "military",
							"title": "Military",
						},
						"Link",
					),
					field(
						"current_position_as_stated", "Current position (as stated)", "KRG Division commander"
					),
				],
			},
			{
				"heading": "Public activity",
				"fields": [
					field(
						"social_accounts",
						"Official accounts",
						[{"handle": "ari_demo"}],
						"Table",
						options="Social Account",
					),
				],
			},
			{
				"heading": "Position (this record's own)",
				"fields": [
					field("latitude", "Latitude", 31.695265, "Float"),
					field("longitude", "Longitude", 34.86709, "Float"),
					field("geo_precision", "Coordinate precision", "centroid", "Select"),
					field("geocoding_method", "How the point was obtained", "map_pick", "Select"),
				],
			},
			{
				"heading": "Source & verification",
				"fields": [
					field(
						"documentation_level",
						"Documentation level",
						{
							"type": "link",
							"doctype": "Documentation Level",
							"name": "partial",
							"title": "Partial",
						},
						"Link",
					),
					field(
						"authentication_level",
						"Authentication level",
						{
							"type": "link",
							"doctype": "Authentication Level",
							"name": "single",
							"title": "Single source",
						},
						"Link",
					),
					field(
						"workflow_state",
						"Record status",
						{
							"type": "link",
							"doctype": "Workflow State",
							"name": "verified",
							"title": "Verified",
						},
						"Link",
					),
				],
			},
			{
				# Tab Break was skipped by the old renderer: these fields used to
				# be appended to the immediately preceding "External identifiers"
				# section.
				"heading": "External identifiers",
				"fields": [
					field("external_identifiers", "External identifiers", [{"scheme": "US"}], "Table"),
					field("completeness_score", "Completeness (%)", 0, "Int"),
				],
			},
		],
		"children": {
			"social_accounts": {
				"label": "Official accounts",
				"options": "Social Account",
				"rows": [
					{
						"platform": {
							"label": "Platform",
							"value": {
								"type": "link",
								"doctype": "Social Platform",
								"name": "telegram",
								"title": "Telegram",
							},
						}
					},
					{
						"platform": {
							"label": "Platform",
							"value": {
								"type": "link",
								"doctype": "Social Platform",
								"name": "telegram",
								"title": "Telegram",
							},
						},
						"url": {"label": "URL", "value": "https://t.me/ari_demo"},
					},
				],
			},
			"external_identifiers": {
				"label": "External identifiers",
				"rows": [
					{
						"scheme": {
							"label": "Scheme",
							"value": {
								"type": "link",
								"doctype": "External ID Scheme",
								"name": "us",
								"title": "United States",
							},
						}
					},
				],
			},
			"evidence": {
				"label": "Evidence",
				"rows": [
					{
						"source": {
							"label": "Source",
							"value": {
								"type": "link",
								"doctype": "Source",
								"name": "S1",
								"title": "MoD press release",
							},
						},
						"support_type": {"label": "Support", "fieldtype": "Select", "value": "supports"},
					},
				],
			},
		},
	}


class ProfilePresentationTest(unittest.TestCase):
	def test_table_fields_become_tables_not_object_strings(self):
		profile = organise_profile(raw_profile())
		scalar = [f for section in profile["sections"] for f in section["fields"]]
		self.assertNotIn("social_accounts", [f["fieldname"] for f in scalar])
		self.assertNotIn("external_identifiers", [f["fieldname"] for f in scalar])
		self.assertNotIn("[object Object]", str(profile["sections"]))
		self.assertIn("social_accounts", profile["children"])
		self.assertEqual(profile["children"]["social_accounts"]["label"], "Official accounts")

	def test_semantic_groups_are_ordered_and_tab_leak_is_fixed(self):
		profile = organise_profile(raw_profile())
		order = [section["id"] for section in profile["sections"]]
		self.assertEqual(
			order,
			[
				"identity",
				"life",
				"classification",
				"public",
				"location",
				"provenance",
				"evidence",
				"identifiers",
				"quality",
			],
		)
		quality = next(section for section in profile["sections"] if section["id"] == "quality")
		self.assertEqual([f["fieldname"] for f in quality["fields"]], ["completeness_score"])
		identifiers = next(section for section in profile["sections"] if section["id"] == "identifiers")
		self.assertEqual(identifiers["fields"], [])

	def test_i18n_metadata_preserves_source_values(self):
		profile = organise_profile(raw_profile())
		fields = {f["fieldname"]: f for section in profile["sections"] for f in section["fields"]}
		precision = fields["birth_date_precision"]
		self.assertEqual(precision["value"], "year")
		self.assertEqual(precision["value_source"], "year")
		self.assertTrue(precision["translatable_value"])
		self.assertEqual(precision["value_kind"], "enum")
		self.assertEqual(fields["latitude"]["value_kind"], "number")
		self.assertEqual(fields["person_status"]["value_kind"], "link")
		self.assertEqual(fields["person_status"]["value"]["title"], "Active")
		self.assertFalse(fields["person_status"]["translatable_value"])
		self.assertTrue(fields["name_ar"]["value_rtl"])
		self.assertEqual(fields["display_name"]["label_source"], "Display name")
		self.assertTrue(fields["display_name"]["value_demo"])
		self.assertFalse(fields["display_name"]["label_demo"])

	def test_child_columns_are_a_union_in_meta_order(self):
		tables = normalise_children(raw_profile()["children"])
		columns = [column["fieldname"] for column in tables["social_accounts"]["columns"]]
		self.assertEqual(columns, ["platform", "url"])
		self.assertEqual(tables["social_accounts"]["section"], "public")
		self.assertEqual(tables["evidence"]["section"], "evidence")
		cell = tables["evidence"]["rows"][0]["support_type"]
		self.assertEqual(cell["value_source"], "supports")
		self.assertTrue(cell["translatable_value"])

	def test_catalogue_contains_every_source_string_but_no_translated_leak(self):
		profile = organise_profile(raw_profile())
		strings = collect_strings(profile)
		for expected in (
			"Identity",
			"Birth",
			"Life & dates",
			"Date of birth precision",
			"year",
			"Official accounts",
			"Platform",
			"supports",
			"Support",
		):
			self.assertIn(expected, strings)
		self.assertFalse(any("object Object" in item for item in strings))
		self.assertEqual(profile["presentation"]["version"], 2)
		self.assertFalse(profile["presentation"]["rtl"])

	def test_relationship_specific_fields_are_grouped_as_relationship(self):
		self.assertEqual(group_for_field("display_name", "Relationship"), "relationship")
		self.assertEqual(group_for_field("display_name", "Person"), "identity")
		sections = normalise_sections(
			[{"heading": "Relationship", "fields": [field("display_name", "Display name", "Member")]}],
			"Relationship",
		)
		self.assertEqual(sections[0]["id"], "relationship")

	def test_pure_helpers_are_safe_for_odd_values(self):
		self.assertEqual(strip_demo_tag("Name [DEMO]"), ("Name", True))
		self.assertEqual(strip_demo_tag("Sans marqueur"), ("Sans marqueur", False))
		self.assertEqual(display_value(None), "")
		self.assertEqual(display_value(True), "Yes")
		self.assertEqual(display_value(False), "No")
		self.assertEqual(display_value({"a": 1, "b": [2]}), '{"a": 1, "b": [2]}')

	def test_organise_does_not_mutate_caller_payload(self):
		payload = raw_profile()
		before = copy.deepcopy(payload)
		organise_profile(payload)
		self.assertEqual(payload, before)


if __name__ == "__main__":
	unittest.main()
