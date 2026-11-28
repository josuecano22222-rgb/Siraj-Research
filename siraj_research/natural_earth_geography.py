"""Natural Earth Vector country intelligence and choropleth classification.

This module is the analytical layer that turns SIRAJ's bundled Natural Earth
Vector pack (``public/natural_earth/110m``) into *data-driven* map features:
country lookup by coordinate, normalized country profiles (capital, population,
GDP, area, Arabic name), and choropleth class breaks.

It is deliberately framework-independent (no Frappe import) so the country
intelligence and classification logic can be unit-tested without a running
site, mirroring the purity of ``siraj_research.utils.map_search``. The Frappe
API layer (``siraj_research.api.natural_earth_vector``) wraps these helpers
with permission checks and site-data aggregation.

Point-in-polygon uses a manual ray-casting fallback so the module works even
when the optional Shapely dependency is absent; Shapely is used as a fast
path when available. Bbox pre-filtering and haversine reuse Siraj's existing
``utils.map_search`` helpers.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

from siraj_research.utils.map_search import haversine_m, point_in_bbox

DATA_DIR = Path(__file__).resolve().parent / "public" / "natural_earth" / "110m"
COUNTRY_LAYER = "ne_110m_admin_0_countries.geojson"
PLACES_LAYER = "ne_110m_populated_places.geojson"

EARTH_RADIUS_M = 6_371_008.8

CHOROPLETH_METHODS = ("quantile", "equal_interval")


class NaturalEarthGeographyError(ValueError):
    """Raised when the bundled geography pack is missing or corrupt."""


# ---------------------------------------------------------------------------
# Layer loading
# ---------------------------------------------------------------------------

@lru_cache(maxsize=8)
def _load_layer(filename: str) -> dict:
    path = DATA_DIR / filename
    if not path.is_file():
        raise NaturalEarthGeographyError(f"Bundled layer {filename} is missing.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NaturalEarthGeographyError(
            f"Bundled layer {filename} is not valid JSON."
        ) from exc
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise NaturalEarthGeographyError(
            f"Bundled layer {filename} is not a FeatureCollection."
        )
    features = payload.get("features")
    if not isinstance(features, list):
        raise NaturalEarthGeographyError(
            f"Bundled layer {filename} has an invalid feature list."
        )
    return payload


def _positions(value: Any):
    """Yield (lon, lat) pairs from a GeoJSON coordinate tree."""
    if (
        isinstance(value, list)
        and len(value) >= 2
        and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value[:2])
    ):
        yield value[0], value[1]
    elif isinstance(value, list):
        for child in value:
            yield from _positions(child)


def _bounds(geometry: dict) -> tuple[float, float, float, float]:
    """(min_lat, min_lon, max_lat, max_lon) — Siraj bbox convention."""
    lons, lats = [], []
    for lon, lat in _positions(geometry.get("coordinates", [])):
        lons.append(lon)
        lats.append(lat)
    return min(lats), min(lons), max(lats), max(lons)


# ---------------------------------------------------------------------------
# Point-in-polygon (Shapely optional)
# ---------------------------------------------------------------------------

def _on_segment(x: float, y: float, a: list, b: list, epsilon: float = 1e-10) -> bool:
    ax, ay = float(a[0]), float(a[1])
    bx, by = float(b[0]), float(b[1])
    cross = (x - ax) * (by - ay) - (y - ay) * (bx - ax)
    if abs(cross) > epsilon:
        return False
    return (
        min(ax, bx) - epsilon <= x <= max(ax, bx) + epsilon
        and min(ay, by) - epsilon <= y <= max(ay, by) + epsilon
    )


def _ring_contains(lon: float, lat: float, ring: list) -> bool:
    inside = False
    if len(ring) < 4:
        return False
    previous = ring[-1]
    for current in ring:
        if _on_segment(lon, lat, previous, current):
            return True
        x1, y1 = float(previous[0]), float(previous[1])
        x2, y2 = float(current[0]), float(current[1])
        if (y1 > lat) != (y2 > lat):
            crossing_lon = (x2 - x1) * (lat - y1) / (y2 - y1) + x1
            if lon < crossing_lon:
                inside = not inside
        previous = current
    return inside


def _polygon_contains(lon: float, lat: float, rings: list) -> bool:
    if not rings or not _ring_contains(lon, lat, rings[0]):
        return False
    return not any(_ring_contains(lon, lat, hole) for hole in rings[1:])


def _point_in_geometry(lon: float, lat: float, geometry: dict) -> bool:
    """Containment with boundary points considered inside; Shapely optional."""
    try:
        from siraj_research.geo_import import shapely  # type: ignore

        if shapely:
            from shapely.geometry import Point, shape

            def floats(value):
                if isinstance(value, dict):
                    return {key: floats(child) for key, child in value.items()}
                if isinstance(value, list):
                    return [floats(child) for child in value]
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    return float(value)
                return value

            return shape(floats(geometry)).covers(Point(lon, lat))
    except Exception:
        pass
    if geometry.get("type") == "Polygon":
        return _polygon_contains(lon, lat, geometry["coordinates"])
    return any(
        _polygon_contains(lon, lat, polygon)
        for polygon in geometry.get("coordinates", [])
    )


# ---------------------------------------------------------------------------
# Country intelligence
# ---------------------------------------------------------------------------

def iso_code(properties: dict) -> str:
    """Natural Earth uses '-99' for some ISO_A3 values (e.g. France, Norway).

    Prefer a valid alphabetic ISO_A3, then fall back to ADM0_A3 which carries
    the real three-letter code in those cases.
    """
    iso = properties.get("ISO_A3")
    if isinstance(iso, str) and len(iso) == 3 and iso.isalpha():
        return iso.upper()
    adm = properties.get("ADM0_A3")
    if isinstance(adm, str) and len(adm) == 3 and adm.isalpha():
        return adm.upper()
    return ""


def adm0_code(properties: dict) -> str:
    """The ``ADM0_A3`` code — valid for all 177 bundled countries.

    This is the canonical join key for the choropleth: unlike ``ISO_A3`` (which
    is ``-99`` for 5 countries including France), ``ADM0_A3`` is a real
    three-letter code for every feature, so per-country values always match a
    map feature when the JS layer joins on the ``ADM0_A3`` property.
    """
    adm = properties.get("ADM0_A3")
    if isinstance(adm, str) and len(adm) == 3 and adm.isalpha():
        return adm.upper()
    return iso_code(properties)


def _clean_label(value: Any) -> str:
    """Return a trimmed label, treating Natural Earth placeholders as empty."""
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text in ("", "-99", "null", "None") else text


def _clean_number(value: Any) -> float | int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value if math.isfinite(float(value)) else None
    return None


@lru_cache(maxsize=1)
def _country_index() -> tuple:
    """Precompute (properties, bbox, geometry) for every country."""
    index = []
    for feature in _load_layer(COUNTRY_LAYER)["features"]:
        geometry = feature.get("geometry")
        properties = feature.get("properties") or {}
        if not geometry:
            continue
        try:
            bounds = _bounds(geometry)
        except (TypeError, ValueError, IndexError):
            continue
        index.append((properties, bounds, geometry))
    return tuple(index)


def find_country(longitude: float, latitude: float) -> dict | None:
    """Return the country properties containing a WGS84 point (bbox pre-filtered)."""
    if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
        return None
    for properties, bbox, geometry in _country_index():
        if not point_in_bbox(latitude, longitude, bbox):
            continue
        try:
            if _point_in_geometry(longitude, latitude, geometry):
                return properties
        except (TypeError, ValueError, IndexError):
            continue
    return None


@lru_cache(maxsize=1)
def _capital_index() -> dict:
    """Map ISO_A3 -> capital city properties from the populated-places layer."""
    capitals: dict[str, dict] = {}
    try:
        features = _load_layer(PLACES_LAYER)["features"]
    except NaturalEarthGeographyError:
        return capitals
    for feature in features:
        properties = feature.get("properties") or {}
        if properties.get("FEATURECLA") != "Admin-0 capital":
            continue
        code = properties.get("ADM0_A3")
        if code and code not in capitals:
            capitals[code] = properties
    return capitals


def country_profile(
    code: str | None = None,
    longitude: float | None = None,
    latitude: float | None = None,
) -> dict | None:
    """Build a normalized country profile from the bundled attributes.

    Accepts either an ISO_A3 / boundary code or a coordinate pair. The capital
    is derived from the populated-places layer; the area is a spherical
    estimate (not a legal survey area).
    """
    properties = None
    if code:
        code = str(code).strip().upper()
        for candidate, _bbox, _geometry in _country_index():
            if iso_code(candidate) == code:
                properties = candidate
                break
    elif longitude is not None and latitude is not None:
        try:
            properties = find_country(float(longitude), float(latitude))
        except (TypeError, ValueError):
            properties = None
    if not properties:
        return None

    iso_a3 = iso_code(properties)
    capital = _capital_index().get(iso_a3)

    geometry = None
    for candidate, _bbox, geom in _country_index():
        if candidate is properties:
            geometry = geom
            break

    area_km2 = None
    if geometry is not None:
        try:
            area_km2 = round(geodesic_area_m2(geometry) / 1_000_000, 1)
        except (TypeError, ValueError, IndexError):
            area_km2 = None

    return {
        "code": iso_a3,
        "adm0_code": adm0_code(properties),
        "iso_a2": properties.get("ISO_A2") or "",
        "name": properties.get("NAME") or properties.get("ADMIN") or "",
        "name_ar": _clean_label(properties.get("NAME_AR")),
        "name_long": properties.get("NAME_LONG") or properties.get("FORMAL_EN") or "",
        "sovereign": properties.get("SOVEREIGNT") or "",
        "type": properties.get("TYPE") or "",
        "continent": properties.get("CONTINENT") or "",
        "region": properties.get("REGION_UN") or "",
        "subregion": properties.get("SUBREGION") or "",
        "economy": properties.get("ECONOMY") or "",
        "income_group": properties.get("INCOME_GRP") or "",
        "population_estimate": _clean_number(properties.get("POP_EST")),
        "population_year": _clean_number(properties.get("POP_YEAR")),
        "gdp_million_usd": _clean_number(
            properties.get("GDP_MD") or properties.get("GDP_MD_EST")
        ),
        "gdp_year": _clean_number(properties.get("GDP_YEAR")),
        "area_km2": area_km2,
        "label_longitude": _clean_number(properties.get("LABEL_X")),
        "label_latitude": _clean_number(properties.get("LABEL_Y")),
        "capital": (
            {
                "name": capital.get("NAME"),
                "name_ar": _clean_label(capital.get("NAME_AR")),
                "admin1": capital.get("ADM1NAME") or "",
                "latitude": _clean_number(capital.get("LATITUDE")),
                "longitude": _clean_number(capital.get("LONGITUDE")),
                "population_max": _clean_number(capital.get("POP_MAX")),
            }
            if capital
            else None
        ),
        "provenance": "natural_earth_bundle",
    }


# ---------------------------------------------------------------------------
# Geodesic area (spherical estimate)
# ---------------------------------------------------------------------------

def _ring_area_m2(ring: list) -> float:
    """Approximate spherical area of one closed ring (square meters)."""
    if not isinstance(ring, list) or len(ring) < 4:
        return 0.0
    total = 0.0
    for index in range(len(ring) - 1):
        lon1 = math.radians(float(ring[index][0]))
        lat1 = math.radians(float(ring[index][1]))
        lon2 = math.radians(float(ring[index + 1][0]))
        lat2 = math.radians(float(ring[index + 1][1]))
        total += (lon2 - lon1) * (2 + math.sin(lat1) + math.sin(lat2))
    return abs(total) * EARTH_RADIUS_M * EARTH_RADIUS_M / 2.0


def geodesic_area_m2(value: Any) -> float:
    """Approximate geodesic area of a Polygon/MultiPolygon in square meters."""
    geometry = value if isinstance(value, dict) else json.loads(value)
    if geometry.get("type") == "Polygon":
        polygons = [geometry["coordinates"]]
    else:
        polygons = geometry.get("coordinates", [])
    total = 0.0
    for polygon in polygons:
        if not isinstance(polygon, list) or not polygon:
            continue
        total += _ring_area_m2(polygon[0])
        for hole in polygon[1:]:
            total -= _ring_area_m2(hole)
    return max(0.0, total)


# ---------------------------------------------------------------------------
# Choropleth classification (pure, testable)
# ---------------------------------------------------------------------------

def classify(values: list, method: str = "quantile", classes: int = 5) -> dict:
    """Compute choropleth class breaks for a list of numeric values.

    Returns breakpoints (upper bound of each class), the observed min/max, and
    the empty-data flag. ``quantile`` distributes features evenly across
    classes; ``equal_interval`` splits the value range into equal-width bands.
    """
    if method not in CHOROPLETH_METHODS:
        raise NaturalEarthGeographyError(f"Unknown classification method {method!r}.")
    if isinstance(classes, bool) or not isinstance(classes, int) or not 2 <= classes <= 9:
        raise NaturalEarthGeographyError(
            "Choropleth classes must be an integer between 2 and 9."
        )
    numbers = sorted(
        float(value)
        for value in values
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))
    )
    if not numbers:
        return {
            "method": method, "classes": classes, "breaks": [],
            "min": None, "max": None, "empty": True,
        }
    low, high = numbers[0], numbers[-1]
    if method == "equal_interval" or high == low:
        if high == low:
            breaks = [high]
        else:
            width = (high - low) / classes
            breaks = [low + width * (index + 1) for index in range(classes)]
    else:  # quantile
        breaks = []
        for index in range(1, classes + 1):
            position = (len(numbers) - 1) * index / classes
            lower = math.floor(position)
            upper = min(lower + 1, len(numbers) - 1)
            fraction = position - lower
            breaks.append(numbers[lower] + (numbers[upper] - numbers[lower]) * fraction)
    # Ensure strictly increasing, finite breaks ending at the observed maximum.
    cleaned = []
    for value in breaks:
        if not cleaned or value > cleaned[-1]:
            cleaned.append(value)
    if cleaned:
        cleaned[-1] = high
    return {
        "method": method,
        "classes": len(cleaned) or classes,
        "breaks": cleaned,
        "min": low,
        "max": high,
        "empty": False,
    }


def class_index(value: float, breaks: list) -> int:
    """Return the zero-based choropleth class for a value given upper-bound breaks."""
    if not breaks:
        return 0
    for index, bound in enumerate(breaks):
        if value <= bound:
            return index
    return len(breaks) - 1


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres (reuses Siraj's haversine)."""
    return haversine_m(lat1, lon1, lat2, lon2)


