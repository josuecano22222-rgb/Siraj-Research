# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
"""Family tab contracts: child DocType JSON shape and pure helper behaviour.

The DocType-level behaviour (hidden-value preservation, throws, autofill,
summary content) runs bench-side in siraj_research.test_person_family; this
file keeps the JSON contracts and helpers fast and importable without a
Frappe site.
"""

import json
from pathlib import Path

from siraj_research.utils.family import build_family_summary, derive_is_grandparent

DOCTYPES = Path("siraj_research/siraj_research/doctype")


def load(folder: str) -> dict:
	return json.loads((DOCTYPES / folder / f"{folder}.json").read_text(encoding="utf-8"))


class TestChildDocTypes:
	def test_identity_flags(self):
		for folder in ("person_child", "person_sibling", "person_grandchild"):
			doc = load(folder)
			assert doc["istable"] == 1, folder
			assert doc["autoname"] == "hash", folder
			assert doc["permissions"] == [], folder
			assert doc["module"] == "Siraj Research", folder
			assert doc["description"], folder

	def test_field_order_matches_fields(self):
		for folder in ("person_child", "person_sibling", "person_grandchild"):
			doc = load(folder)
			names = [f["fieldname"] for f in doc["fields"]]
			assert doc["field_order"] == names, folder

	def test_sibling_link_is_to_person_only(self):
		sib = load("person_sibling")
		link = next(f for f in sib["fields"] if f["fieldname"] == "person")
		assert link["fieldtype"] == "Link" and link["options"] == "Person"
		# The other two child types must carry no Person link at all — the
		# exclusivity rule: spouse/children/grandchildren never link out.
		for folder in ("person_child", "person_grandchild"):
			doc = load(folder)
			links = [f for f in doc["fields"] if f["fieldtype"] == "Link"]
			assert links == [], folder

	def test_grandchild_through_child_is_select_without_options(self):
		doc = load("person_grandchild")
		through = next(f for f in doc["fields"] if f["fieldname"] == "through_child")
		assert through["fieldtype"] == "Select"
		# Options are filled client-side from the Children table.
		assert through.get("options") in (None, "")

	def test_required_names_in_list_view(self):
		for folder, name_field in (
			("person_child", "child_name"),
			("person_sibling", "sibling_name"),
			("person_grandchild", "grandchild_name"),
		):
			doc = load(folder)
			f = next(x for x in doc["fields"] if x["fieldname"] == name_field)
			assert f.get("reqd") == 1, folder
			assert f.get("in_list_view"), folder


