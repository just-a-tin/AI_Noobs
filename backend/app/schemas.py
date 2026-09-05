"""Request/response models, and the JSON schema Bedrock is constrained to.

The Bedrock output schema is *derived* from `AnalysisCore` rather than written
out by hand, so the model's contract and our parsing can never drift apart.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class Platform(str, Enum):
    SHOPEE = "shopee"
    LAZADA = "lazada"
    AMAZON_SG = "amazon_sg"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class CustomerReview(BaseModel):
    """One buyer review, already filtered for usefulness by the extension."""

    text: str
    rating: int | None = None
    hasImages: bool = False


class ReviewStats(BaseModel):
    """What the review population looked like before filtering.

    The model needs the shape of what was discarded, not just what survived:
    a listing with 400 reviews of which 6 carry real text reads very
    differently from one with 6 reviews all of which do.
    """

    totalFound: int = 0
    usable: int = 0
    discardedTooShort: int = 0
    duplicateGroups: int = 0
    averageRating: float | None = None


class AnalyzeRequest(BaseModel):
    platform: Platform = Platform.SHOPEE
    itemId: str
    # Not in the original spec, but Shopee's PDP API is keyed on (shop, item)
    # and the URL carries both: `-i.{shopId}.{itemId}`.
    shopId: str | None = None
    title: str
    price: float
    originalPrice: float | None = None
    sellerRating: float | None = None
    shopLocation: str | None = None
    specs: dict[str, str] = Field(default_factory=dict)
    imageUrls: list[HttpUrl] = Field(default_factory=list)
    reviewImageUrls: list[HttpUrl] = Field(default_factory=list)
    reviews: list["CustomerReview"] = Field(default_factory=list)
    reviewStats: "ReviewStats | None" = None

    def cache_key(self) -> str:
        return f"{self.platform.value}#{self.itemId}"

    def specs_hash(self) -> str:
        """Stable digest of the listing fields a seller could quietly edit."""
        payload = json.dumps(
            {"title": self.title, "specs": dict(sorted(self.specs.items()))},
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class ImageAnalysis(BaseModel):
    isAiGenerated: bool = Field(
        description="True if the seller's gallery images show signs of being AI-generated."
    )
    visualDiscrepancyDetected: bool = Field(
        description=(
            "True if the product in the gallery images differs from the product "
            "in customer review photos."
        )
    )
    explanation: str = Field(
        description="Two or three sentences on the visual evidence, citing what you saw."
    )


# NOTE: deliberately no docstring. A docstring here becomes the schema
# description for every field of this type and would compete with the
# field-level instruction on `scaleConfidence`, which is the specific one.
#
# NONE is the important value: absolute size cannot be recovered from a photo
# without something of known size in frame, so "cannot tell" must be
# expressible rather than forcing a fabricated number.
class ScaleConfidence(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


# No docstring, for the same reason as ScaleConfidence below: a class docstring
# becomes the schema description for every field of this type.
class ReferenceAgreement(str, Enum):
    NONE = "NONE"
    SINGLE = "SINGLE"
    AGREE = "AGREE"
    CONFLICT = "CONFLICT"


class SceneReference(BaseModel):
    """One object in the frame used to work out how big the product really is.

    Reading several at once does two jobs: it cross-checks the estimate, and
    disagreement between them is itself evidence the image is a composite.
    """

    objectName: str = Field(
        description=(
            "The recognisable object in the image being used for scale "
            "(e.g. 'adult person', 'two-seat sofa', 'standard doorway', "
            "'AA battery', 'human hand')."
        )
    )
    assumedRealCm: float = Field(
        description=(
            "The typical real-world size in cm of that reference object "
            "itself — not the product. E.g. an adult person is ~170 cm."
        )
    )
    impliedProductCm: float = Field(
        description=(
            "How big the product would have to be, in cm, if this reference "
            "is correct. Derived from their relative sizes in the image."
        )
    )


class ReviewAnalysis(BaseModel):
    """What the written reviews say, and whether they can be trusted.

    Reviews are the one place a buyer says what actually arrived, so they are
    the strongest textual counter-evidence to a seller's own description.
    """

    usableReviewCount: int = Field(
        description="How many reviews carried enough text to be worth reading."
    )
    complaintThemes: list[str] = Field(
        description=(
            "Recurring substantive complaints, each a short phrase (e.g. "
            "'arrived much smaller than pictured', 'bottle half empty', "
            "'different brand than advertised'). Empty if none recur."
        )
    )
    contradictsListing: bool = Field(
        description=(
            "True if reviewers describe receiving something materially "
            "different from what the listing advertises — wrong size, wrong "
            "brand, wrong product, or missing parts."
        )
    )
    suspectedFakeReviews: bool = Field(
        description=(
            "True only on positive evidence of manipulation: near-identical "
            "wording repeated across reviews, generic praise that names no "
            "specific feature, or text unrelated to this product. Few reviews "
            "is not evidence; fabricated ones are."
        )
    )
    explanation: str = Field(
        description=(
            "Two or three sentences on what the reviews show. If too few had "
            "usable text, say that plainly instead of inferring from silence."
        )
    )


class ScaleAnalysis(BaseModel):
    """Does the product's apparent size match reality and the listing?

    Three numbers are triangulated: what the listing claims, what this kind of
    product actually measures, and how big it looks next to a reference object.
    Any two disagreeing is the signal — it catches the common
    "ordered furniture, received a dollhouse version" scam.
    """

    identifiedProduct: str = Field(
        description=(
            "What the product in the images actually appears to be, as "
            "specifically as you can tell (e.g. 'wireless earbuds charging "
            "case', 'artificial Christmas tree')."
        )
    )
    scaleConfidence: ScaleConfidence = Field(
        description=(
            "HIGH/MEDIUM/LOW only if an object of known real-world size is "
            "visible in frame to judge against. If nothing provides scale, "
            "this MUST be NONE and the size estimates MUST be null. Absolute "
            "size cannot be recovered from a photo without a reference."
        )
    )
    sceneReferences: list[SceneReference] = Field(
        description=(
            "Every object in the images usable for scale, with what each one "
            "implies about the product's size. List all you can find, not just "
            "the best — several are more reliable than one, and disagreement "
            "between them is itself meaningful. Empty when nothing in frame "
            "has a knowable real size."
        )
    )
    referenceAgreement: ReferenceAgreement = Field(
        description=(
            "NONE when sceneReferences is empty. SINGLE when there is only "
            "one. AGREE when several references imply a consistent product "
            "size. CONFLICT when they imply sizes that cannot all be true of "
            "one real photograph — strong evidence the image is a composite "
            "or generated, independent of whether the listing's size claim is "
            "honest."
        )
    )
    expectedLongestCm: float | None = Field(
        description=(
            "From your own knowledge, the typical longest dimension in cm for "
            "this kind of product. Null if you genuinely cannot say."
        )
    )
    apparentLongestCm: float | None = Field(
        description=(
            "Best single estimate, in cm, of the product's longest dimension, "
            "consolidated across sceneReferences. Null when scaleConfidence "
            "is NONE."
        )
    )
    mismatchDetected: bool = Field(
        description=(
            "True only if the claimed, expected and apparent sizes disagree by "
            "enough to mislead a buyer. Never true on a null estimate."
        )
    )
    explanation: str = Field(
        description=(
            "Two or three sentences on how you judged the size, naming the "
            "objects you measured against. If the references disagree, say "
            "what that implies about the image. If scale could not be "
            "determined at all, say that plainly instead of guessing."
        )
    )


class SubScores(BaseModel):
    """Per-dimension scores backing the popup's diagnostic breakdown.

    Absent from the original spec, but the UI promises a three-part breakdown;
    without these the frontend would have to invent the numbers.

    Field descriptions below are sent to the model as part of the output
    schema, so they are written as instructions to it, not notes to ourselves.
    """

    visualIntegrity: int = Field(
        ge=0,
        le=100,
        description=(
            "0-100. Are gallery images genuine photographs of the product sold? "
            "Lower for AI-generation artefacts, reused stock imagery, foreign "
            "watermarks, or a systematic mismatch against review photos."
        ),
    )
    specConsistency: int = Field(
        ge=0,
        le=100,
        description=(
            "0-100. Do title, specification table and images describe one "
            "coherent, physically plausible product?"
        ),
    )
    priceSanity: int = Field(
        ge=0,
        le=100,
        description=(
            "0-100. Is the price explicable for this category? A steep discount "
            "alone is not fraud; weigh it with the other evidence."
        ),
    )
    reviewCredibility: int = Field(
        ge=0,
        le=100,
        description=(
            "0-100. Do the written reviews read like real buyers? Low when "
            "they are repetitive, generic, implausibly uniform, or describe a "
            "different product from the listing. Use 50 when too few reviews "
            "carry usable text to judge — an absence of reviews is not "
            "evidence of fraud."
        ),
    )
    scaleFidelity: int = Field(
        ge=0,
        le=100,
        description=(
            "0-100. Does the product's real size match what the listing claims "
            "and what the images imply? Low when images are staged to make a "
            "small item look large. Use 50 when scale could not be determined "
            "— an unknown is not a pass and not a failure."
        ),
    )


class AnalysisCore(BaseModel):
    """Exactly what the model produces. `riskLevel` is deliberately absent —
    the backend derives it from the score so the badge colour and the number
    can never disagree."""

    overallTrustScore: int = Field(
        ge=0,
        le=100,
        description=(
            "0-100 holistic trust judgement, where 100 is entirely trustworthy. "
            "Should broadly reflect the sub-scores weighted by which evidence is "
            "strongest, rather than a strict average."
        ),
    )
    subScores: SubScores
    scaleAnalysis: ScaleAnalysis
    reviewAnalysis: ReviewAnalysis
    findings: list[str] = Field(
        description=(
            "Specific, concrete observations a shopper could verify themselves. "
            "Not generic safety advice. If evidence is thin, say so here."
        )
    )
    imageAnalysis: ImageAnalysis
    specDiscrepancies: list[str] = Field(
        description=(
            "Direct contradictions between title, specification table and "
            "images. Empty if there are none."
        )
    )


class AnalysisResult(AnalysisCore):
    riskLevel: RiskLevel
    # Parsed deterministically from the specs, not asked of the model, so the
    # UI can show what the listing claimed alongside what the images implied.
    listedLongestCm: float | None = None
    cached: bool = False
    modelId: str | None = None
    analyzedAt: int | None = None  # epoch seconds


#: JSON Schema validation keywords that structured outputs reject.
#:
#: Bedrock returns a 400 for these — e.g. `Field(ge=0, le=100)` becomes
#: "minimum"/"maximum" and fails with "For 'integer' type, properties maximum,
#: minimum are not supported". Dropping them from the wire schema costs
#: nothing: the bounds still exist on the Pydantic model, so the response is
#: validated against them when it is parsed, and the field descriptions state
#: the intended range in words the model actually reads.
_UNSUPPORTED_KEYWORDS = frozenset(
    {
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "minLength",
        "maxLength",
        "pattern",
        "minItems",
        "maxItems",
        "uniqueItems",
        "format",
        "default",
    }
)


def _strictify(node: Any) -> Any:
    """Make a JSON schema acceptable to structured outputs.

    Requires `additionalProperties: false` and every property listed in
    `required` on each object node, and removes keywords the API rejects.

    Also strips the noise Pydantic generates: auto-titles like
    "Overalltrustscore", and object-level descriptions lifted from class
    docstrings. Everything in this schema is sent to the model as instruction,
    and our internal rationale about frontend design is not something it should
    be reading. Field-level descriptions are deliberately kept — those are
    written for the model.
    """
    if isinstance(node, dict):
        node = {
            k: _strictify(v)
            for k, v in node.items()
            if k != "title" and k not in _UNSUPPORTED_KEYWORDS
        }
        if node.get("type") == "object" and "properties" in node:
            node.pop("description", None)  # class docstring, not model guidance
            node["additionalProperties"] = False
            node["required"] = list(node["properties"].keys())
        return node
    if isinstance(node, list):
        return [_strictify(item) for item in node]
    return node


def build_analysis_schema() -> dict[str, Any]:
    """The json_schema handed to `output_config.format`."""
    schema = AnalysisCore.model_json_schema()

    # Structured outputs want a self-contained schema; inline the $defs that
    # Pydantic factors out for nested models.
    defs = schema.pop("$defs", {})

    def inline(node: Any) -> Any:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if ref and ref.startswith("#/$defs/"):
                # Merge, don't replace. Pydantic emits a field's own
                # description as a sibling of $ref, so returning the
                # definition alone silently drops the instruction written for
                # that field and leaves only the referenced class's docstring.
                # The field-level description is the specific one, so it wins.
                target = inline(defs[ref.split("/")[-1]])
                siblings = {
                    k: inline(v) for k, v in node.items() if k != "$ref"
                }
                return {**target, **siblings}
            return {k: inline(v) for k, v in node.items()}
        if isinstance(node, list):
            return [inline(item) for item in node]
        return node

    return _strictify(inline(schema))


ANALYSIS_SCHEMA = build_analysis_schema()
