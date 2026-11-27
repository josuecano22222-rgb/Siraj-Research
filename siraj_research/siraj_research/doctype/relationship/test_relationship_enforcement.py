# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
"""Live enforcement tests for the consolidated `Relationship` controller.

These exercise the Relationship controller's pair-membership, duplicate and
self-link rules (docs/decisions/relationship-consolidation.md §3.2, §8), the
HD-4 cross-data-group link guard (§3.2 / `permissions.validate_same_data_group_links`)
and the §8 endpoint delete-block, for **all five** endpoint DocTypes
(Person, Institution, Place, Siraj Event, Military Unit) on both the subject
and object side.

Every test seeds its own `Relationship Type` and its own allowed-pair child
rows, so a green result can never be vacuous: a type with no pairs would
skip enforcement, and these tests prove the rules fire when pairs exist.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

# All five endpoint DocTypes (title fields read from each endpoint's JSON).
ENDPOINT_TITLE_FIELDS = {
    "Person": ("name_en", "name_ar"),
    "Institution": ("name_en", "name_ar"),
    "Place": ("name_en", "name_ar"),
    "Siraj Event": ("title_en", "title_ar"),
    "Military Unit": ("unit_name", None),
}
ENDPOINT_VOCAB = {
    "Institution": ("Institution Type", "institution_type", "PR_INST_TYPE"),
    "Place": ("Place Type", "place_type", "PR_PLACE_TYPE"),
    "Siraj Event": ("Event Type", "event_type", "PR_EVENT_TYPE"),
}
ENDPOINT_REQUIRED_FIELDS = {
    "Military Unit": {"echelon": "Brigade", "status": "Active", "direct_personnel": 100},
}
ALL_ENDPOINTS = ("Person", "Institution", "Place", "Siraj Event", "Military Unit")


class TestRelationshipEnforcement(FrappeTestCase):
    # ------------------------------------------------------------------
    # Fixture helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_data_group(name):
        if not frappe.db.exists("Data Group", name):
            frappe.get_doc({"doctype": "Data Group", "group_name": name}).insert(
                ignore_permissions=True
            )

    @staticmethod
    def _ensure_vocab(doctype, code):
        label = f"PR Fix {code}"
        if frappe.db.exists(doctype, label):
            return label
        frappe.get_doc(
            {
                "doctype": doctype,
                "label_en": label,
                "label_ar": f"اختبار {code}",
                "code": code,
            }
        ).insert(ignore_permissions=True)
        return label

    def _make_endpoint(self, doctype, name, data_group="GD"):
        """Create a minimal endpoint record with all required fields set."""
        self._ensure_data_group(data_group)
        title_en, title_ar = ENDPOINT_TITLE_FIELDS.get(doctype, ("name_en", "name_ar"))
        payload = {"doctype": doctype, "data_group": data_group, title_en: name}
        if title_ar:
            payload[title_ar] = name
        vocab_doctype, vocab_field, vocab_code = ENDPOINT_VOCAB.get(
            doctype, (None, None, None)
        )
        if vocab_doctype:
            payload[vocab_field] = self._ensure_vocab(vocab_doctype, vocab_code)
        payload.update(ENDPOINT_REQUIRED_FIELDS.get(doctype, {}))
        return frappe.get_doc(payload).insert(ignore_permissions=True)

    def _make_type(self, code, *, symmetric=False, pairs=None, hierarchical=False):
        label = f"PhaseR {code}"
        if frappe.db.exists("Relationship Type", label):
            doc = frappe.get_doc("Relationship Type", label)
        else:
            doc = frappe.get_doc(
                {
                    "doctype": "Relationship Type",
                    "code": code,
                    "label_en": label,
                    "label_ar": f"مرحلة {code}",
                    "is_symmetric": 1 if symmetric else 0,
                    "is_hierarchical": 1 if hierarchical else 0,
                }
            ).insert(ignore_permissions=True)
        doc.set("allowed_pairs", [])  # clear any existing child rows before re-seeding
        for idx, (subject_doctype, object_doctype) in enumerate(pairs or [], start=1):
            doc.append(
                "allowed_pairs",
                {
                    "subject_doctype": subject_doctype,
                    "object_doctype": object_doctype,
                    "sort_order": idx,
                },
            )
        doc.save(ignore_permissions=True)
        return doc

    def _make_relationship(self, rel_type, subject_type, subject, object_type, object_name, **kw):
        payload = {
            "doctype": "Relationship",
            "relationship_type": rel_type,
            "subject_type": subject_type,
            "subject": subject,
            "object_type": object_type,
            "object": object_name,
            "naming_series": "REL-.####",
            "data_group": kw.pop("data_group", "GD"),
        }
        payload.update(kw)
        return frappe.get_doc(payload)

    @staticmethod
    def _cleanup(*docs):
        for doc in docs:
            if doc is None:
                continue
            if frappe.db.exists(doc.doctype, doc.name):
                try:
                    frappe.delete_doc(doc.doctype, doc.name, force=True, ignore_permissions=True)
                except frappe.ValidationError:
                    pass

    # ------------------------------------------------------------------
    # §3.2 pair membership
    # ------------------------------------------------------------------

    def test_invalid_pair_rejected(self):
        """A pair not in the type's allowed-pair rows is rejected; a seeded one saves."""
        rt = self._make_type("PR_ENF_INVALID", pairs=[("Person", "Institution")])
        person = self._make_endpoint("Person", "PR Enf Invalid Person")
        institution = self._make_endpoint("Institution", "PR Enf Invalid Inst")
        place = self._make_endpoint("Place", "PR Enf Invalid Place")
        try:
            with self.assertRaises(frappe.ValidationError):
                self._make_relationship(
                    rt.name, "Person", person.name, "Place", place.name
                ).insert(ignore_permissions=True)
            ok = self._make_relationship(
                rt.name, "Person", person.name, "Institution", institution.name
            ).insert(ignore_permissions=True)
            self.assertEqual(ok.subject, person.name)
        finally:
            self._cleanup(person, institution, place)

    # ------------------------------------------------------------------
    # §8 duplicates
    # ------------------------------------------------------------------

    def test_directed_duplicate_rejected(self):
        """A directed type rejects a repeat of the exact ordered pair."""
        rt = self._make_type("PR_ENF_DUP_DIR", pairs=[("Person", "Institution")])
        person = self._make_endpoint("Person", "PR Enf DupDir Person")
        institution = self._make_endpoint("Institution", "PR Enf DupDir Inst")
        try:
            first = self._make_relationship(
                rt.name, "Person", person.name, "Institution", institution.name
            ).insert(ignore_permissions=True)
            with self.assertRaises(frappe.ValidationError):
                self._make_relationship(
                    rt.name, "Person", person.name, "Institution", institution.name
                ).insert(ignore_permissions=True)
            self.assertTrue(first.name)
        finally:
            self._cleanup(person, institution)

    def test_symmetric_duplicate_rejected_both_orientations(self):
        """A symmetric type treats (A→B) and (B→A) as one edge: both repeats rejected."""
        rt = self._make_type(
            "PR_ENF_DUP_SYM",
            symmetric=True,
            pairs=[("Person", "Institution"), ("Institution", "Person")],
        )
        person = self._make_endpoint("Person", "PR Enf DupSym Person")
        institution = self._make_endpoint("Institution", "PR Enf DupSym Inst")
        try:
            first = self._make_relationship(
                rt.name, "Person", person.name, "Institution", institution.name
            ).insert(ignore_permissions=True)
            self.assertEqual(first.direction, "Symmetric")
            # Reversed orientation is the same symmetric edge.
            with self.assertRaises(frappe.ValidationError):
                self._make_relationship(
                    rt.name, "Institution", institution.name, "Person", person.name
                ).insert(ignore_permissions=True)
            # Same orientation again is also a duplicate.
            with self.assertRaises(frappe.ValidationError):
                self._make_relationship(
                    rt.name, "Person", person.name, "Institution", institution.name
                ).insert(ignore_permissions=True)
        finally:
            self._cleanup(person, institution)

    # ------------------------------------------------------------------
    # Self-update vs self-link
    # ------------------------------------------------------------------

    def test_self_update_accepted(self):
        """Re-saving a Relationship with its own endpoints unchanged is not a duplicate."""
        rt = self._make_type("PR_ENF_SELF_UPD", pairs=[("Person", "Institution")])
        person = self._make_endpoint("Person", "PR Enf SelfUpd Person")
        institution = self._make_endpoint("Institution", "PR Enf SelfUpd Inst")
        try:
            rel = self._make_relationship(
                rt.name, "Person", person.name, "Institution", institution.name
            ).insert(ignore_permissions=True)
            rel.description = "Updated provenance note"
            rel.role_as_stated = "Updated role"
            rel.title_en = "Updated title"
            rel.save(ignore_permissions=True)
            self.assertEqual(rel.description, "Updated provenance note")
        finally:
            self._cleanup(person, institution)

    def test_self_link_rejected_once_pairs_exist(self):
        """A non-hierarchical type rejects a record linked to itself once pairs exist."""
        rt = self._make_type("PR_ENF_SELF_LINK", pairs=[("Person", "Person")])
        person = self._make_endpoint("Person", "PR Enf SelfLink Person")
        try:
            with self.assertRaises(frappe.ValidationError):
                self._make_relationship(
                    rt.name, "Person", person.name, "Person", person.name
                ).insert(ignore_permissions=True)
        finally:
            self._cleanup(person)

    # ------------------------------------------------------------------
    # HD-4 cross data-group (§3.2 / permissions.validate_same_data_group_links)
    # ------------------------------------------------------------------

    def test_cross_group_rejected_on_subject_and_object_hd4(self):
        """HD-4: a cross-group link is rejected whether the foreign record is the
        subject or the object.

        `validate_same_data_group_links` runs on `validate` for every role
        including Administrator, so this is exercised at the controller layer
        here; the real-user permission path is covered by
        `test_21_relationship_cross_group_rejected_on_both_endpoints_hd4`.
        """
        rt = self._make_type("PR_ENF_HD4", pairs=[("Person", "Person")])
        gd_person = self._make_endpoint("Person", "PR Enf HD4 GD Person", data_group="GD")
        gc_person = self._make_endpoint("Person", "PR Enf HD4 GC Person", data_group="GC")
        gd_person_2 = None
        try:
            # Object-side cross-group: GD subject -> GC object.
            with self.assertRaises(frappe.PermissionError):
                self._make_relationship(
                    rt.name, "Person", gd_person.name, "Person", gc_person.name,
                    data_group="GD",
                ).insert(ignore_permissions=True)
            # Subject-side cross-group: GC subject -> GD object.
            with self.assertRaises(frappe.PermissionError):
                self._make_relationship(
                    rt.name, "Person", gc_person.name, "Person", gd_person.name,
                    data_group="GD",
                ).insert(ignore_permissions=True)
            # Positive control: same group on both endpoints saves.
            gd_person_2 = self._make_endpoint("Person", "PR Enf HD4 GD Person 2", data_group="GD")
            same = self._make_relationship(
                rt.name, "Person", gd_person.name, "Person", gd_person_2.name,
                data_group="GD",
            ).insert(ignore_permissions=True)
            self.assertEqual(same.data_group, "GD")
        finally:
            self._cleanup(gd_person, gc_person, gd_person_2)

    # ------------------------------------------------------------------
    # §8 endpoint delete blocking — all five DocTypes, both sides
    # ------------------------------------------------------------------

    def test_endpoint_delete_blocked_all_doctypes_both_sides(self):
        """Deleting an endpoint referenced by a Relationship is blocked on both
        the subject and object side, for every endpoint DocType."""
        for doctype in ALL_ENDPOINTS:
            with self.subTest(doctype=doctype):
                rt = self._make_type(
                    "PR_ENF_DEL",
                    pairs=[(doctype, "Person"), ("Person", doctype)],
                )
                endpoint = self._make_endpoint(doctype, f"PR Enf Del {doctype}")
                person = self._make_endpoint("Person", f"PR Enf Del Person {doctype}")
                try:
                    # Subject side: endpoint is the subject.
                    rel_subject = self._make_relationship(
                        rt.name, doctype, endpoint.name, "Person", person.name
                    ).insert(ignore_permissions=True)
                    with self.assertRaises(frappe.ValidationError):
                        frappe.delete_doc(doctype, endpoint.name, ignore_permissions=True)
                    # subject/object are Dynamic Link fields: Frappe's delete machinery
                    # can leave the row's link reference detectable, so remove the row
                    # with a direct hard delete rather than frappe.delete_doc.
                    frappe.db.delete("Relationship", {"name": rel_subject.name})

                    # Object side: endpoint is the object.
                    rel_object = self._make_relationship(
                        rt.name, "Person", person.name, doctype, endpoint.name
                    ).insert(ignore_permissions=True)
                    with self.assertRaises(frappe.ValidationError):
                        frappe.delete_doc(doctype, endpoint.name, ignore_permissions=True)
                    frappe.db.delete("Relationship", {"name": rel_object.name})

                    # No Relationship should reference the endpoint anymore.
                    self.assertFalse(
                        frappe.db.exists(
                            "Relationship",
                            {"subject_type": doctype, "subject": endpoint.name},
                        )
                        or frappe.db.exists(
                            "Relationship",
                            {"object_type": doctype, "object": endpoint.name},
                        )
                    )

                    # force=True skips Frappe's check_if_doc_is_dynamically_linked
                    # (a stale link reference for Dynamic Link fields) but still
                    # runs our before_delete guard; with no Relationship
                    # referencing the endpoint, the guard passes and the delete
                    # succeeds.
                    frappe.delete_doc(doctype, endpoint.name, force=True, ignore_permissions=True)
                    self.assertFalse(frappe.db.exists(doctype, endpoint.name))
                except Exception:
                    self._cleanup(endpoint, person)
                    raise
                self._cleanup(person)

    # ------------------------------------------------------------------
    # Migration-window tolerance: a type with NO pairs skips enforcement
    # ------------------------------------------------------------------

    def test_no_pairs_type_skips_enforcement(self):
        """A Relationship Type with no allowed-pair rows is unconstrained (§3.2
        migration window): any pair saves and duplicates are not rejected.

        This documents the kept tolerance. Step 3 seeds pairs for every type,
        so in production no type reaches this state; the test proves the
        documented behaviour rather than relying on it silently.
        """
        rt = self._make_type("PR_ENF_NOPAIRS", pairs=None)
        person = self._make_endpoint("Person", "PR Enf NoPairs Person")
        institution = self._make_endpoint("Institution", "PR Enf NoPairs Inst")
        try:
            first = self._make_relationship(
                rt.name, "Person", person.name, "Institution", institution.name
            ).insert(ignore_permissions=True)
            # Pair (Person, Institution) is NOT seeded, yet it saves (no pairs => skipped).
            self.assertEqual(first.subject, person.name)
            # The same ordered pair again is also accepted (duplicate skipped).
            second = self._make_relationship(
                rt.name, "Person", person.name, "Institution", institution.name
            ).insert(ignore_permissions=True)
            self.assertNotEqual(first.name, second.name)
        finally:
            self._cleanup(person, institution)
