"""Pure contracts for the Phase 4 quality scoring (profile_presentation).

Deterministic scoring over the profile payload itself: completeness over
non-empty data fields, quality = 60/25/15 completeness/evidence/source,
confidence from the six ordered CONFIDENCE_CODES (recorded
authentication_level wins; otherwise derived from evidence rows).

Run with: pytest tests/test_quality_scores.py
"""

from __future__ import annotations

from siraj_research.profile_presentation import (
    CONFIDENCE_CODES,
    EVIDENCE_SATURATION_ROWS,
    QUALITY_WEIGHTS,
    compute_quality_scores,
)


def _field(fieldname, value):
    return {"fieldname": fieldname, "label": fieldname, "value": value}


def _profile(fields, evidence_rows=0, source_present=False, auth=None):
    entries = [_field(name, value) for name, value in fields]
    if source_present:
        entries.append(_field("primary_source", "SRC-0001"))
    if auth is not None:
        entries.append(_field("authentication_level", auth))
    children = {}
    if evidence_rows is not None:
        children["evidence"] = {
            "rows": [{} for _ in range(evidence_rows)],
            "total": evidence_rows,
        }
    return {"sections": [{"heading": "Person", "fields": entries}], "children": children}


def test_confidence_scale_is_the_six_ordered_codes():
    assert len(CONFIDENCE_CODES) == 6
    assert CONFIDENCE_CODES[0] == "unverified"
    assert CONFIDENCE_CODES[-1] == "institutionally_confirmed"


def test_completeness_counts_non_empty_fields():
    profile = _profile(
        [
            ("display_name", "Ada"),
            ("name_ar", "أدا"),
            ("website", ""),
            ("notes", None),
            ("latitude", 0),  # 0 is a filled value, not empty
        ]
    )
    scores = compute_quality_scores(profile)
    # 3 filled of 5 data fields → 60.
    assert scores["completeness_score"] == 60


def test_quality_fields_are_excluded_from_the_denominator():
    profile = _profile(
        [
            ("display_name", "Ada"),
            ("completeness_score", 0),
            ("quality_score", 0),
            ("confidence", ""),
        ]
    )
    scores = compute_quality_scores(profile)
    assert scores["completeness_score"] == 100


def test_quality_score_weights_and_saturation():
    # Full completeness (100), no evidence, no source → 60.
    base = compute_quality_scores(_profile([("display_name", "Ada")]))
    assert base["quality_score"] == 60

    # One evidence row → +25 * (1/5) → 60 + 5 = 65.
    one = compute_quality_scores(
        _profile([("display_name", "Ada")], evidence_rows=1)
    )
    assert one["quality_score"] == 65

    # Saturation: rows beyond 5 do not add more.
    full = compute_quality_scores(
        _profile([("display_name", "Ada")], evidence_rows=EVIDENCE_SATURATION_ROWS)
    )
    many = compute_quality_scores(
        _profile([("display_name", "Ada")], evidence_rows=99)
    )
    assert full["quality_score"] == many["quality_score"] == 85

    # Primary source adds exactly the source weight (15).
    sourced = compute_quality_scores(
        _profile([("display_name", "Ada")], source_present=True)
    )
    assert sourced["quality_score"] == 75
    assert sum(QUALITY_WEIGHTS.values()) == 1.0


def test_confidence_prefers_recorded_authentication_level():
    profile = _profile(
        [("display_name", "Ada")],
        evidence_rows=0,
        auth="institutionally_confirmed",
    )
    assert compute_quality_scores(profile)["confidence"] == "institutionally_confirmed"


def test_confidence_derives_from_evidence_rows():
    assert (
        compute_quality_scores(_profile([("display_name", "Ada")]))["confidence"]
        == "unverified"
    )
    assert (
        compute_quality_scores(_profile([("display_name", "Ada")], evidence_rows=1))[
            "confidence"
        ]
        == "single_source"
    )
    assert (
        compute_quality_scores(_profile([("display_name", "Ada")], evidence_rows=4))[
            "confidence"
        ]
        == "corroborated"
    )


def test_unknown_authentication_falls_back_to_derivation():
    profile = _profile(
        [("display_name", "Ada")], evidence_rows=2, auth="not_a_real_level"
    )
    assert compute_quality_scores(profile)["confidence"] == "corroborated"


def test_empty_profile_scores_zero():
    scores = compute_quality_scores({})
    assert scores["completeness_score"] == 0
    assert scores["quality_score"] == 0
    assert scores["confidence"] == "unverified"
    assert scores["evidence_rows"] == 0


def test_scoring_is_deterministic():
    profile = _profile(
        [("display_name", "Ada"), ("website", "https://example.org")],
        evidence_rows=3,
        source_present=True,
        auth="corroborated",
    )
    first = compute_quality_scores(profile)
    second = compute_quality_scores(profile)
    assert first == second
    assert first["confidence_scale"] == list(CONFIDENCE_CODES)


def test_normalised_payload_shape_is_accepted():
    # Already-normalised entries carry value dicts for links etc.
    profile = {
        "sections": [
            {
                "heading": "Identity",
                "fields": [
                    {"fieldname": "person_status", "value": {"type": "link", "name": "Active"}},
                    {"fieldname": "display_name", "value": "Ada"},
                ],
            }
        ],
        "children": {"evidence": {"rows": [{}, {}], "total": 2}},
    }
    scores = compute_quality_scores(profile)
    assert scores["completeness_score"] == 100
    assert scores["confidence"] == "corroborated"


def test_confidence_derived_flag_distinguishes_recorded_from_evidence():
    """confidence_derived powers the UI's (derived) badge vs recorded values."""
    recorded = compute_quality_scores(
        _profile([("display_name", "Ada")], evidence_rows=0, auth="institutionally_confirmed")
    )
    assert recorded["confidence"] == "institutionally_confirmed"
    assert recorded["confidence_derived"] is False

    derived_corroborated = compute_quality_scores(
        _profile([("display_name", "Ada")], evidence_rows=3)
    )
    assert derived_corroborated["confidence"] == "corroborated"
    assert derived_corroborated["confidence_derived"] is True

    derived_zero = compute_quality_scores(_profile([("display_name", "Ada")], evidence_rows=0))
    assert derived_zero["confidence"] == "unverified"
    assert derived_zero["confidence_derived"] is True


def test_quality_help_documents_the_shipped_weights():
    """The Quality section help text and QUALITY_WEIGHTS must agree."""
    from siraj_research.profile_presentation import QUALITY_HELP, SECTION_BLUEPRINTS

    quality = next(spec for spec in SECTION_BLUEPRINTS if spec["id"] == "quality")
    assert quality["help"] == QUALITY_HELP
    assert QUALITY_WEIGHTS == {"completeness": 0.6, "evidence": 0.25, "source": 0.15}
    for token in ("60%", "25%", "15%", "saturates at 5"):
        assert token in QUALITY_HELP, f"help text must document {token!r}"
    assert "(derived)" in QUALITY_HELP
