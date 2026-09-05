"""Parse the physical size a listing *claims*, from its specification table.

This is done deterministically rather than being left to the model, so the
claimed size is ground truth the model is asked to check against — not another
thing it could get wrong. Sellers write dimensions a dozen different ways
("12x8x3 cm", "150mm", '6"'), so the parsing is deliberately forgiving.
"""

from __future__ import annotations

import re

# Longest edge only: for scam detection, "how big is this thing" is the
# question, and a single number is far more robust to parse than an ordered
# triple that sellers scramble anyway.
_TO_CM = {
    "cm": 1.0,
    "centimetre": 1.0,
    "centimeter": 1.0,
    "mm": 0.1,
    "millimetre": 0.1,
    "millimeter": 0.1,
    "m": 100.0,
    "metre": 100.0,
    "meter": 100.0,
    "in": 2.54,
    "inch": 2.54,
    "inches": 2.54,
    '"': 2.54,
}

# Keys worth reading. Weight and capacity are not sizes. Plurals matter:
# "Dimensions" is the single most common spelling on Shopee.
_SIZE_KEY = re.compile(
    r"\b(dimensions?|sizes?|length|width|height|depth|measurements?|diameter)\b",
    re.I,
)

_NUMBER = r"\d+(?:[.,]\d+)?"

# Alternation order is load-bearing: the regex engine takes the first branch
# that matches, so "m" listed before "millimeter" would silently read
# "150 millimeters" as 150 metres. Longest spellings first, always.
_UNIT = (
    r"(?:centimet(?:re|er)s?|millimet(?:re|er)s?|met(?:re|er)s?"
    r"|inches|inch|cm|mm|in|m|\")"
)

# "12 x 8 x 3 cm", "12*8cm" — unit usually appears once, at the end.
_SERIES = re.compile(
    rf"({_NUMBER})\s*[x×*]\s*({_NUMBER})(?:\s*[x×*]\s*({_NUMBER}))?\s*({_UNIT})?",
    re.I,
)
_SINGLE = re.compile(rf"({_NUMBER})\s*({_UNIT})", re.I)


def _to_float(raw: str) -> float | None:
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return None


def _unit_factor(raw: str | None, default: float | None = None) -> float | None:
    if not raw:
        return default
    key = raw.strip().lower()
    if key in _TO_CM:
        return _TO_CM[key]
    return _TO_CM.get(key.rstrip("s"))


def parse_longest_cm(text: str) -> float | None:
    """Longest edge in centimetres found in a free-text dimension string."""
    if not text:
        return None

    best: float | None = None

    for match in _SERIES.finditer(text):
        factor = _unit_factor(match.group(4), default=1.0)  # bare numbers → cm
        if factor is None:
            continue
        for group in match.groups()[:3]:
            if not group:
                continue
            value = _to_float(group)
            if value is not None and value > 0:
                best = max(best or 0.0, value * factor)

    if best is not None:
        return round(best, 2)

    for match in _SINGLE.finditer(text):
        factor = _unit_factor(match.group(2))
        value = _to_float(match.group(1))
        if factor is None or value is None or value <= 0:
            continue
        best = max(best or 0.0, value * factor)

    return round(best, 2) if best is not None else None


def listed_longest_cm(specs: dict[str, str]) -> float | None:
    """Largest dimension the listing claims, across all size-ish spec fields."""
    best: float | None = None
    for key, value in specs.items():
        if not _SIZE_KEY.search(key):
            continue
        found = parse_longest_cm(str(value))
        if found is not None:
            best = max(best or 0.0, found)
    return best
