"""Canned verdicts for MOCK_AWS=true.

Two properties matter here, and they pull in different directions:

* **Deterministic** - a given listing always demos the same way. A demo that
  reshuffles its verdict between rehearsal and the judging table is worse than
  no demo.
* **Plausible** - the verdict should visibly respond to the listing. Handing a
  green badge to a listing advertising 512GB earbuds at 82% off makes the
  product look broken to exactly the audience you are trying to convince.

So selection runs cheap heuristics over the listing first and only falls back
to hashing the item id when nothing stands out.
"""

from __future__ import annotations

import hashlib
import re

from .schemas import (
    AnalysisCore,
    AnalyzeRequest,
    ImageAnalysis,
    ScaleAnalysis,
    ScaleConfidence,
    SubScores,
)

_CLEAN = AnalysisCore(
    overallTrustScore=88,
    subScores=SubScores(
        visualIntegrity=92, specConsistency=90, priceSanity=82, scaleFidelity=86
    ),
    scaleAnalysis=ScaleAnalysis(
        identifiedProduct="wireless earbuds charging case",
        scaleConfidence=ScaleConfidence.HIGH,
        scaleReference="adult hand holding the case",
        expectedLongestCm=6.0,
        apparentLongestCm=6.2,
        mismatchDetected=False,
        explanation=(
            "One review photo shows the case held in an adult hand, spanning "
            "roughly a third of the palm width. That puts it near 6 cm, which "
            "matches both the listed dimensions and the normal size for this "
            "product."
        ),
    ),
    findings=[
        "Gallery images and customer review photos show a consistent product.",
        "Listed weight and dimensions agree with the manufacturer's published specs.",
        "Price sits within the normal range for this category on Shopee SG.",
        "Seller rating and shop location are consistent with an established store.",
    ],
    imageAnalysis=ImageAnalysis(
        isAiGenerated=False,
        visualDiscrepancyDetected=False,
        explanation=(
            "Gallery photography shows natural lighting, consistent shadows and "
            "real background detail. Review images depict the same product with "
            "matching branding and proportions."
        ),
    ),
    specDiscrepancies=[],
)

_SPEC_MISMATCH = AnalysisCore(
    overallTrustScore=58,
    subScores=SubScores(
        visualIntegrity=74, specConsistency=38, priceSanity=61, scaleFidelity=50
    ),
    scaleAnalysis=ScaleAnalysis(
        identifiedProduct="compact bluetooth speaker",
        # The common, honest case: studio shots on white with nothing for scale.
        scaleConfidence=ScaleConfidence.NONE,
        scaleReference=None,
        expectedLongestCm=12.0,
        apparentLongestCm=None,
        mismatchDetected=False,
        explanation=(
            "All images are studio shots on a plain white background with no "
            "object of known size in frame, so the product's real size cannot "
            "be determined from them. This is common and not suspicious in "
            "itself, but it means size could not be verified."
        ),
    ),
    findings=[
        "Listed weight (2.4 kg) is inconsistent with the stated dimensions and "
        "material for this product class.",
        "Title claims 'aluminium body' while the specification table says ABS plastic.",
        "Review photos show a product that broadly matches, but with different "
        "port placement from the gallery images.",
    ],
    imageAnalysis=ImageAnalysis(
        isAiGenerated=False,
        visualDiscrepancyDetected=True,
        explanation=(
            "Gallery images appear to be genuine manufacturer renders, but the "
            "port layout differs from every customer review photo, suggesting the "
            "listing reuses imagery from a different model variant."
        ),
    ),
    specDiscrepancies=[
        "Title says aluminium; specs say ABS plastic.",
        "Stated weight 2.4 kg implausible for stated 12x8x3 cm dimensions.",
    ],
)

_BAIT_AND_SWITCH = AnalysisCore(
    overallTrustScore=17,
    subScores=SubScores(
        visualIntegrity=12, specConsistency=20, priceSanity=19, scaleFidelity=8
    ),
    scaleAnalysis=ScaleAnalysis(
        identifiedProduct="artificial Christmas tree",
        scaleConfidence=ScaleConfidence.HIGH,
        scaleReference="adult hand in customer review photo",
        expectedLongestCm=180.0,
        apparentLongestCm=22.0,
        mismatchDetected=True,
        explanation=(
            "Gallery images show the tree beside a sofa, implying roughly 180 "
            "cm. But a customer review photo shows the delivered item held in "
            "one hand, spanning barely the width of a palm — about 22 cm. The "
            "gallery photography is staged to make a desk ornament look like "
            "full-sized furniture."
        ),
    ),
    findings=[
        "Gallery images show the product at roughly 180 cm, but review photos "
        "show buyers holding a 22 cm version in one hand.",
        "Gallery images show strong indicators of AI generation: malformed text "
        "on packaging and inconsistent reflections.",
        "Customer review photos show a visibly different, lower-grade product.",
        "Price is far below the median for this product category — outside the "
        "range explainable by a legitimate promotion.",
        "Shop was created recently and has a low rating relative to its volume.",
    ],
    imageAnalysis=ImageAnalysis(
        isAiGenerated=True,
        visualDiscrepancyDetected=True,
        explanation=(
            "Primary gallery images exhibit classic generative artefacts: "
            "unreadable pseudo-text on the box, physically inconsistent "
            "reflections and a subject that does not match any review photo. "
            "Review images show a plain unbranded item."
        ),
    ),
    specDiscrepancies=[
        "Listing states a height of 180 cm, but review photos show an item that "
        "fits in one hand.",
        "Stated shipping weight of 0.31 kg is far too light for a 180 cm tree.",
        "Package dimensions (60 cm longest side) cannot contain a 180 cm tree.",
        "Brand named in the title does not appear on the product in review photos.",
    ],
)

_PERSONAS = (_CLEAN, _SPEC_MISMATCH, _BAIT_AND_SWITCH)

# Claims that are implausible for the categories these listings sit in, and so
# are strong tells in practice.
_IMPLAUSIBLE_CLAIMS = re.compile(
    r"\b(\d{3,})\s?(?:gb|tb)\b|\bunlimited\b|\b100%\s?original\b", re.I
)


def _risk_signals(req: AnalyzeRequest) -> int:
    """Count cheap, human-legible red flags. Higher means more suspicious."""
    signals = 0

    if req.originalPrice and req.originalPrice > 0:
        discount = 1 - (req.price / req.originalPrice)
        if discount >= 0.75:
            signals += 2
        elif discount >= 0.5:
            signals += 1

    haystack = " ".join([req.title, *req.specs.values()])
    if _IMPLAUSIBLE_CLAIMS.search(haystack):
        signals += 2

    if req.sellerRating is not None and req.sellerRating < 4.3:
        signals += 1

    if any("no warranty" in v.lower() for v in req.specs.values()):
        signals += 1

    return signals


def mock_analysis(req: AnalyzeRequest) -> AnalysisCore:
    """Pick a persona: heuristics first, hash as a stable tie-break."""
    signals = _risk_signals(req)

    if signals >= 4:
        persona = _BAIT_AND_SWITCH
    elif signals >= 2:
        persona = _SPEC_MISMATCH
    elif signals == 1:
        persona = _CLEAN
    else:
        # Nothing distinctive: spread across personas so a demo run over
        # several listings still shows all three states.
        digest = hashlib.sha256(req.itemId.encode("utf-8")).digest()
        persona = _PERSONAS[digest[0] % len(_PERSONAS)]

    return persona.model_copy(deep=True)
