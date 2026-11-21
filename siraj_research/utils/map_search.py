"""Pure query core for the advanced map search (no Frappe import).

Precision contract (docs/map-search.md):

* Decimal coordinate input is passed through **verbatim** as a normalized
  string — converting through float would silently round a value the
  researcher typed, so numbers are never routed through ``float`` here.
* DMS input is converted with exact rational arithmetic (``Fraction``);
  the result is emitted as a 28-significant-digit Decimal string plus the
  exact reduced fraction, so no information from the input is lost.
* Name matching folds Arabic orthography exactly like the client-side
  filter (``SirajFilters.normaliseText``): diacritics off, alef variants
  unified, ta marbuta → ha, ya → alef maqsura.
* Ranking is deterministic: pcode > exact > prefix > word-start >
  contains, ties broken by data (coarser region level first) then name.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, localcontext
from fractions import Fraction

# ---------------------------------------------------------------------------
# Arabic-aware name normalisation (mirrors public/js/siraj-map/siraj-filters.js)
# ---------------------------------------------------------------------------

_DIACRITICS = re.compile(r"[\u064B-\u065F\u0670]")
_ALEF_VARIANTS = str.maketrans({"أ": "ا", "إ": "ا", "ٱ": "ا", "آ": "ا"})

# SQL-side fold for the fast LIKE prefilter: REPLACE chains over the same
# rules, so "غزه" can still hit a stored "غزة" before the Python fallback.
SQL_FOLD = [
    ("ة", "ه"),
    ("ى", "ي"),
    ("أ", "ا"),
    ("إ", "ا"),
    ("ٱ", "ا"),
    ("آ", "ا"),
]


def normalise_name(value) -> str:
    """Fold a name for comparison. Never used for storage or display."""
    if value is None:
        return ""
    text = str(value).lower()
    text = _DIACRITICS.sub("", text)
    text = text.translate(_ALEF_VARIANTS)
    text = text.replace("ة", "ه").replace("ى", "ي")
    return re.sub(r"\s+", " ", text).strip()


def folded_like_clause(field: str, pattern: str) -> str:
    """A SQL fragment matching ``pattern`` against a fold-equivalent field."""
    expr = field
    for src, dst in SQL_FOLD:
        expr = f"REPLACE({expr}, '{src}', '{dst}')"
    return f"({field} LIKE {pattern} OR {expr} LIKE {pattern})"


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

SCORE_PCODE = 1000
SCORE_EXACT = 900
SCORE_PREFIX = 700
SCORE_WORD = 600
SCORE_CONTAINS = 400


def score_name(query_norm: str, *values) -> int:
    """Best score of any candidate value against the folded query."""
    if not query_norm:
        return 0
    best = 0
    for value in values:
        if not value:
            continue
        folded = normalise_name(value)
        if not folded:
            continue
        if folded == query_norm:
            score = SCORE_EXACT
        elif folded.startswith(query_norm):
            score = SCORE_PREFIX
        elif re.search(r"(?:^|\s)" + re.escape(query_norm), folded):
            score = SCORE_WORD
        elif query_norm in folded:
            score = SCORE_CONTAINS
        else:
            continue
        best = max(best, score)
    return best


def score_pcode(query: str, *values) -> int:
    """Exact pcode match (case-insensitive, whitespace-trimmed)."""
    needle = str(query or "").strip().lower()
    if not needle:
        return 0
    for value in values:
        if value and str(value).strip().lower() == needle:
            return SCORE_PCODE
    return 0


def rank_candidates(raw_query: str, rows: list[dict], label_keys: tuple,
                    pcode_keys: tuple = (), tie_break=None) -> list[dict]:
    """Return rows that match, best-first, each tagged with ``_score``.

    ``tie_break(row)`` supplies an ascending secondary key (e.g. region
    level); labels break remaining ties alphabetically (case-folded).
    """
    query_norm = normalise_name(raw_query)
    kept = []
    for row in rows:
        pcode_score = score_pcode(raw_query, *(row.get(k) for k in pcode_keys))
        name_score = score_name(query_norm, *(row.get(k) for k in label_keys))
        score = max(pcode_score, name_score)
        if score <= 0:
            continue
        tagged = dict(row)
        tagged["_score"] = score
        kept.append(tagged)
    kept.sort(
        key=lambda r: (
            -r["_score"],
            tie_break(r) if tie_break else 0,
            normalise_name(r.get(label_keys[0]) or r.get("name") or ""),
        )
    )
    return kept


# ---------------------------------------------------------------------------
# Coordinate query parsing (exact)
# ---------------------------------------------------------------------------

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫", "01234567890123456789.")
_NUMBER = re.compile(r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)$")
_DMS_NUMBER = re.compile(r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)$")

# 31d35'24.5"N style pairs, d/m/s letters, Arabic digits and prime marks.
_DMS_RE = re.compile(
    r"""^\s*
    (?P<lat_d>[+-]?[0-9]+(?:\.[0-9]+)?)\s*(?:°|d|degrees?)\s*
    (?:(?P<lat_m>[0-9]+(?:\.[0-9]+)?)\s*(?:'|′|m|min|minutes?)\s*)?
    (?:(?P<lat_s>[0-9]+(?:\.[0-9]+)?)\s*(?:''|″|"|s|sec|seconds?)\s*)?
    (?P<lat_h>[NSns])?
    [\s,;]+
    (?P<lon_d>[+-]?[0-9]+(?:\.[0-9]+)?)\s*(?:°|d|degrees?)\s*
    (?:(?P<lon_m>[0-9]+(?:\.[0-9]+)?)\s*(?:'|′|m|min|minutes?)\s*)?
    (?:(?P<lon_s>[0-9]+(?:\.[0-9]+)?)\s*(?:''|″|"|s|sec|seconds?)\s*)?
    (?P<lon_h>[EWew])?
    \s*$""",
    re.VERBOSE,
)

# "31.59N, 34.47E" — decimal pair with hemisphere suffixes.
_HEMI_PAIR_RE = re.compile(
    r"""^\s*
    (?P<lat>[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+))\s*(?P<lat_h>[NSns])?\s*[,;\s]\s*
    (?P<lon>[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+))\s*(?P<lon_h>[EWew])?
    \s*$""",
    re.VERBOSE,
)


def _translate_digits(text: str) -> str:
    return text.translate(_ARABIC_DIGITS)


def _decimal_string(text: str):
    """Exact Decimal from literal text, or None. No rounding, no float."""
    cleaned = _translate_digits(text.strip())
    if not _NUMBER.fullmatch(cleaned):
        return None
    try:
        number = Decimal(cleaned)
    except InvalidOperation:
        return None
    if not number.is_finite():
        return None
    # Normalize: keep the researcher's digits, drop only exponent form.
    if number == number.to_integral_value() and "e" not in cleaned.lower():
        return format(number, "f")
    return format(number, "f")


def _fraction_to_decimal_strings(value: Fraction) -> tuple[str, str]:
    """Exact fraction → (28-digit decimal string, reduced 'n/d' string)."""
    with localcontext() as ctx:
        ctx.prec = 28
        decimal_text = format(Decimal(value.numerator) / Decimal(value.denominator), "f")
    # Trim trailing zeros but keep at least one digit after the point.
    if "." in decimal_text:
        decimal_text = decimal_text.rstrip("0")
        if decimal_text.endswith("."):
            decimal_text += "0"
    return decimal_text, f"{value.numerator}/{value.denominator}"


def _dms_component(deg_text, min_text, s_text, hemi, *, is_latitude):
    """DMS → (exact Decimal-ish string, fraction string, error|None)."""
    try:
        degrees = Fraction(_translate_digits(deg_text))
    except (ValueError, ZeroDivisionError):
        return None, None, "invalid_number"
    minutes = Fraction(_translate_digits(min_text)) if min_text else Fraction(0)
    seconds = Fraction(_translate_digits(s_text)) if s_text else Fraction(0)
    if minutes >= 60 or seconds >= 60:
        return None, None, "dms_out_of_range"
    if degrees < 0 and (minutes or seconds):
        return None, None, "dms_sign_conflict"
    value = abs(degrees) + minutes / 60 + seconds / 3600
    hemi = (hemi or "").upper()
    if is_latitude:
        if hemi in ("S",):
            value = -value
        elif hemi and hemi not in ("N",):
            return None, None, "wrong_hemisphere"
        limit = 90
    else:
        if hemi in ("W",):
            value = -value
        elif hemi and hemi not in ("E",):
            return None, None, "wrong_hemisphere"
        limit = 180
    if abs(value) > limit:
        return None, None, "out_of_range"
    if degrees < 0 and hemi:
        return None, None, "dms_sign_conflict"
    decimal_text, fraction_text = _fraction_to_decimal_strings(value)
    return decimal_text, fraction_text, None


def _pair_error(lat_text: str, lon_text: str, lat_hemi: str, lon_hemi: str):
    """Validate a decimal pair; returns (error, swapped_suggestion)."""
    lat = _decimal_string(lat_text)
    lon = _decimal_string(lon_text)
    if lat is None or lon is None:
        return "invalid_number", False
    lat_h = (lat_hemi or "").upper()
    lon_h = (lon_hemi or "").upper()
    if lat_h in ("S",):
        if lat.startswith("-"):
            return "conflicting_hemisphere", False
        lat = "-" + lat.lstrip("+")
    if lat_h in ("N",) and lat.startswith("-"):
        return "conflicting_hemisphere", False
    if lon_h in ("W",):
        if lon.startswith("-"):
            return "conflicting_hemisphere", False
        lon = "-" + lon.lstrip("+")
    if lon_h in ("E",) and lon.startswith("-"):
        return "conflicting_hemisphere", False
    lat_n, lon_n = Decimal(lat), Decimal(lon)
    if abs(lat_n) <= 90 and abs(lon_n) <= 180:
        return None, False
    # GeoJSON order (lon, lat) pasted by accident is a common, recoverable
    # mistake: offer it as an explicit suggestion, never apply silently.
    if abs(lon_n) <= 90 and abs(lat_n) <= 180:
        return "out_of_range", True
    return "out_of_range", False


def parse_coordinate_query(text):
    """Classify a query string as coordinates.

    Returns ``None`` when the query is not coordinate-like, otherwise::

        {"format": "decimal"|"dms",
         "lat": "...", "lon": "...",          # exact decimal strings
         "lat_fraction": "...", "lon_fraction": "...",   # DMS only
         "input": <original>,
         "assumed_order": "lat,lon" | "lon,lat"}

    or ``{"error": "...", "suggestion": {...}|None, "input": ...}`` when the
    text looks like coordinates but is unusable.
    """
    if text is None:
        return None
    original = str(text).strip()
    if not original:
        return None
    translated = _translate_digits(original)

    # Arabic hemisphere letters (ش ج ق غ) — only meaningful next to degree
    # marks, which the DMS pattern requires, so folding them is safe.
    dms_text = (translated.replace("ش", "N").replace("س", "S")
                .replace("ج", "S").replace("ق", "E").replace("غ", "W"))
    dms = _DMS_RE.match(dms_text)
    if dms:
        lat, lat_f, err = _dms_component(
            dms.group("lat_d"), dms.group("lat_m"), dms.group("lat_s"),
            dms.group("lat_h"), is_latitude=True,
        )
        if err:
            return {"error": err, "input": original, "suggestion": None}
        lon, lon_f, err = _dms_component(
            dms.group("lon_d"), dms.group("lon_m"), dms.group("lon_s"),
            dms.group("lon_h"), is_latitude=False,
        )
        if err:
            return {"error": err, "input": original, "suggestion": None}
        return {
            "format": "dms",
            "lat": lat, "lon": lon,
            "lat_fraction": lat_f, "lon_fraction": lon_f,
            "input": original,
            "assumed_order": "lat,lon",
        }

    pair = _HEMI_PAIR_RE.match(translated)
    if pair:
        error, swapped = _pair_error(
            pair.group("lat"), pair.group("lon"),
            pair.group("lat_h"), pair.group("lon_h"),
        )
        if error:
            suggestion = None
            if swapped:
                suggestion = {
                    "format": "decimal",
                    "lat": _decimal_string(pair.group("lon")),
                    "lon": _decimal_string(pair.group("lat")),
                    "input": original,
                    "assumed_order": "lon,lat",
                }
            return {"error": error, "input": original, "suggestion": suggestion}
        lat = _decimal_string(pair.group("lat"))
        lon = _decimal_string(pair.group("lon"))
        lat_h = (pair.group("lat_h") or "").upper()
        lon_h = (pair.group("lon_h") or "").upper()
        if lat_h == "S" and not lat.startswith("-"):
            lat = "-" + lat.lstrip("+")
        if lon_h == "W" and not lon.startswith("-"):
            lon = "-" + lon.lstrip("+")
        return {
            "format": "decimal",
            "lat": lat, "lon": lon,
            "input": original,
            "assumed_order": "lat,lon",
        }

    # A bare number is ambiguous on purpose: never guess a single value.
    return None


def coordinate_looks_like(text) -> bool:
    """Cheap pre-check so the UI can short-circuit obviously textual queries."""
    if text is None:
        return False
    translated = _translate_digits(str(text))
    return bool(_DMS_RE.match(translated) or _HEMI_PAIR_RE.match(translated))


# ---------------------------------------------------------------------------
# Region levels
# ---------------------------------------------------------------------------

LEVEL_LABELS = {
    0: "Country",
    1: "Governorate",
    2: "District",
    3: "Municipality",
    4: "Village",
    5: "Community",
}

HIERARCHY_DOCTYPES = {
    0: "Country",
    1: "Governorate",
    2: "District",
    3: "Municipality",
    4: "Village",
    5: "Community",
}


def parse_levels(levels) -> list[int]:
    """Accept '1,2', [1, 2] or None → sorted unique valid levels."""
    if not levels:
        return []
    if isinstance(levels, str):
        parts = [p for p in levels.split(",") if p.strip()]
    else:
        parts = list(levels)
    valid = set()
    for part in parts:
        try:
            value = int(str(part).strip())
        except (TypeError, ValueError):
            continue
        if value in LEVEL_LABELS:
            valid.add(value)
    return sorted(valid)


def parse_types(types, allowed: tuple) -> list[str]:
    """Accept 'Person,Place', ['Person'] or None, restricted to ``allowed``."""
    if not types:
        return []
    if isinstance(types, str):
        parts = [p.strip() for p in types.split(",") if p.strip()]
    else:
        parts = [str(p).strip() for p in types]
    return [p for p in dict.fromkeys(parts) if p in allowed]
