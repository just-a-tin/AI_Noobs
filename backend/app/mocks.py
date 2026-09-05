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
    ReviewAnalysis,
    AnalyzeRequest,
    ImageAnalysis,
    ReferenceAgreement,
    ScaleAnalysis,
    ScaleConfidence,
    SceneReference,
    SubScores,
)

_CLEAN = AnalysisCore(
    overallTrustScore=88,
    subScores=SubScores(
        visualIntegrity=92,
        specConsistency=90,
        priceSanity=82,
        scaleFidelity=86,
        reviewCredibility=84,
    ),
    scaleAnalysis=ScaleAnalysis(
        identifiedProduct="wireless earbuds charging case",
        scaleConfidence=ScaleConfidence.HIGH,
        sceneReferences=[
            SceneReference(
                objectName="adult hand holding the case",
                assumedRealCm=18.0,
                impliedProductCm=6.2,
            ),
            SceneReference(
                objectName="desk keyboard beside the case",
                assumedRealCm=44.0,
                impliedProductCm=6.0,
            ),
        ],
        referenceAgreement=ReferenceAgreement.AGREE,
        expectedLongestCm=6.0,
        apparentLongestCm=6.1,
        mismatchDetected=False,
        explanation=(
            "A review photo shows the case held in an adult hand, spanning "
            "about a third of the palm — near 6 cm. A second photo beside a "
            "keyboard gives the same answer. Both agree with the listed "
            "dimensions and with normal size for this product."
        ),
    ),
    reviewAnalysis=ReviewAnalysis(
        usableReviewCount=11,
        complaintThemes=[],
        contradictsListing=False,
        suspectedFakeReviews=False,
        explanation=(
            "Eleven reviews carried substantive text. They mention specific "
            "details — battery life, case size, fit in the ear — and vary in "
            "phrasing and sentiment, which is what genuine buyer feedback "
            "looks like. Nothing contradicts the listing."
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
        visualIntegrity=74,
        specConsistency=38,
        priceSanity=61,
        scaleFidelity=50,
        reviewCredibility=45,
    ),
    scaleAnalysis=ScaleAnalysis(
        identifiedProduct="floor-standing air purifier",
        # Objects in frame contradict each other: the photo is a composite.
        scaleConfidence=ScaleConfidence.MEDIUM,
        sceneReferences=[
            SceneReference(
                objectName="adult person standing beside the unit",
                assumedRealCm=170.0,
                impliedProductCm=95.0,
            ),
            SceneReference(
                objectName="wall power socket behind the unit",
                assumedRealCm=12.0,
                impliedProductCm=34.0,
            ),
            SceneReference(
                objectName="interior doorway in background",
                assumedRealCm=200.0,
                impliedProductCm=88.0,
            ),
        ],
        referenceAgreement=ReferenceAgreement.CONFLICT,
        expectedLongestCm=70.0,
        apparentLongestCm=90.0,
        mismatchDetected=True,
        explanation=(
            "The person and the doorway both put the unit near 90 cm, but the "
            "wall socket behind it implies only 34 cm. No single real "
            "photograph can satisfy both, so the product has most likely been "
            "composited into a room scene at an exaggerated size."
        ),
    ),
    reviewAnalysis=ReviewAnalysis(
        usableReviewCount=6,
        complaintThemes=[
            "unit smaller than it appears in the listing photos",
            "build feels like plastic despite the aluminium claim",
        ],
        contradictsListing=True,
        suspectedFakeReviews=False,
        explanation=(
            "Six reviews had usable text and read as genuine, but two "
            "independently describe the product as smaller and cheaper-feeling "
            "than the listing implies. That is corroboration of the spec "
            "mismatch rather than evidence of review manipulation."
        ),
    ),
    findings=[
        "Objects in the main image contradict each other: a person and a "
        "doorway imply a 90 cm unit, while the wall socket implies 34 cm. The "
        "room scene appears to be composited.",
        "Title claims 'aluminium body' while the specification table says ABS plastic.",
        "Review photos show a product that broadly matches, but with different "
        "port placement from the gallery images.",
    ],
    imageAnalysis=ImageAnalysis(
        isAiGenerated=False,
        visualDiscrepancyDetected=True,
        explanation=(
            "The lifestyle shot is internally inconsistent — the product's size "
            "relative to the wall socket does not agree with its size relative "
            "to the person or the doorway. That geometry cannot occur in a "
            "single real photograph, indicating the product was composited in."
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
        visualIntegrity=12,
        specConsistency=20,
        priceSanity=19,
        scaleFidelity=8,
        reviewCredibility=9,
    ),
    scaleAnalysis=ScaleAnalysis(
        identifiedProduct="artificial Christmas tree",
        scaleConfidence=ScaleConfidence.HIGH,
        sceneReferences=[
            SceneReference(
                objectName="two-seat sofa in gallery image",
                assumedRealCm=180.0,
                impliedProductCm=175.0,
            ),
            SceneReference(
                objectName="adult hand in customer review photo",
                assumedRealCm=18.0,
                impliedProductCm=22.0,
            ),
            SceneReference(
                objectName="dining table in customer review photo",
                assumedRealCm=75.0,
                impliedProductCm=24.0,
            ),
        ],
        # Gallery and review photos disagree, but each is internally coherent:
        # this is a staging lie about the product, not a doctored image.
        referenceAgreement=ReferenceAgreement.AGREE,
        expectedLongestCm=180.0,
        apparentLongestCm=22.0,
        mismatchDetected=True,
        explanation=(
            "The seller's gallery stages the tree beside a sofa, implying "
            "about 175 cm. Every customer review photo tells a different "
            "story: against a hand it is 22 cm, against a dining table 24 cm. "
            "The review photos agree with each other, so the gallery is "
            "staged to make a desk ornament look like full-sized furniture."
        ),
    ),
    reviewAnalysis=ReviewAnalysis(
        usableReviewCount=4,
        complaintThemes=[
            "received a tiny desk ornament, not a floor-standing tree",
            "nothing like the photos",
        ],
        contradictsListing=True,
        suspectedFakeReviews=True,
        explanation=(
            "Only 4 of 312 reviews carried real text, and those describe "
            "receiving a hand-sized ornament. The remaining ratings are empty "
            "or one-word praise, with several near-identical phrasings — the "
            "signature of a review farm padding the score."
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
