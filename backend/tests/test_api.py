from fastapi.testclient import TestClient

from app.main import app, cache
from app.scoring import derive_risk_level

client = TestClient(app)

PAYLOAD = {
    "platform": "shopee",
    "itemId": "22334455",
    "shopId": "998877",
    "title": "Anker Soundcore Life P3 Wireless Earbuds",
    "price": 59.90,
    "originalPrice": 129.00,
    "sellerRating": 4.8,
    "shopLocation": "Singapore",
    "specs": {"weight": "52g", "material": "ABS plastic", "dimensions": "6x5x3 cm"},
    "imageUrls": ["https://down-sg.img.susercontent.com/file/abc123"],
    "reviewImageUrls": ["https://down-sg.img.susercontent.com/file/def456"],
}


def setup_function():
    cache.clear()  # InMemoryCache in mock mode


def test_health_reports_mock_mode():
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["mockMode"] is True


def test_analyze_returns_full_contract():
    body = client.post("/api/v1/analyze", json=PAYLOAD).json()

    assert 0 <= body["overallTrustScore"] <= 100
    assert body["riskLevel"] in {"LOW", "MEDIUM", "HIGH"}
    assert isinstance(body["findings"], list) and body["findings"]
    assert set(body["subScores"]) == {
        "visualIntegrity",
        "specConsistency",
        "priceSanity",
        "scaleFidelity",
    }
    assert set(body["scaleAnalysis"]) == {
        "identifiedProduct",
        "scaleConfidence",
        "sceneReferences",
        "referenceAgreement",
        "expectedLongestCm",
        "apparentLongestCm",
        "mismatchDetected",
        "explanation",
    }
    assert set(body["imageAnalysis"]) == {
        "isAiGenerated",
        "visualDiscrepancyDetected",
        "explanation",
    }
    assert isinstance(body["specDiscrepancies"], list)
    assert body["cached"] is False


def test_risk_level_always_agrees_with_score():
    """The invariant the whole badge depends on."""
    for item_id in (str(n) for n in range(40)):
        body = client.post(
            "/api/v1/analyze", json={**PAYLOAD, "itemId": item_id}
        ).json()
        expected = derive_risk_level(body["overallTrustScore"])
        assert body["riskLevel"] == expected.value


def test_second_call_is_served_from_cache():
    first = client.post("/api/v1/analyze", json=PAYLOAD).json()
    second = client.post("/api/v1/analyze", json=PAYLOAD).json()

    assert first["cached"] is False
    assert second["cached"] is True
    assert first["overallTrustScore"] == second["overallTrustScore"]


def test_price_change_forces_reanalysis():
    client.post("/api/v1/analyze", json=PAYLOAD)
    moved = client.post(
        "/api/v1/analyze", json={**PAYLOAD, "price": PAYLOAD["price"] * 2}
    ).json()
    assert moved["cached"] is False


def test_mock_verdicts_are_deterministic():
    a = client.post("/api/v1/analyze", json={**PAYLOAD, "itemId": "777"}).json()
    cache.clear()
    b = client.post("/api/v1/analyze", json={**PAYLOAD, "itemId": "777"}).json()
    assert a["overallTrustScore"] == b["overallTrustScore"]


def test_rejects_malformed_payload():
    assert client.post("/api/v1/analyze", json={"itemId": "1"}).status_code == 422


def test_presentation_covers_every_risk_level():
    body = client.get("/api/v1/presentation").json()
    assert set(body) == {"LOW", "MEDIUM", "HIGH"}
    assert body["HIGH"]["color"] == "red"
