"""Claude-on-Bedrock listing analysis.

Output is constrained with `output_config.format` (json_schema), which is GA on
Bedrock. That turns "please reply with JSON" from a hope into a guarantee and
removes the repair/retry loop that otherwise fails on demo day.
"""

from __future__ import annotations

import json
import logging

from .config import settings
from .dimensions import listed_longest_cm
from .images import PreparedImage, prepare_images
from .mocks import mock_analysis
from .schemas import ANALYSIS_SCHEMA, AnalysisCore, AnalyzeRequest

log = logging.getLogger(__name__)

# Identical on every request, so it is worth a cache breakpoint.
SYSTEM_PROMPT = """\
You are Sentinel, a fraud analyst for Southeast Asian e-commerce marketplaces \
(Shopee, Lazada, Amazon SG). You assess whether a product listing is honest or \
is set up for a bait-and-switch: attractive imagery and specifications \
advertising one product, with a cheaper or counterfeit item actually shipped.

Score four dimensions independently, 0-100, where 100 is entirely trustworthy:

1. VISUAL INTEGRITY - Are the gallery images genuine photographs of the product \
being sold? Look for generative-AI artefacts (malformed text on packaging, \
impossible reflections, incoherent fine detail, warped logos), stock imagery \
reused across unrelated products, watermarks from other retailers, and heavy \
compositing. Crucially, compare gallery images against customer review photos: \
a systematic mismatch between the two is the single strongest bait-and-switch \
signal, because review photos show what buyers actually received.

2. SPEC CONSISTENCY - Do title, specification table and images describe one \
coherent product? Check that weight is physically plausible for the stated \
dimensions and material, that claimed capacity or performance is achievable, \
and that the brand in the title actually appears on the product.

3. PRICE SANITY - Is the price plausible for this category? A steep discount is \
not by itself fraud; weigh it together with the visual and spec evidence. Treat \
price as corroborating evidence, not as proof on its own.

4. SCALE FIDELITY - Is the product really the size a buyer would expect? This \
catches one of the most common marketplace scams: photographing a small item so \
it appears full-sized, so the buyer orders furniture and receives a doll-sized \
version. Triangulate three numbers:

   (a) CLAIMED - the size stated in the listing, given to you below when the \
       specifications contain one.
   (b) EXPECTED - from your own knowledge, what this kind of product actually \
       measures in the real world.
   (c) APPARENT - how big the product looks in the images.

   To judge (c), read the whole scene. Inventory every object in the frame \
whose real-world size you know - a person (~170 cm), a hand (~18 cm), a \
doorway (~200 cm), a sofa (~180 cm), a coin, a phone, a keyboard, a mug, a \
power socket, floor tiles, a ruler - and for EACH one work out what size the \
product would have to be if that object is the size you expect. Report every \
usable reference you find in sceneReferences, not just the best one.

   CRITICAL: absolute size cannot be recovered from a photograph without such \
a reference. A miniature photographed close up is pixel-for-pixel identical to \
a full-size object photographed further away. If nothing in frame has a \
knowable real size, set scaleConfidence to NONE, leave sceneReferences empty \
and apparentLongestCm null, and say so. Do not guess a number, and do not \
treat a missing estimate as either reassuring or damning - score \
scaleFidelity around 50.

   CROSS-CHECK THE REFERENCES AGAINST EACH OTHER. If a person in the image \
implies the product is 30 cm but a doorway in the same image implies it is \
200 cm, no real photograph could produce both - the image has been composited \
or generated. Set referenceAgreement to CONFLICT and lower visualIntegrity as \
well as scaleFidelity. This is a separate finding from the product simply \
being smaller than advertised, and it holds even when the listing's stated \
size is honest. Allow generous tolerance before calling CONFLICT: perspective, \
camera lens choice and an object being nearer or further from the camera all \
shift apparent sizes legitimately. Only flag disagreements too large for \
those to explain.

   Report a mismatch only when the disagreement is large enough to actually \
mislead a buyer. Manufacturing tolerance, packaging-versus-product size, and \
rounding are not fraud. A listing whose only images are plain white-background \
studio shots with nothing for scale is very common and is not by itself \
suspicious - it is simply undeterminable.

Then set overallTrustScore as a holistic judgement. It should broadly reflect \
the four sub-scores, weighted by which evidence is strongest, rather than a \
strict average. A confirmed scale mismatch is strong evidence of deliberate \
deception and should weigh heavily; an undeterminable scale should not.

Write findings as specific, concrete observations a shopper could verify \
themselves - not generic safety advice. If evidence is thin or images are \
missing, say so in the findings and score nearer the middle rather than \
inventing certainty in either direction. Never accuse a listing of fraud on \
price alone.
"""


