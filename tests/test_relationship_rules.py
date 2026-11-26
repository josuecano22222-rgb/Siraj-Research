# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
"""Pure-Python tests for the Relationship pair/duplicate helpers.

These exercise `siraj_research.utils.relationship_rules` with no frappe
dependency, so they run in the sandbox and pin the consolidation rules from
`docs/decisions/relationship-consolidation.md` §3.2 and §8 before the
`Relationship` controller and child-table schema land.
"""

from __future__ import annotations

import pytest

from siraj_research.utils.relationship_rules import (
    directed_pair_key,
    duplicate_key,
    pair_allowed,
    symmetric_pair_key,
)

# The 14 association DocTypes map to this default allowed-pair set (doc §3.3).
DEFAULT_PAIRS = [
    ("Siraj Event", "Person"),
    ("Siraj Event", "Institution"),
    ("Siraj Event", "Place"),
    ("Siraj Event", "Military Unit"),
    ("Person", "Siraj Event"),
    ("Person", "Institution"),
    ("Person", "Place"),
    ("Person", "Military Unit"),
    ("Institution", "Siraj Event"),
    ("Institution", "Place"),
    ("Institution", "Military Unit"),
    ("Military Unit", "Siraj Event"),
    ("Military Unit", "Institution"),
    ("Military Unit", "Place"),
]


class TestPairAllowed:
	def test_directed_exact_row_required(self):
		# A directed type only accepts the exact ordered row.
		assert pair_allowed(DEFAULT_PAIRS, "Person", "Institution", symmetric=False)
		assert not pair_allowed(DEFAULT_PAIRS, "Institution", "Person", symmetric=False)

	def test_directed_missing_pair_rejected(self):
		# (Place, Person) is not in the set.
		assert not pair_allowed(DEFAULT_PAIRS, "Place", "Person", symmetric=False)

	def test_symmetric_accepts_either_orientation(self):
		# A symmetric type accepts (A, B) if either orientation is present.
		assert pair_allowed(DEFAULT_PAIRS, "Person", "Institution", symmetric=True)
		assert pair_allowed(DEFAULT_PAIRS, "Institution", "Person", symmetric=True)

	def test_symmetric_rejects_absent_pair(self):
		assert not pair_allowed(DEFAULT_PAIRS, "Source", "Person", symmetric=True)

	def test_empty_allowed_set_rejects_everything(self):
		assert not pair_allowed([], "Person", "Institution", symmetric=False)
		assert not pair_allowed([], "Person", "Institution", symmetric=True)


class TestDuplicateKey:
	def test_directed_order_matters(self):
		a = duplicate_key("T", "Person", "P1", "Institution", "I1", symmetric=False)
		b = duplicate_key("T", "Institution", "I1", "Person", "P1", symmetric=False)
		assert a != b, "directed (A→B) and (B→A) must be distinct edges"

	def test_directed_same_edge_same_key(self):
		a = duplicate_key("T", "Person", "P1", "Institution", "I1", symmetric=False)
		b = duplicate_key("T", "Person", "P1", "Institution", "I1", symmetric=False)
		assert a == b

	def test_symmetric_orientation_normalized(self):
		a = duplicate_key("T", "Person", "P1", "Institution", "I1", symmetric=True)
		b = duplicate_key("T", "Institution", "I1", "Person", "P1", symmetric=True)
		assert a == b, "symmetric (A→B) and (B→A) must collapse to one edge"

	def test_symmetric_different_endpoints_distinct(self):
		a = duplicate_key("T", "Person", "P1", "Institution", "I1", symmetric=True)
		b = duplicate_key("T", "Person", "P1", "Place", "L1", symmetric=True)
		assert a != b

	def test_type_participates_in_identity(self):
		a = duplicate_key("T1", "Person", "P1", "Institution", "I1", symmetric=False)
		b = duplicate_key("T2", "Person", "P1", "Institution", "I1", symmetric=False)
		assert a != b


class TestPairKeys:
	def test_directed_pair_key_preserves_order(self):
		key = directed_pair_key("Person", "P1", "Institution", "I1")
		assert key == (("Person", "P1"), ("Institution", "I1"))

	def test_symmetric_pair_key_sorted(self):
		k1 = symmetric_pair_key("Person", "P1", "Institution", "I1")
		k2 = symmetric_pair_key("Institution", "I1", "Person", "P1")
		assert k1 == k2
		# Sorted by (doctype, name): Institution < Person alphabetically.
		assert k1[0] == ("Institution", "I1")
		assert k1[1] == ("Person", "P1")


if __name__ == "__main__":
	raise SystemExit(pytest.main([__file__, "-v"]))
