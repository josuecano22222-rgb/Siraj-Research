"""Shared decimal-degree parsing for migration/audit and candidate map consumers.

WGS84 is a policy assumption, never inferred from a coordinate pair. Return
exact Decimal values; rendering as a binary float can lose display precision.
"""
from decimal import Decimal, InvalidOperation
import math
import re

DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫', '01234567890123456789.')
DECIMAL = re.compile(r'^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)$')


def parse_coordinate(value, *, max_length=None):
    """Return (blank|invalid|valid, Decimal or None), without bounds or rounding.

    Scientific notation is accepted only for actual numeric legacy values.
    Strings support Arabic/Persian digits and decimal separator. An optional
    text-length cap is used by candidate storage, not legacy map previews.
    """
    if value is None or isinstance(value, str) and not value.strip(): return 'blank', None
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)): return 'invalid', None
    if isinstance(value, float) and not math.isfinite(value): return 'invalid', None
    try:
        text = str(value).strip().translate(DIGITS)
        if (max_length is not None and len(text) > max_length) or (isinstance(value, str) and not DECIMAL.fullmatch(text)):
            return 'invalid', None
        number = Decimal(text)
        return ('valid', number) if number.is_finite() else ('invalid', None)
    except (InvalidOperation, ValueError, OverflowError):
        return 'invalid', None


def bounded_coordinate(value, limit, *, max_length=None):
    status, number = parse_coordinate(value, max_length=max_length)
    if status != 'valid': return status, None
    if number.copy_abs() > limit: return 'invalid', None
    return 'valid', number


def map_number(value, limit):
    """Approximate a valid coordinate for map rendering, never for storage."""
    status, number = bounded_coordinate(value, limit)
    if status != 'valid': return None
    try: return float(number)
    except (ValueError, OverflowError): return None