def _describe_listing(req: AnalyzeRequest, images: list[PreparedImage]) -> str:
    specs = (
        "\n".join(f"  - {k}: {v}" for k, v in req.specs.items())
        or "  (none provided)"
    )
    discount = ""
    if req.originalPrice and req.originalPrice > req.price:
        pct = round((1 - req.price / req.originalPrice) * 100)
        discount = f"\nOriginal price: SGD {req.originalPrice:.2f} (a {pct}% discount)"

    n_gallery = sum(1 for i in images if i.kind == "gallery")
    n_review = sum(1 for i in images if i.kind == "review")
    if images:
        manifest = (
            f"\nThe {len(images)} attached images are, in order: "
            f"{n_gallery} seller gallery image(s), then {n_review} verified "
            f"customer review photo(s). Compare the two groups directly."
        )
    else:
        manifest = (
            "\nNo images could be retrieved. Judge on text alone, note this "
            "limitation in your findings, and keep visualIntegrity near 50."
        )

    listed_cm = listed_longest_cm(req.specs)
    claimed = (
        f"\nCLAIMED SIZE: the specifications state a longest dimension of "
        f"{listed_cm:g} cm. Check this against what this product really "
        f"measures and against the images."
        if listed_cm is not None
        else "\nCLAIMED SIZE: the listing states no dimensions. Judge expected "
        "versus apparent size only."
    )

    return f"""\
Analyse this {req.platform.value} listing.

Title: {req.title}
Price: SGD {req.price:.2f}{discount}
Seller rating: {req.sellerRating if req.sellerRating is not None else "unknown"}
Shop location: {req.shopLocation or "unknown"}
Specifications:
{specs}
{claimed}
{manifest}"""


class BedrockAnalyzer:
    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is None:
            # The Mantle client is the current Messages-API path for Bedrock;
            # plain AnthropicBedrock is the legacy InvokeModel route.
            from anthropic import AnthropicBedrockMantle

            self._client = AnthropicBedrockMantle(aws_region=settings.aws_region)
        return self._client

    async def analyze(self, req: AnalyzeRequest) -> AnalysisCore:
        if settings.mock_bedrock:
            log.info("mock mode - returning canned verdict for %s", req.itemId)
            return mock_analysis(req)

        images = await prepare_images(
            [str(u) for u in req.imageUrls],
            [str(u) for u in req.reviewImageUrls],
            settings.max_images,
        )

        content: list[dict] = [img.block for img in images]
        content.append({"type": "text", "text": _describe_listing(req, images)})

        response = self._get_client().messages.create(
            model=settings.model_id,
            max_tokens=4096,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            thinking={"type": "adaptive"},
            output_config={
                "effort": "high",
                "format": {"type": "json_schema", "schema": ANALYSIS_SCHEMA},
            },
            messages=[{"role": "user", "content": content}],
        )

        usage = getattr(response, "usage", None)
        if usage is not None:
            log.info(
                "bedrock usage in=%s out=%s cache_read=%s",
                getattr(usage, "input_tokens", "?"),
                getattr(usage, "output_tokens", "?"),
                getattr(usage, "cache_read_input_tokens", "?"),
            )

        # With output_config.format the response carries valid JSON in a text
        # block; thinking blocks may precede it, so select by type.
        text = next(b.text for b in response.content if b.type == "text")
        return AnalysisCore.model_validate(json.loads(text))


analyzer = BedrockAnalyzer()
