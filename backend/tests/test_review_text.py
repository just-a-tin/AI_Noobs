"""Template answers are not written feedback.

Shopee prompts reviewers with "Quality", "Value for money", "Best feature(s)"
and stores the tapped answers in the same field as free text. Everyone picks
from the same short list, so those answers pad the prompt without
distinguishing an honest listing from a fraudulent one.
"""

import pytest

from app.reviews import is_substantive, strip_review_template


def test_strips_template_lines_and_keeps_the_body():
    text = (
        "Quality: good\n"
        "Value for money: worth it\n"
        "Best feature(s): design\n"
        "Bottle arrived only half full and the label is different from the photos"
    )
    body = strip_review_template(text)
    assert body == (
        "Bottle arrived only half full and the label is different from the photos"
    )


def test_template_only_review_becomes_empty():
    """This is the case that matters: it looks like feedback and is not."""
    text = "Quality: good\nValue for money: worth it\nBest feature(s): design"
    assert strip_review_template(text) == ""
    assert not is_substantive(strip_review_template(text))


def test_full_width_colon_is_handled():
    """Shopee SG renders the template with a full-width colon for CJK input."""
    assert strip_review_template("Quality：good\nArrived broken in the box") == (
        "Arrived broken in the box"
    )


def test_known_label_with_a_long_answer_is_kept():
    """A buyer who actually wrote a paragraph under a template heading is
    giving real evidence; do not discard it."""
    text = (
        "Quality: honestly the plastic feels very cheap and one hinge snapped "
        "within the first week of normal use"
    )
    body = strip_review_template(text)
    assert "hinge snapped" in body


def test_unknown_short_label_is_treated_as_template():
    assert strip_review_template("Scent: nice\nSmells lovely and lasts all day") == (
        "Smells lovely and lasts all day"
    )


def test_prose_starting_with_a_word_and_colon_survives():
    """'Update:' and 'Note:' introduce real content, not template answers."""
    text = "Update: the seller refused to refund me after three weeks of chasing"
    assert strip_review_template(text) == text


def test_bare_tick_list_lines_are_dropped():
    text = "Quality\nValue for money\nThe item is much smaller than advertised"
    assert strip_review_template(text) == "The item is much smaller than advertised"


@pytest.mark.parametrize("text", ["", None, "   \n  \n "])
def test_empty_input_is_safe(text):
    assert strip_review_template(text) == ""


def test_substantive_threshold():
    assert not is_substantive("ok")
    assert not is_substantive("good product")
    assert is_substantive("arrived much smaller than the photos suggested")
