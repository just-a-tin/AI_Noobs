import time

import pytest

from app.cache import InMemoryCache
from app.schemas import (
    AnalysisResult,
    AnalyzeRequest,
    ImageAnalysis,
    ReferenceAgreement,
    ReviewAnalysis,
    RiskLevel,
    ScaleAnalysis,
    ScaleConfidence,
    SceneReference,
    SubScores,
)


def make_request(**overrides) -> AnalyzeRequest:
    base = {
        "platform": "shopee",
        "itemId": "123456789",
        "shopId": "987654",
        "title": "Wireless Earbuds Pro",
        "price": 49.90,
        "specs": {"weight": "45g", "material": "ABS"},
        "imageUrls": [],
        "reviewImageUrls": [],
    }
    base.update(overrides)
    return AnalyzeRequest(**base)


def make_result(score: int = 80) -> AnalysisResult:
    return AnalysisResult(
        overallTrustScore=score,
        subScores=SubScores(
            visualIntegrity=score,
            specConsistency=score,
            priceSanity=score,
            scaleFidelity=score,
            reviewCredibility=score,
        ),
        scaleAnalysis=ScaleAnalysis(
            identifiedProduct="wireless earbuds",
            scaleConfidence=ScaleConfidence.HIGH,
            sceneReferences=[
                SceneReference(
                    objectName="adult hand", assumedRealCm=18.0, impliedProductCm=6.1
                )
            ],
            referenceAgreement=ReferenceAgreement.SINGLE,
            expectedLongestCm=6.0,
            apparentLongestCm=6.1,
            mismatchDetected=False,
            explanation="Matches expected size.",
        ),
        reviewAnalysis=ReviewAnalysis(
            usableReviewCount=3,
            complaintThemes=[],
            contradictsListing=False,
            suspectedFakeReviews=False,
            explanation="Reviews read as genuine.",
        ),
        findings=["ok"],
        imageAnalysis=ImageAnalysis(
            isAiGenerated=False, visualDiscrepancyDetected=False, explanation="fine"
        ),
        specDiscrepancies=[],
        riskLevel=RiskLevel.LOW,
    )


def test_miss_then_hit():
    cache = InMemoryCache()
    req = make_request()
    assert cache.get(req) is None

    cache.put(req, make_result())
    hit = cache.get(req)
    assert hit is not None
    assert hit.cached is True
    assert hit.overallTrustScore == 80


def test_expired_entry_is_a_miss():
    cache = InMemoryCache()
    req = make_request()
    cache.put(req, make_result())

    # Backdate the stored expiry.
    cache._store[req.cache_key()]["expiresAt"] = int(time.time()) - 1
    assert cache.get(req) is None


def test_material_price_change_invalidates():
    """The core reason a plain TTL is not enough: a bait-and-switch listing
    mutates its price after banking reviews."""
    cache = InMemoryCache()
    cache.put(make_request(price=49.90), make_result())

    # 2% default tolerance: 50.20 is within, 60.00 is not.
    assert cache.get(make_request(price=50.20)) is not None
    assert cache.get(make_request(price=60.00)) is None


def test_spec_edit_invalidates():
    cache = InMemoryCache()
    cache.put(make_request(), make_result())

    changed = make_request(specs={"weight": "900g", "material": "ABS"})
    assert cache.get(changed) is None


def test_cache_key_separates_platforms():
    a = make_request(platform="shopee", itemId="1")
    b = make_request(platform="lazada", itemId="1")
    assert a.cache_key() != b.cache_key()


@pytest.mark.parametrize("field", ["title", "specs"])
def test_specs_hash_is_stable_and_sensitive(field):
    req = make_request()
    assert req.specs_hash() == make_request().specs_hash()

    changed = make_request(**{field: "different" if field == "title" else {"x": "y"}})
    assert changed.specs_hash() != req.specs_hash()