# ---------------------------------------------------------------------------
# Site-data aggregation (pure, framework-independent)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=2)
def _country_names() -> dict[str, str]:
    """Map lower-cased NE country names/aliases -> ADM0_A3 join code."""
    mapping: dict[str, str] = {}
    for properties, _bbox, _geometry in _country_index():
        code = adm0_code(properties)
        for alias in {
            properties.get("NAME"),
            properties.get("NAME_LONG"),
            properties.get("ADMIN"),
        }:
            if isinstance(alias, str) and alias.strip():
                mapping.setdefault(alias.strip().lower(), code)
    return mapping


def resolve_site_country(
    latitude: Any = None,
    longitude: Any = None,
    country_name: Any = None,
) -> str:
    """Resolve a site record to an NE ``ADM0_A3`` join code.

    Prefers coordinate containment (robust to differing Country-doctype
    naming), then falls back to an English country-name match. Returns an
    empty string when no country can be determined. The returned code is the
    ``ADM0_A3`` value so it always matches a map feature (see ``adm0_code``).
    """
    if latitude is not None and longitude is not None:
        try:
            lat = float(latitude)
            lon = float(longitude)
        except (TypeError, ValueError):
            lat = lon = None
        if lat is not None and lon is not None:
            properties = find_country(lon, lat)
            if properties:
                return adm0_code(properties)
    if country_name:
        name = str(country_name).strip().lower()
        if name:
            return _country_names().get(name, "")
    return ""


