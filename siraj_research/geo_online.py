"""External reverse-geocoding fallback for the administrative hierarchy.

Local polygon/gazetteer resolution is always attempted first
(:mod:`siraj_research.api.geo_resolve`). This module is used only when the
local chain is incomplete or an operator explicitly asks for a refresh. It
normalises four public/paid providers into the SIRAJ chain contract and
applies caching + throttling so a public service is never hammered.

Pluggable transport
-------------------
``lookup(lat, lon, http_get=...)`` accepts an injected callable for tests::

    http_get(url, headers=None) -> decoded JSON dict

In production ``requests.get(...).json()`` is used. No network call happens
unless ``Geo Settings.online_geocoder_enabled`` is checked.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

try:  # pragma: no cover - bench only
    import frappe
except Exception:  # pragma: no cover - pure-Python tests
    frappe = None  # type: ignore[assignment]

_MEMORY_CACHE: dict[str, tuple[float, Any]] = {}
_LAST_CALL = {"ts": 0.0}


PROVIDERS = ("Nominatim (OpenStreetMap)", "Esri World Geocoding",
             "Photon (Komoot)", "Google Geocoding")

# Which address keys each provider uses for the SIRAJ levels. Earlier entries
# win; this keeps a well-known "city" ahead of a generic "county".
CHAIN_KEYS = {
	"country": ("country", "country_code", "CountryCode"),
	"governorate": ("state", "region", "Region", "province", " Governorate"),
	"district": ("county", "district", "Subregion", "County", "District"),
	"municipality": ("city", "town", "municipality", "City", "Town", "Municipality"),
	"village": ("village", "hamlet", "Village", "locality"),
	"community": ("neighbourhood", "neighbourhood_name", "suburb", "quarter",
	              "Neighborhood", "Neighbourhood", "Suburb", "Quarter"),
}


def _settings() -> dict:
	defaults = {
		"enabled": False,
		"provider": PROVIDERS[0],
		"api_key": "",
		"user_agent": "SirajResearch/1.0 (administrative registry; contact your site administrator)",
		"rate_limit_per_min": 30,
		"min_interval_s": 1,
		"cache_days": 30,
		"fallback_when": "Missing any level",
	}
	if frappe is None:
		return defaults
	try:
		s = frappe.get_single("Geo Settings")
	except Exception:
		return defaults
	return {
		"enabled": bool(s.online_geocoder_enabled),
		"provider": s.online_provider or defaults["provider"],
		"api_key": s.online_api_key or "",
		"user_agent": s.online_user_agent or defaults["user_agent"],
		"rate_limit_per_min": int(s.online_rate_limit_per_min or defaults["rate_limit_per_min"]),
		"min_interval_s": int(s.online_min_interval_s or defaults["min_interval_s"]),
		"cache_days": int(s.online_cache_days or defaults["cache_days"]),
		"fallback_when": s.online_fallback_when or defaults["fallback_when"],
	}


def _cache_key(lat: float, lon: float, provider: str) -> str:
	return f"siraj:geo:online:{provider}:{round(lat, 5)}:{round(lon, 5)}"


def _cache_get(key: str) -> dict | None:
	if frappe is not None:
		try:
			raw = frappe.cache().get_value(key)
			if raw:
				return json.loads(raw)
		except Exception:
			pass
	entry = _MEMORY_CACHE.get(key)
	if entry and entry[0] > time.time():
		return entry[1]
	return None


def _cache_set(key: str, value: dict, days: int) -> None:
	if frappe is not None:
		try:
			frappe.cache().set_value(key, json.dumps(value), expires_in_sec=max(1, days) * 86400)
			return
		except Exception:
			pass
	_MEMORY_CACHE[key] = (time.time() + max(1, days) * 86400, value)
	# Keep the in-process cache bounded in bench-free test runs.
	if len(_MEMORY_CACHE) > 1024:
		oldest = min(_MEMORY_CACHE, key=lambda k: _MEMORY_CACHE[k][0])
		_MEMORY_CACHE_POP(oldest)


def _MEMORY_CACHE_POP(key: str) -> None:
	_MEMORY_CACHE.pop(key, None)


def _throttle(min_interval_s: int, rate_limit_per_min: int) -> None:
	"""Best-effort local throttle shared by all requests in the process."""
	wait = 60.0 / max(1, rate_limit_per_min)
	wait = max(wait, float(max(0, min_interval_s)))
	delta = wait - (time.time() - _LAST_CALL["ts"])
	if 0 < delta < wait:
		time.sleep(delta)
	_LAST_CALL["ts"] = time.time()


def _default_get(url: str, headers: dict | None = None) -> dict:
	import requests  # bench dependency; injected in tests
	response = requests.get(url, headers=headers or {}, timeout=12)
	response.raise_for_status()
	return response.json()


def _entry(value: Any, source: str, confidence: str = "medium") -> dict | None:
	if isinstance(value, dict):
		name = value.get("name") or value.get("label_en") or value.get("name_en")
		code = value.get("code") or value.get("pcode") or value.get("osm_id")
		label_ar = value.get("name_ar")
	else:
		name, code, label_ar = value, None, None
	if name in (None, ""):
		return None
	entry = {
		"name_en": str(name),
		"name_ar": str(label_ar) if label_ar else None,
		"pcode": str(code) if code else None,
		"source": source,
		"confidence": confidence,
	}
	return entry


def _from_keyed(address: dict, source: str) -> dict:
	chain: dict[str, dict] = {}
	lower = {str(k).lower(): v for k, v in (address or {}).items()}
	for field, keys in CHAIN_KEYS.items():
		for key in keys:
			value = lower.get(key.lower().strip())
			if value:
				entry = _entry(value, source, "medium")
				if entry:
					chain[field] = entry
					break
	return chain


def parse_nominatim(payload: dict) -> dict:
	address = payload.get("address") or {}
	chain = _from_keyed(address, "nominatim")
	code = address.get("country_code")
	if code and chain.get("country"):
		chain["country"]["pcode"] = str(code).upper()
	place = _entry(payload.get("name") or address.get("name"), "nominatim", "medium")
	return {
		"provider": PROVIDERS[0],
		"admin_chain": chain,
		"nearest_place": place,
		"raw": payload,
	}


def parse_esri(payload: dict) -> dict:
	address = ((payload or {}).get("address") or {})
	chain = _from_keyed(address, "esri")
	if not chain.get("country") and address.get("Country"):
		chain["country"] = _entry(address["Country"], "esri") or {}
	place = _entry(address.get("Address") or address.get("PlaceName"), "esri", "medium")
	return {"provider": PROVIDERS[1], "admin_chain": chain,
	        "nearest_place": place, "raw": payload}


def parse_photon(payload: dict) -> dict:
	features = (payload or {}).get("features") or []
	if not features:
		return {"provider": PROVIDERS[2], "admin_chain": {}, "nearest_place": None, "raw": payload}
	props = features[0].get("properties") or {}
	chain = _from_keyed(props, "photon")
	code = props.get("countrycode")
	if code and chain.get("country"):
		chain["country"]["pcode"] = str(code).upper()
	place = _entry(props.get("name"), "photon", "medium")
	return {"provider": PROVIDERS[2], "admin_chain": chain,
	        "nearest_place": place, "raw": payload}


def parse_google(payload: dict) -> dict:
	results = (payload or {}).get("results") or []
	if not results:
		return {"provider": PROVIDERS[3], "admin_chain": {}, "nearest_place": None, "raw": payload}
	types_to_level = {
		"country": "country",
		"administrative_area_level_1": "governorate",
		"administrative_area_level_2": "district",
		"administrative_area_level_3": "municipality",
		"locality": "municipality",
		"postal_town": "municipality",
		"administrative_area_level_4": "village",
		"sublocality": "community",
		"neighborhood": "community",
	}
	chain: dict[str, dict] = {}
	for component in results[0].get("address_components") or []:
		types = component.get("types") or []
		short_name = component.get("short_name")
		long_name = component.get("long_name")
		for type_name in types:
			if type_name not in types_to_level:
				continue
			field = types_to_level[type_name]
			if field in chain:
				continue
			entry = _entry(long_name, "google", "medium")
			if entry:
				entry["pcode"] = short_name if type_name == "country" else entry["pcode"]
				chain[field] = entry
			break
	place = _entry(results[0].get("name"), "google", "medium")
	return {"provider": PROVIDERS[3], "admin_chain": chain,
	        "nearest_place": place, "raw": payload}


PARSERS = {
	PROVIDERS[0]: (parse_nominatim, "https://nominatim.openstreetmap.org/reverse"),
	PROVIDERS[1]: (parse_esri, "https://geocode-api.arcgis.com/arcgis/rest/services/World/GeocodeServer/reverseGeocode"),
	PROVIDERS[2]: (parse_photon, "https://photon.komoot.io/reverse"),
	PROVIDERS[3]: (parse_google, "https://maps.googleapis.com/maps/api/geocode/json"),
}


def _url_and_headers(provider: str, lat: float, lon: float, cfg: dict) -> tuple[str, dict]:
	base = PARSERS[provider][1]
	if provider == PROVIDERS[0]:
		return (
			f"{base}?format=jsonv2&lat={lat}&lon={lon}&zoom=18&addressdetails=1",
			{"User-Agent": cfg["user_agent"], "Accept-Language": "en"},
		)
	if provider == PROVIDERS[1]:
		token = f"&token={cfg['api_key']}" if cfg["api_key"] else ""
		return (f"{base}?location={lon},{lat}&f=json{token}&outFields=*", {"User-Agent": cfg["user_agent"]})
	if provider == PROVIDERS[2]:
		return (f"{base}?lat={lat}&lon={lon}&limit=1", {"User-Agent": cfg["user_agent"]})
	if cfg["api_key"]:
		return (f"{base}?latlng={lat},{lon}&key={cfg['api_key']}&language=en", {"User-Agent": cfg["user_agent"]})
	raise ValueError("Google Geocoding requires an API key in Geo Settings")


def lookup(lat: float, lon: float, *, provider: str | None = None,
           http_get: Callable[[str, dict | None], dict] | None = None) -> dict:
	"""Resolve a coordinate through the configured external provider.

	Returns an empty chain (with ``skipped``) when the fallback is disabled,
	cached/throttled when enabled, and a normalised chain otherwise. Network
	errors are swallowed so a failed external call never breaks a local
	resolve; the ``error`` key explains what happened.
	"""
	cfg = _settings()
	if not cfg["enabled"]:
		return {"provider": None, "admin_chain": {}, "nearest_place": None,
		        "skipped": "disabled", "raw": None}
	provider = provider or cfg["provider"]
	if provider not in PARSERS:
		return {"provider": provider, "admin_chain": {}, "nearest_place": None,
		        "error": "unsupported provider", "raw": None}
	key = _cache_key(lat, lon, provider)
	cached = _cache_get(key)
	if cached is not None:
		return {**cached, "cached": True}
	get = http_get or _default_get
	try:
		_throttle(cfg["min_interval_s"], cfg["rate_limit_per_min"])
		url, headers = _url_and_headers(provider, lat, lon, cfg)
		payload = get(url, headers)
		result = PARSERS[provider][0](payload)
		result["cached"] = False
		result["lat"] = lat
		result["lon"] = lon
		_cache_set(key, result, cfg["cache_days"])
		return result
	except Exception as exc:  # network / parse / provider errors are non-fatal
		return {"provider": provider, "admin_chain": {}, "nearest_place": None,
		        "error": f"{type(exc).__name__}: {exc}", "raw": None}


def should_fallback(resolution: dict, cfg: dict | None = None) -> bool:
	"""Decide whether the online fallback is worth a request."""
	cfg = cfg or _settings()
	if not cfg["enabled"]:
		return False
	mode = str(cfg["fallback_when"] or "Missing any level")
	if mode == "Always":
		return True
	chain = resolution.get("admin_chain") or {}
	if not chain.get("country"):
		return True
	if mode == "Missing country":
		return False
	# Levels with no polygon are common in small countries; only trigger when
	# a *lower* level is missing beneath a known governorate, or the local
	# result reported no land at all.
	return bool(chain.get("governorate")) and (
		not chain.get("district") or not chain.get("municipality")
		or resolution.get("on_land") is False
	)
