"""Provider parsing, caching and fallback decisions (no network, no bench)."""

import pytest

from siraj_research import geo_online as go


@pytest.fixture(autouse=True)
def _clean_cache(monkeypatch):
    go._MEMORY_CACHE.clear()
    go._LAST_CALL["ts"] = 0.0
    monkeypatch.setattr(go, "_settings", lambda: {
        "enabled": True,
        "provider": go.PROVIDERS[0],
        "api_key": "",
        "user_agent": "SirajResearch test",
        "rate_limit_per_min": 6000,
        "min_interval_s": 0,
        "cache_days": 1,
        "fallback_when": "Missing any level",
    })


def test_nominatim_parsing_does_not_overwrite_country_code():
    payload = {"address": {
        "country": "Iraq", "country_code": "iq", "state": "Baghdad",
        "county": "Baghdad", "city": "Baghdad", "suburb": "Karrada",
    }}
    parsed = go.parse_nominatim(payload)
    assert parsed["admin_chain"]["country"]["pcode"] == "IQ"
    assert parsed["admin_chain"]["governorate"]["name_en"] == "Baghdad"
    assert parsed["admin_chain"]["community"]["name_en"] == "Karrada"


def test_esri_and_photon_parsers():
    esri = go.parse_esri({"address": {
        "CountryCode": "SY", "Region": "Damascus", "Subregion": "Damascus",
        "City": "Damascus", "Neighborhood": "Al-Midan",
    }})
    assert esri["admin_chain"]["country"]["name_en"] == "SY"
    assert esri["admin_chain"]["district"]["name_en"] == "Damascus"
    photon = go.parse_photon({"features": [{"properties": {
        "country": "Lebanon", "countrycode": "lb", "state": "Beirut",
        "city": "Beirut", "name": "Mar Mikhael",
    }}]})
    assert photon["admin_chain"]["country"]["pcode"] == "LB"
    assert photon["nearest_place"]["name_en"] == "Mar Mikhael"


def test_google_address_components_mapping():
    payload = {"results": [{"name": "Damascus", "address_components": [
        {"long_name": "Syria", "short_name": "SY", "types": ["country"]},
        {"long_name": "Damascus Governorate", "short_name": "DI",
         "types": ["administrative_area_level_1"]},
        {"long_name": "Damascus", "short_name": "DM", "types": ["locality"]},
        {"long_name": "Al-Midan", "short_name": "MD",
         "types": ["neighborhood"]},
    ]}]}
    parsed = go.parse_google(payload)
    assert parsed["admin_chain"]["country"]["pcode"] == "SY"
    assert parsed["admin_chain"]["municipality"]["name_en"] == "Damascus"
    assert parsed["admin_chain"]["community"]["name_en"] == "Al-Midan"


def test_lookup_is_cached_and_never_calls_transport_twice():
    calls = []

    def fake_get(url, headers=None):
        calls.append(url)
        return {"address": {"country": "Iraq", "country_code": "iq",
                            "state": "Baghdad", "city": "Baghdad"}}

    first = go.lookup(33.5, 36.2, http_get=fake_get)
    second = go.lookup(33.5, 36.2, http_get=fake_get)
    assert first["cached"] is False
    assert second["cached"] is True
    assert len(calls) == 1
    assert second["admin_chain"]["governorate"]["source"] == "nominatim"


def test_lookup_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(go, "_settings", lambda: {
        "enabled": False, "provider": go.PROVIDERS[0], "api_key": "",
        "user_agent": "x", "rate_limit_per_min": 60, "min_interval_s": 1,
        "cache_days": 1, "fallback_when": "Always",
    })
    result = go.lookup(1, 2)
    assert result["skipped"] == "disabled"
    assert result["admin_chain"] == {}


def test_should_fallback_decision_matrix():
    cfg = go._settings()
    assert go.should_fallback({"admin_chain": {}}, cfg) is True
    assert go.should_fallback({"admin_chain": {
        "country": {"name_en": "Iraq"}, "governorate": {"name_en": "x"}}}, cfg) is True
    shallow = {"admin_chain": {"country": {"name_en": "Iraq"}}}
    assert go.should_fallback(shallow, cfg) is False
    cfg["fallback_when"] = "Always"
    assert go.should_fallback(shallow, cfg) is True
