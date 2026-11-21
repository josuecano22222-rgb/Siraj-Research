"""Translation coverage + quality gates (no bench required).

- every __(...)/_(...)/DocType/report source has an ar.csv row
- ar.csv satisfies the locale contract (Arabic, placeholder parity, no dupes)
- seed reference data carries real Arabic labels (no Latin transliterations,
  bidi control junk, mojibake, or in-country duplicates)
"""

from pathlib import Path

from siraj_research.setup.translation_audit import (
    audit_locale_csv,
    audit_reference_data,
    coverage_gaps,
)


def test_every_app_source_is_translated():
    gaps = coverage_gaps(Path("siraj_research"))
    assert not gaps, (
        "Sources missing from translations/ar.csv (translate them, then re-run): "
        + "; ".join(sorted(repr(g) for g in gaps))
    )


def test_locale_csv_contract():
    findings = audit_locale_csv(Path("siraj_research/translations/ar.csv"))
    assert not findings, f"ar.csv quality findings: {findings}"


def test_reference_data_arabic_labels():
    findings = audit_reference_data(Path("siraj_research/setup/reference_data"))
    assert not findings, f"reference data label_ar findings: {findings}"
