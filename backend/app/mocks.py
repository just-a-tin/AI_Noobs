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

from .schemas import AnalysisCore, AnalyzeRequest, ImageAnalysis, SubScores

_CLEAN = AnalysisCore(
    overallTrustScore=88,
    subScores=SubScores(visualIntegrity=92, specConsistency=90, priceSanity=82),
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
    subScores=SubScores(visualIntegrity=74, specConsistency=38, priceSanity=61),
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
    subScores=SubScores(visualIntegrity=12, specConsistency=20, priceSanity=19),
    findings=[
        "Gallery images show strong indicators of AI generation: malformed text "
        "on packaging and inconsistent reflections.",
        "Customer review photos show a visibly different, lower-grade product.",
        "Price is 82% below the median for this product category — far outside "
        "the range explainable by a legitimate promotion.",
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
        "Advertised 512GB capacity is implausible at the listed price.",
        "Brand named in the title does not appear on the product in review photos.",
        "No model number given, unusual for this category.",
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
