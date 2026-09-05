"""Reduce a customer review to what the buyer actually wrote.

Shopee prompts reviewers with a template — "Quality", "Value for money",
"Best feature(s)" — and the tapped answers are stored in the same comment
field as free text. Those answers are near-content-free: everyone picks from
the same short list, so they pad the prompt without distinguishing an honest
listing from a fraudulent one. Worse, a review consisting only of template
answers looks like written feedback while carrying none.

So template lines are stripped, and the length filter is applied to what
remains. A review whose body is empty after stripping is discarded.
"""

from __future__ import annotations

import re
import unicodedata

#: Labels Shopee (and Lazada) use in their review templates.
_TEMPLATE_LABELS = {
    "quality",
    "product quality",
    "value",
    "value for money",
    "worth it",
    "best feature",
    "best features",
    "feature",
    "features",
    "effectiveness",
    "texture",
    "scent",
    "smell",
    "colour",
    "color",
    "size",
    "fit",
    "packaging",
    "delivery",
    "shipping",
    "shipping speed",
    "seller service",
    "service",
    "performance",
    "durability",
    "material",
    "comfort",
    "skin type",
    "suitable for",
    "would recommend",
    "recommend",
    "taste",
    "freshness",
    "brightness",
    "sound quality",
    "battery life",
    "ease of use",
}

# "Label: answer" — full-width colon included, since Shopee SG serves users
# typing in Chinese and the template renders with a full-width colon there.
_LABELLED_LINE = re.compile(r"^\s*([^:：]{2,32})[:：]\s*(.*)$")

# Reviewers sometimes get a bare tick-list with no colons at all.
_BARE_TEMPLATE_LINE = re.compile(
    r"^\s*(?:%s)\s*$" % "|".join(re.escape(x) for x in sorted(_TEMPLATE_LABELS)),
    re.I,
)


def _is_template_line(label: str, answer: str) -> bool:
    """Is this a tapped template answer rather than something written?"""
    normalised = unicodedata.normalize("NFKC", label).strip().lower()
    normalised = re.sub(r"[^a-z ]", "", normalised).strip()

    if normalised in _TEMPLATE_LABELS:
        # A known label with a genuinely long answer is still prose the buyer
        # wrote, so keep it rather than discarding real evidence.
        return len(answer.split()) <= 12

    # Unknown label: only treat it as a template when both halves are terse,
    # so "Update: the seller refused to refund me after three weeks" survives.
    return len(normalised.split()) <= 3 and 0 < len(answer.split()) <= 4


def strip_review_template(text: str) -> str:
    """Return only the free-text body of a review."""
    if not text:
        return ""

    kept: list[str] = []
    for line in re.split(r"[\r\n]+", text):
        stripped = line.strip()
        if not stripped:
            continue
        if _BARE_TEMPLATE_LINE.match(stripped):
            continue

        match = _LABELLED_LINE.match(stripped)
        if match and _is_template_line(match.group(1), match.group(2)):
            continue

        kept.append(stripped)

    return re.sub(r"\s+", " ", " ".join(kept)).strip()


def is_substantive(body: str, min_words: int = 5, min_chars: int = 20) -> bool:
    """Enough written content to say anything about the product?"""
    return len(body) >= min_chars and len(body.split()) >= min_words
