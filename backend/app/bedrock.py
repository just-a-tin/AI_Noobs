"""Claude-on-Bedrock listing analysis.

Output is constrained with `output_config.format` (json_schema), which is GA on
Bedrock. That turns "please reply with JSON" from a hope into a guarantee and
removes the repair/retry loop that otherwise fails on demo day.
"""

from __future__ import annotations

import json
import logging

from .config import settings
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

Score three dimensions independently, 0-100, where 100 is entirely trustworthy:

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

Then set overallTrustScore as a holistic judgement. It should broadly reflect \
the three sub-scores, weighted by which evidence is strongest, rather than a \
strict average.

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

    return f"""\
Analyse this {req.platform.value} listing.

Title: {req.title}
Price: SGD {req.price:.2f}{discount}
Seller rating: {req.sellerRating if req.sellerRating is not None else "unknown"}
Shop location: {req.shopLocation or "unknown"}
Specifications:
{specs}
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
        if settings.mock_aws:
            log.info("MOCK_AWS=true - returning canned verdict for %s", req.itemId)
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
