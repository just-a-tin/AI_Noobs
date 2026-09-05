"""Review text handling.

The filtering rule is deliberate: reviews with no text, or one or two words,
say nothing about whether the product matches its listing, and they are what
review farms mass-produce. The extension applies the filter; these tests pin
the contract the backend relies on and how the prompt presents it.
"""

import os

os.environ.setdefault("SENTINEL_SKIP_DOTENV", "1")
os.environ.setdefault("MOCK_AWS", "true")

from app.bedrock import _describe_listing
from app.schemas import AnalyzeRequest, CustomerReview, ReviewStats


def make_request(**overrides) -> AnalyzeRequest:
    base = {
        "itemId": "1",
        "title": "Hydrating Facial Serum 30ml",
        "price": 12.90,
        "specs": {"Volume": "30 ml"},
    }
    base.update(overrides)
    return AnalyzeRequest(**base)


def test_reviews_are_rendered_with_rating_and_photo_flag():
    prompt = _describe_listing(
        make_request(
            reviews=[
                CustomerReview(
                    text="Bottle arrived half empty and the label was different",
                    rating=2,
                    hasImages=True,
                )
            ],
            reviewStats=ReviewStats(totalFound=10, usable=1, discardedTooShort=9),
        ),
        [],
    )
    assert "CUSTOMER REVIEWS" in prompt
    assert "half empty" in prompt
    assert "2/5" in prompt
    assert "with photo" in prompt


def test_population_stats_reach_the_model():
    """"400 ratings, 6 with text" and "6 ratings, all with text" are very
    different signals, and the surviving reviews alone cannot distinguish
    them."""
    prompt = _describe_listing(
        make_request(
            reviews=[CustomerReview(text="Works well, skin feels smoother after use")],
            reviewStats=ReviewStats(
                totalFound=312,
                usable=1,
                discardedTooShort=305,
                duplicateGroups=4,
                averageRating=4.6,
            ),
        ),
        [],
    )
    assert "312" in prompt
    assert "305" in prompt
    assert "near-identical" in prompt
    assert "4.6" in prompt


def test_many_ratings_but_no_text_is_flagged_as_missing_evidence():
    prompt = _describe_listing(
        make_request(
            reviews=[],
            reviewStats=ReviewStats(totalFound=400, usable=0, discardedTooShort=400),
        ),
        [],
    )
    assert "400 found" in prompt
    # Absence of usable text must not read as an accusation.
    assert "missing" in prompt.lower()


def test_no_reviews_at_all_is_stated_plainly():
    prompt = _describe_listing(make_request(), [])
    assert "none could be retrieved" in prompt


def test_reviews_are_optional_in_the_request():
    """Older extension builds post no review fields; that must still validate."""
    req = make_request()
    assert req.reviews == []
    assert req.reviewStats is None


def test_prompt_tells_the_model_that_few_reviews_is_not_fraud():
    from app.bedrock import SYSTEM_PROMPT

    assert "REVIEW CREDIBILITY" in SYSTEM_PROMPT
    assert "NOT EVIDENCE OF FRAUD" in SYSTEM_PROMPT