class TestPersonFamilyTab:
	def person(self) -> dict:
		return load("person")

	def test_tab_sits_before_evidence(self):
		names = [f["fieldname"] for f in self.person()["fields"]]
		assert "tab_family" in names
		assert names.index("tab_family") < names.index("tab_evidence")

	def test_family_fields_in_field_order(self):
		doc = self.person()
		family_names = {
			f["fieldname"]
			for f in doc["fields"]
			if f["fieldname"]
			in {
				"marital_status",
				"family_summary",
				"spouse_name",
				"children",
				"grandchildren",
				"siblings",
				"father_name",
				"family_notes",
			}
		}
		assert family_names <= set(doc["field_order"])
		# The whole document stays in sync (Frappe contract).
		missing = [f["fieldname"] for f in doc["fields"] if f["fieldname"] not in doc["field_order"]]
		assert missing == []

	def test_personal_identifiers_and_phone_lists_cover_related_people(self):
		doc = self.person()
		fields = {f["fieldname"]: f for f in doc["fields"]}
		for name in ("personal_id_number", "phone_numbers"):
			assert fields[name]["permlevel"] == 1
		assert fields["personal_id_number"]["fieldtype"] == "Data"
		assert fields["phone_numbers"]["fieldtype"] == "Small Text"
		assert "one mobile number per line" in fields["phone_numbers"]["description"]

		for name in (
			"spouse_personal_id_number", "spouse_phone_numbers",
			"father_personal_id_number", "father_phone_numbers",
			"mother_personal_id_number", "mother_phone_numbers",
		):
			assert name in fields
			assert fields[name]["permlevel"] == 1

		for folder in ("person_child", "person_sibling", "person_grandchild"):
			member_fields = {f["fieldname"]: f for f in load(folder)["fields"]}
			assert member_fields["personal_id_number"]["fieldtype"] == "Data"
			assert member_fields["phone_numbers"]["fieldtype"] == "Small Text"
			assert member_fields["personal_id_number"]["permlevel"] == 1
			assert member_fields["phone_numbers"]["permlevel"] == 1

	def test_person_profile_fields_are_optional_and_accounts_are_repeatable(self):
		doc = self.person()
		fields = {f["fieldname"]: f for f in doc["fields"]}
		optional_fields = (
			"name_ar", "name_en", "birth_date_as_stated", "birthplace",
			"birthplace_as_stated", "current_residence", "marital_status",
			"nationality", "gender", "personal_id_number", "phone_numbers",
			"social_accounts",
		)
		for name in optional_fields:
			assert not fields[name].get("reqd"), name
			assert not fields[name].get("mandatory_depends_on"), name
		assert fields["gender"]["options"] == "\nMale\nFemale\nUnknown"
		assert fields["social_accounts"]["fieldtype"] == "Table"
		assert fields["social_accounts"]["options"] == "Social Account"
		account = load("social_account")
		platform = next(f for f in account["fields"] if f["fieldname"] == "platform")
		assert not platform.get("reqd")

	def test_per_person_custom_label_fields(self):
		doc = self.person()
		fields = {f["fieldname"]: f for f in doc["fields"]}
		assert fields["additional_fields"]["fieldtype"] == "Table"
		assert fields["additional_fields"]["options"] == "Person Additional Field"
		custom = load("person_additional_field")
		custom_fields = {f["fieldname"]: f for f in custom["fields"]}
		assert custom_fields["field_label"]["reqd"] == 1
		assert custom_fields["field_value"]["fieldtype"] == "Small Text"
		assert not custom_fields["field_value"].get("reqd")

	def test_table_options_point_at_child_doctypes(self):
		fields = {f["fieldname"]: f for f in self.person()["fields"]}
		assert fields["children"]["options"] == "Person Child"
		assert fields["grandchildren"]["options"] == "Person Grandchild"
		assert fields["siblings"]["options"] == "Person Sibling"

	def test_marital_status_options(self):
		fields = {f["fieldname"]: f for f in self.person()["fields"]}
		options = fields["marital_status"]["options"].split("\n")
		assert options == ["", "Single", "Married"]

	def test_conditional_visibility(self):
		fields = {f["fieldname"]: f for f in self.person()["fields"]}
		married = "eval:doc.marital_status == 'Married'"
		assert fields["sb_spouse"]["depends_on"] == married
		assert fields["sb_children"]["depends_on"] == married
		grand = "eval:doc.marital_status == 'Married' && doc.is_grandparent"
		assert fields["sb_grandchildren"]["depends_on"] == grand
		# Siblings and origin stay visible regardless of marital status.
		assert "depends_on" not in fields["sb_siblings"]
		assert "depends_on" not in fields["sb_family_origin"]

	def test_no_person_links_beyond_the_sibling_exception(self):
		"""Only father_person and the sibling row's person may link a Person."""
		fields = {f["fieldname"]: f for f in self.person()["fields"]}
		person_links = {
			name
			for name, f in fields.items()
			if f["fieldtype"] == "Link" and f.get("options") == "Person"
		}
		assert person_links == {"father_person"}

	def test_search_fields_include_family_summary(self):
		assert "family_summary" in self.person()["search_fields"]


class TestHelpers:
	def test_derive_is_grandparent(self):
		assert derive_is_grandparent([0, 0, 0]) == 0
		assert derive_is_grandparent([]) == 0
		assert derive_is_grandparent([0, 2, 0]) == 1
		assert derive_is_grandparent([None, 1]) == 1
		assert derive_is_grandparent(["", 0]) == 0

	def build(self, **overrides):
		translate = overrides.pop("translate", lambda s: s)
		data = {
			"marital_status": "Married",
			"spouse_name": "Amina",
			"children_count": 2,
			"grandchildren_count": 3,
			"siblings_count": 4,
		}
		data.update(overrides)
		return build_family_summary(data, translate=translate)

	def test_married_summary_parts(self):
		summary = self.build()
		assert summary == "Married · Spouse: Amina · Children: 2 · Grandchildren: 3 · Siblings: 4"

	def test_single_summary_is_bare(self):
		summary = self.build(
			marital_status="Single", spouse_name=None,
			children_count=0, grandchildren_count=0,
		)
		assert summary == "Single · Siblings: 4"

	def test_married_without_name_still_marks_the_spouse(self):
		summary = self.build(spouse_name=None)
		assert summary.startswith("Married · Spouse: unknown · Children: 2")

	def test_counts_only_appear_when_positive(self):
		summary = self.build(children_count=0, grandchildren_count=0, siblings_count=0)
		assert summary == "Married · Spouse: Amina"

	def test_every_string_is_a_translation_source(self):
		seen = set()

		def spy(text):
			seen.add(text)
			return text

		self.build(translate=spy)
		assert "Married" in seen
		assert "Spouse: {0}" in seen
		assert "Children: {0}" in seen
		assert "Grandchildren: {0}" in seen
		assert "Siblings: {0}" in seen
		# Empty-string sources would poison ar.csv.
		assert "" not in seen