def aggregate_site_data(
    records: list, agg: str = "count", value_key: str = "value"
) -> dict:
    """Aggregate site records onto NE countries (pure, testable).

    Each record is a dict with optional ``latitude``/``longitude``/
    ``country``/``country_name`` keys and, when ``agg != "count"``, a numeric
    ``value`` key (or a key given by ``value_key``). Counts records by default;
    ``sum``/``mean`` aggregate the supplied value. Records that cannot be
    resolved to a country are skipped (counted under ``"unmatched"``).

    Join strategy: coordinate containment first (most robust), then English
    country-name fallback.
    """
    if agg not in ("count", "sum", "mean"):
        raise NaturalEarthGeographyError(f"Unknown aggregation {agg!r}.")
    buckets: dict[str, list] = {}
    for record in records:
        code = resolve_site_country(
            record.get("latitude"),
            record.get("longitude"),
            record.get("country_name") or record.get("country"),
        )
        buckets.setdefault(code or "unmatched", []).append(record)

    result: dict[str, float | int] = {}
    for code, items in buckets.items():
        if code == "unmatched":
            result[code] = len(items)
            continue
        if agg == "count":
            result[code] = len(items)
        else:
            numbers = [
                float(record[value_key])
                for record in items
                if isinstance(record.get(value_key), (int, float))
                and not isinstance(record.get(value_key), bool)
                and math.isfinite(float(record[value_key]))
            ]
            if agg == "sum":
                result[code] = sum(numbers)
            else:  # mean
                result[code] = (sum(numbers) / len(numbers)) if numbers else 0.0
    return result


def choropleth_from_values(
    values_by_code: dict, method: str = "quantile", classes: int = 5
) -> dict:
    """Build a complete choropleth payload from an ISO_A3 -> value mapping.

    Returns the classification (breaks, min, max) plus a per-country class
    index so the JS map can color features without re-deriving the breaks.
    """
    entries = [
        (code, value)
        for code, value in values_by_code.items()
        if code and isinstance(value, (int, float)) and not isinstance(value, bool)
        and math.isfinite(float(value))
    ]
    classification = classify([value for _code, value in entries], method, classes)
    breaks = classification["breaks"]
    color_map = {
        code: class_index(float(value), breaks) for code, value in entries
    } if breaks else {}
    return {
        "method": classification["method"],
        "classes": classification["classes"],
        "breaks": breaks,
        "min": classification["min"],
        "max": classification["max"],
        "empty": classification["empty"],
        "valueByKey": {code: float(value) for code, value in entries},
        "classByKey": color_map,
        "matchedCount": len(entries),
    }
