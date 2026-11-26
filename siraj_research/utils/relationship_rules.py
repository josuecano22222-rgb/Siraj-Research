# Copyright (c) 2026, SIRAJ and contributors
# For license information, please see license.txt
"""Pure helpers for `Relationship` pair enforcement and duplicate normalization.

These functions contain **no** frappe imports so the consolidation rules can be
unit-tested in isolation (see ``tests/test_relationship_rules.py``) and reused
by the ``Relationship`` controller without duplicating the logic.

The rules implement ``docs/decisions/relationship-consolidation.md`` §3.2
(pair membership, symmetric swap-tolerance, self-links) and §8 (duplicate
normalization for directed and symmetric types).
"""

from __future__ import annotations


def symmetric_pair_key(
    subject_type: str, subject: str, object_type: str, object_name: str
) -> tuple[tuple[str, str], tuple[str, str]]:
    """Canonical, order-independent key for a symmetric edge.

    Endpoints are sorted by ``(doctype, name)`` so both orientations of the
    same unordered edge produce one key — ``(A→B)`` and ``(B→A)`` collapse to
    the same identity and only one row is kept (§8).
    """
    a = (subject_type, subject)
    b = (object_type, object_name)
    return tuple(sorted((a, b)))  # type: ignore[return-value]


def directed_pair_key(
    subject_type: str, subject: str, object_type: str, object_name: str
) -> tuple[tuple[str, str], tuple[str, str]]:
    """Ordered key for a directed edge (subject first, object second)."""
    return ((subject_type, subject), (object_type, object_name))


def duplicate_key(
    relationship_type: str,
    subject_type: str,
    subject: str,
    object_type: str,
    object_name: str,
    *,
    symmetric: bool,
) -> tuple:
    """Build the uniqueness key used to reject duplicate `Relationship` rows.

    For **directed** types the ordered
    ``(type, (subject_type, subject), (object_type, object))`` is the identity.
    For **symmetric** types the endpoints are normalized first, so ``(A→B)``
    and ``(B→A)`` are the same edge and only one row is kept (§8).
    """
    if symmetric:
        return (relationship_type, symmetric_pair_key(subject_type, subject, object_type, object_name))
    return (
        relationship_type,
        directed_pair_key(subject_type, subject, object_type, object_name),
    )


def pair_allowed(
    allowed_pairs, subject_type: str, object_type: str, *, symmetric: bool
) -> bool:
    """Return whether ``(subject_type, object_type)`` is an allowed pair.

    ``allowed_pairs`` is any iterable of ``(subject_doctype, object_doctype)``
    tuples (the rows of the ``Relationship Type Allowed Pair`` child table).

    - **Directed** types require the exact ordered row ``(subject, object)``.
    - **Symmetric** types accept the row in either orientation: ``(A, B)`` is
      allowed if ``(A, B)`` *or* ``(B, A)`` is present (§3.2).
    """
    pairs = set(allowed_pairs)
    if (subject_type, object_type) in pairs:
        return True
    if symmetric and (object_type, subject_type) in pairs:
        return True
    return False
