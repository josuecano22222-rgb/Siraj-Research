"""Pure regression tests for Country → Community parent/child cascading."""
import pytest

from siraj_research.geo_cascade import (
    ancestor_filters,
    cascade,
    chain_from_filters,
    chain_from_record,
    merge_chain,
    option_from_row,
    visible_chain,
)


def test_ancestor_filters_follow_the_six_level_chain():
    assert ancestor_filters("country", {"country": "IL"}) == {}
    assert ancestor_filters("governorate", {"country": "IL"}) == {"country": "IL"}
    assert ancestor_filters("community", {
        "country": "IL", "governorate": "G1", "district": "D1",
        "municipality": "M1", "village": "V1", "community": "Q1",
    }) == {
        "country": "IL", "governorate": "G1", "district": "D1",
        "municipality": "M1", "village": "V1",
    }


def test_option_from_row_uses_link_target_not_raw_label():
    row = option_from_row("community", {
        "name": "Com A", "label_en": "Community A", "label_ar": "مجتمع أ",
        "code": "Q1", "pcode": "Q1",
    })
    assert row["value"] == "Com A"       # safe Link target
    assert row["label"] == "Community A"
    assert row["label_ar"] == "مجتمع أ"
    assert row["doctype"] == "Community"
    country = option_from_row("country", {"name": "IL", "country_name": "Israel"})
    assert country["label"] == "Israel"


def test_chain_from_record_backfills_every_higher_level():
    record = {
        "name": "Com A", "country": "IL", "governorate": "Gov A",
        "district": "Dist A", "municipality": "Mun A", "village": "Vil A",
        "pcode": "Q1", "parent_pcode": "V1",
    }
    chain = chain_from_record("community", "Com A", record)
    assert chain["community"]["value"] == "Com A"
    assert chain["village"]["value"] == "Vil A"
    assert chain["municipality"]["value"] == "Mun A"
    assert chain["district"]["value"] == "Dist A"
    assert chain["governorate"]["value"] == "Gov A"
    assert chain["country"]["value"] == "IL"
    assert [row["field"] for row in visible_chain(chain)] == [
        "country", "governorate", "district", "municipality", "village", "community",
    ]


def test_missing_ancestors_stay_gaps_and_do_not_get_invented():
    chain = chain_from_record("district", "Dist A", {"name": "Dist A", "country": ""})
    assert chain["country"]["value"] == ""
    assert chain["governorate"]["value"] == ""
    assert [row["field"] for row in visible_chain(chain)] == ["district"]


def test_merge_and_filters_chains_prefer_specific_values():
    broad = chain_from_filters({"country": "IL"})
    specific = chain_from_record("village", "Vil A", {
        "name": "Vil A", "country": "PS", "governorate": "Gov B",
        "district": "Dist B", "municipality": "Mun B",
    })
    merged = merge_chain(broad, specific)
    assert merged["country"]["value"] == "PS"  # selected record wins
    assert merged["village"]["value"] == "Vil A"


@pytest.fixture(autouse=True)
def _bare_frappe_surface():
    """Make the whitelisted cascade callable without a bench site.

    On CI the real frappe package is absent and `frappe is None` inside
    geo_cascade, so nothing extra is needed. On a bench box (real frappe,
    no initialised site) the whitelist wrapper reads ``frappe.local.flags``
    and cascade touches has_permission/get_meta/get_all — stub exactly
    that surface and restore it afterwards.
    """
    try:
        import frappe
    except Exception:
        yield
        return
    _missing = object()
    old_flags = getattr(frappe.local, "flags", _missing)
    if old_flags is _missing:
        frappe.local.flags = frappe._dict()
    old = (frappe.has_permission, frappe.get_meta, frappe.get_all)
    frappe.has_permission = lambda *a, **k: True
    frappe.get_meta = lambda *a, **k: type(
        "Meta", (), {"has_field": staticmethod(lambda name: False),
                     "get_field": staticmethod(lambda name: None)})()
    frappe.get_all = lambda *a, **k: []
    try:
        yield
    finally:
        frappe.has_permission, frappe.get_meta, frappe.get_all = old
        if old_flags is _missing:
            try:
                del frappe.local.flags
            except Exception:
                pass
        else:
            frappe.local.flags = old_flags


def test_cascade_rejects_unknown_field_and_returns_shape_without_frappe():
    result = cascade("not_a_level", "x")
    assert result["error"].startswith("Unknown hierarchy field")
    result = cascade("governorate", None, country="IL")
    assert result["field"] == "governorate"
    assert result["filters"] == {"country": "IL"}
    assert result["source"] == "local-bench"
    assert result["options"] == []  # pure process has no local bench rows


def test_global_options_when_no_parent_selected():
    """With no country chosen, every governorate is a valid search target."""
    # Server-side: empty ancestor values → empty filters → all rows.
    assert ancestor_filters("governorate", {}) == {}
    assert ancestor_filters("district", {"country": "LB"}) == {"country": "LB"}
    # chain_from_filters still yields usable empty display rows for globals.
    chain = chain_from_filters({})
    assert chain["governorate"]["value"] == ""
    assert chain["country"]["value"] == ""
