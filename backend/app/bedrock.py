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
from .reviews import is_substantive, strip_review_template
from .mocks import mock_analysis
from .schemas import ANALYSIS_SCHEMA, AnalysisCore, AnalyzeRequest

log = logging.getLogger(__name__)

# Identical on every request, so it is worth a cache breakpoint.
SYSTEM_PROMPT = """\
You are Sentinel, a fraud analyst for Southeast Asian e-commerce marketplaces \
(Shopee, Lazada, Amazon SG). You assess whether a product listing is honest or \
is set up for a bait-and-switch: attractive imagery and specifications \
advertising one product, with a cheaper or counterfeit item actually shipped.

Evaluate the listing across these dimensions and populate the diagnostic flags. \
Score five dimensions independently, 0-100, where 100 is entirely trustworthy:

1. VISUAL INTEGRITY - Are the gallery images genuine photographs of the product \
being sold? Look for generative-AI artefacts (malformed text on packaging, \
impossible reflections, incoherent fine detail, warped logos), stock imagery \
reused across unrelated products, watermarks from other retailers, and heavy \
compositing. Crucially, compare gallery images against customer review photos: \
a systematic mismatch between the two is the single strongest bait-and-switch \
signal, because review photos show what buyers actually received.

2. SPEC CONSISTENCY & TEXT SIGNALS - Do title, specification table and images \
describe one coherent product? Check that weight is physically plausible for the \
stated dimensions and material, that claimed capacity or performance is achievable \
(e.g., flag physically impossible 16TB flash drives), and that the brand in the \
title actually appears on the product. Flag any brand mismatches where a title claims \
a premium brand but the spec table says 'OEM' or 'No Brand'. Look for unedited AI/LLM \
boilerplate text or off-platform transaction requests (e.g., WhatsApp).

3. PRICE SANITY & COMMERCIAL TRUST - Is the price plausible for this category? \
Check for variant baiting (where the lowest price tier is an accessory like 'Cable Only') \
and implausible discounts on high-value goods outside official stores. A steep \
discount alone is not fraud; weigh it together with the visual and spec evidence.

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

5. REVIEW CREDIBILITY - What do buyers actually say? Written reviews are \
the only place a purchaser reports what really arrived, so they are the \
strongest textual counter-evidence to a seller's own description. Look for \
recurring substantive complaints - wrong size, wrong brand, missing parts, \
empty or expired stock, 'not as pictured' - and weigh a theme repeated by \
several independent buyers far more heavily than one unhappy customer.

   Judge whether the reviews themselves look genuine. Near-identical \
wording across reviews, uniformly generic praise naming no specific \
feature, or text unrelated to this product all indicate a review farm. The \
review population is described below: note especially how many reviews \
carried no usable text, since hundreds of ratings with almost no written \
content is a different thing from a handful of detailed reviews.

   Only reviews long enough to be meaningful are shown to you; one and two \
word reviews have already been discarded as uninformative. A SMALL NUMBER \
OF USABLE REVIEWS IS NOT EVIDENCE OF FRAUD - it is missing evidence. Score \
reviewCredibility near 50 and say so.

Then set overallTrustScore as a holistic judgement. It should broadly reflect \
the five sub-scores, weighted by which evidence is strongest, rather than a \
strict average. A confirmed scale mismatch is strong evidence of deliberate \
deception and should weigh heavily; an undeterminable scale should not.

IGNORE IMAGES THAT ARE NOT THE PRODUCT. Scraped pages sometimes include a \
user's profile picture, a marketplace promotional banner, a voucher tile, a \
category icon or an unrelated recommended product. Silently disregard any such \
image: do not describe it, do not treat it as a discrepancy, and do not let it \
influence any score. If after discarding them no genuine product imagery \
remains, say so plainly in the findings, keep visualIntegrity near 50 and set \
scaleConfidence to NONE - an unusable image set is missing evidence, not \
evidence of fraud.

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

    # The system prompt tells the model the claimed size is "given to you
    # below", so it has to actually be here. Parsed deterministically rather
    # than left to the model, so the claim is ground truth it checks against.
    listed_cm = listed_longest_cm(req.specs)
    claimed = (
        f"\nCLAIMED SIZE: the specifications state a longest dimension of "
        f"{listed_cm:g} cm. Check this against what this product really "
        f"measures and against the images."
        if listed_cm is not None
        else "\nCLAIMED SIZE: the listing states no dimensions. Judge expected "
        "versus apparent size only."
    )

    # Reviews are the one place a buyer says what actually arrived. The stats
    # matter as much as the text: hundreds of ratings with almost no written
    # content is a different signal from a handful of detailed reviews.
    # Reviews are the one place a buyer says what actually arrived. The stats
    # matter as much as the text: hundreds of ratings with almost no written
    # content is a different signal from a handful of detailed reviews.
    stats = req.reviewStats

    # Strip Shopee's review template before the model sees anything. The
    # tapped answers ('Quality: good', 'Value for money: worth it') come
    # from the same short list for every reviewer, so they pad the prompt
    # without distinguishing an honest listing from a fraudulent one - and
    # a review consisting only of them looks like feedback while carrying
    # none.
    usable_reviews = []
    template_only = 0
    for r in req.reviews:
        body = strip_review_template(r.text)
        if not is_substantive(body):
            template_only += 1
            continue
        usable_reviews.append((r, body))

    if usable_reviews:
        rendered = []
        for r, body in usable_reviews:
            stars = f"{r.rating}/5" if r.rating is not None else "no rating"
            photo = ", with photo" if r.hasImages else ""
            rendered.append(f'  - [{stars}{photo}] "{body}"')

        extras = ""
        if stats and stats.duplicateGroups:
            extras += f"; {stats.duplicateGroups} group(s) of near-identical reviews"
        if stats and stats.averageRating is not None:
            extras += f"; average rating {stats.averageRating}"

        shown = len(usable_reviews)
        if stats:
            counted = (
                f"{shown} of {stats.totalFound} carried usable written "
                f"text, {stats.discardedTooShort} were empty or too short"
            )
            if template_only:
                counted += (
                    f", {template_only} contained only tapped template "
                    "answers"
                )
        else:
            counted = f"{shown} shown"
        joined = "\n".join(rendered)
        reviews_block = f"\nCUSTOMER REVIEWS ({counted}{extras}):\n{joined}"
    elif (stats and stats.totalFound) or req.reviews:
        reviews_block = (
            f"\nCUSTOMER REVIEWS: {stats.totalFound if stats else len(req.reviews)} found, but none "
            "carried written text beyond the tapped template answers. "
            "Treat this as missing evidence, not as a finding."
        )
    else:
        reviews_block = "\nCUSTOMER REVIEWS: none could be retrieved."

    return f"""\
Analyse this {req.platform.value} listing.

Title: {req.title}
Price: SGD {req.price:.2f}{discount}
Seller rating: {req.sellerRating if req.sellerRating is not None else "unknown"}
Shop location: {req.shopLocation or "unknown"}
Specifications:
{specs}
{claimed}
{manifest}
{reviews_block}"""


class BedrockAnalyzer:
    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        """Build the Bedrock client for the configured API.

        Both expose the same messages.create surface; they differ in endpoint,
        IAM action and model-id form. See Settings.bedrock_api for why the
        legacy runtime path is the default.
        """
        if self._client is None:
            if settings.bedrock_api == "mantle":
                from anthropic import AnthropicBedrockMantle

                self._client = AnthropicBedrockMantle(aws_region=settings.aws_region)
            else:
                from anthropic import AnthropicBedrock

                self._client = AnthropicBedrock(aws_region=settings.aws_region)
            log.info(
                "bedrock client: %s (%s)", settings.bedrock_api, settings.model_id
            )
        return self._client

    async def analyze(self, req: AnalyzeRequest) -> AnalysisCore:
        # mock_bedrock, not mock_aws: the two are separate so real analysis can
        # run against the in-memory cache before DynamoDB is deployed.
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
                "effort": settings.effort,
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
