"""Mock-mode verdicts must be both stable and plausible.

Plausibility is a demo requirement, not a modelling one: a green badge on a
listing advertising 512GB earbuds at 82% off makes the product look broken.
"""

from app.mocks import mock_analysis
from app.scoring import derive_risk_level
from app.schemas import AnalyzeRequest, RiskLevel


def req(**overrides) -> AnalyzeRequest:
    base = {
        "platform": "shopee",
        "itemId": "22334455",
        "title": "Wireless Earbuds Pro",
        "price": 59.90,
        "specs": {},
    }
    base.update(overrides)
    return AnalyzeRequest(**base)


def test_deterministic_for_same_listing():
    a = mock_analysis(req())
    b = mock_analysis(req())
    assert a.overallTrustScore == b.overallTrustScore


def test_obvious_scam_listing_scores_high_risk():
    """The bundled fixture's own shape: deep discount, implausible capacity,
    weak rating, no warranty."""
    result = mock_analysis(
        req(
            title="Wireless Earbuds Pro ANC Bluetooth 5.3 512GB Storage",
            price=59.90,
            originalPrice=329.00,
            sellerRating=4.1,
            specs={"Storage Capacity": "512GB", "Warranty Type": "No Warranty"},
        )
    )
    assert derive_risk_level(result.overallTrustScore) is RiskLevel.HIGH
    assert result.imageAnalysis.isAiGenerated is True


def test_moderate_discount_is_not_treated_as_fraud():
    result = mock_analysis(
        req(price=99.00, originalPrice=149.00, sellerRating=4.9, specs={})
    )
    assert derive_risk_level(result.overallTrustScore) is not RiskLevel.HIGH


def test_unremarkable_listings_spread_across_personas():
    """With no signals, hashing should still exercise all three states."""
    levels = {
        derive_risk_level(mock_analysis(req(itemId=str(n))).overallTrustScore)
        for n in range(60)
    }
    assert levels == {RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH}
