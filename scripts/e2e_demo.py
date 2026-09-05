"""End-to-end check: a captured Shopee PDP payload, through the full API.

Runs entirely offline in mock mode. Exercises the same transformations the
content script performs (price descaling, image-hash to CDN URL, spec
flattening), so a regression in the payload contract surfaces here rather than
on a live Shopee page.

    python scripts/e2e_demo.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("MOCK_AWS", "true")

# On Windows, stdout defaults to cp1252 when piped or redirected, and the box
# and arrow characters below raise UnicodeEncodeError. The console happens to
# be UTF-8, so this only breaks the moment someone pipes the output to a file
# or a pager — which is exactly when they are trying to share a failure.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):  # pragma: no cover - very old or odd stdout
    pass

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.scoring import derive_risk_level  # noqa: E402

FIXTURE = ROOT / "backend" / "tests" / "fixtures" / "shopee_pdp_sample.json"
CDN = "https://down-sg.img.susercontent.com/file/"
PRICE_SCALE = 100_000

GREEN, YELLOW, RED, DIM, RESET = (
    "\033[32m",
    "\033[33m",
    "\033[31m",
    "\033[90m",
    "\033[0m",
)
COLORS = {"LOW": GREEN, "MEDIUM": YELLOW, "HIGH": RED}


def build_request(raw: dict) -> dict:
    """Mirror extension/src/shared/extract.js against the raw PDP payload."""
    item = raw["data"]["item"]

    specs = {a["name"]: a["value"] for a in item.get("attributes", [])}
    if item.get("weight"):
        specs["weight"] = f"{item['weight']} kg"
    d = item.get("dimension") or {}
    if d:
        specs["dimensions"] = f"{d['length']}x{d['width']}x{d['height']} cm"

    return {
        "platform": "shopee",
        "itemId": str(item["itemid"]),
        "shopId": str(item["shopid"]),
        "title": item["title"],
        "price": item["price"] / PRICE_SCALE,
        "originalPrice": item["price_before_discount"] / PRICE_SCALE,
        "sellerRating": item.get("shop_rating"),
        "shopLocation": item.get("shop_location"),
        "specs": specs,
        "imageUrls": [CDN + h for h in item.get("images", [])],
        "reviewImageUrls": [CDN + h for h in raw.get("_reviewImages", [])],
    }


def check(label: str, ok: bool) -> bool:
    print(f"  {GREEN}PASS{RESET} {label}" if ok else f"  {RED}FAIL{RESET} {label}")
    return ok


def main() -> int:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload = build_request(raw)

    print(f"\n{DIM}Fixture:{RESET} {raw['_sourceUrl']}")
    print(f"{DIM}Listing:{RESET} {payload['title'][:70]}")
    print(
        f"{DIM}Price:  {RESET} SGD {payload['price']:.2f} "
        f"(was {payload['originalPrice']:.2f})"
    )
    print(
        f"{DIM}Images: {RESET} {len(payload['imageUrls'])} gallery, "
        f"{len(payload['reviewImageUrls'])} review\n"
    )

    client = TestClient(app)

    health = client.get("/health").json()
    print(f"{DIM}Backend mock mode: {health['mockMode']}{RESET}\n")

    response = client.post("/api/v1/analyze", json=payload)
    if response.status_code != 200:
        print(f"{RED}Request failed: {response.status_code} {response.text}{RESET}")
        return 1

    result = response.json()
    color = COLORS.get(result["riskLevel"], DIM)
    s = result["subScores"]

    print(
        f"{color}▌{RESET} Trust score {color}{result['overallTrustScore']}/100"
        f"{RESET}  ({color}{result['riskLevel']}{RESET})"
    )
    print(f"    Visual integrity  {s['visualIntegrity']:>3}")
    print(f"    Spec consistency  {s['specConsistency']:>3}")
    print(f"    Price sanity      {s['priceSanity']:>3}")
    print(f"    Scale fidelity    {s['scaleFidelity']:>3}\n")

    sa = result["scaleAnalysis"]
    print(f"{DIM}    Real-world size{RESET}")
    print(f"    identified as: {sa['identifiedProduct']}")
    if sa["scaleConfidence"] == "NONE" or sa["apparentLongestCm"] is None:
        print(f"    {YELLOW}size could not be determined from the images{RESET}")
    else:
        claim = result.get("listedLongestCm") or sa["expectedLongestCm"]
        arrow = f"{claim:g} cm -> " if claim else ""
        marker = f"{RED}MISMATCH{RESET}" if sa["mismatchDetected"] else f"{GREEN}ok{RESET}"
        print(f"    {arrow}{sa['apparentLongestCm']:g} cm in photos  [{marker}]")

        refs = sa.get("sceneReferences") or []
        if refs:
            conflict = sa["referenceAgreement"] == "CONFLICT"
            header = (
                f"{RED}objects in frame contradict each other{RESET}"
                if conflict
                else "what each object in frame implies"
            )
            print(f"    {DIM}{header}{RESET}")
            for ref in refs:
                print(
                    f"      {ref['objectName']:<38} -> "
                    f"{ref['impliedProductCm']:g} cm"
                )
    print(f"{DIM}    {sa['explanation']}{RESET}\n")

    for finding in result["findings"]:
        print(f"    • {finding}")
    if result["specDiscrepancies"]:
        print(f"\n{DIM}    Spec discrepancies:{RESET}")
        for d in result["specDiscrepancies"]:
            print(f"    ! {d}")

    print(f"\n{DIM}Assertions{RESET}")
    second = client.post("/api/v1/analyze", json=payload).json()
    moved = client.post(
        "/api/v1/analyze", json={**payload, "price": payload["price"] * 3}
    ).json()

    ok = all(
        [
            check("price descaled from micros", abs(payload["price"] - 12.90) < 0.01),
            check("image hashes became CDN URLs", payload["imageUrls"][0].startswith(CDN)),
            check("trust score in range", 0 <= result["overallTrustScore"] <= 100),
            check(
                "risk level agrees with score",
                result["riskLevel"] == derive_risk_level(result["overallTrustScore"]).value,
            ),
            check("findings present", bool(result["findings"])),
            check("sub-scores present for UI breakdown", len(s) == 4),
            check(
                "claimed size parsed from specs",
                result.get("listedLongestCm") is not None,
            ),
            check(
                "scale estimate is null unless a reference was found",
                (sa["scaleConfidence"] == "NONE") == (sa["apparentLongestCm"] is None),
            ),
            check(
                "scene references reported per object",
                (sa["scaleConfidence"] == "NONE") or bool(sa["sceneReferences"]),
            ),
            check("repeat request served from cache", second["cached"] is True),
            check("price change busts the cache", moved["cached"] is False),
        ]
    )

    print(f"\n{GREEN}End-to-end OK{RESET}\n" if ok else f"\n{RED}Failures above{RESET}\n")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
