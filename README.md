# Sentinel

**Scam shield for Shopee Singapore.** A Chrome extension that scores product
listings for bait-and-switch risk before you buy, backed by multimodal analysis
with Claude on Amazon Bedrock.

Built for the 2026 SimplifyNext Hackathon.

---

## What it does

Sentinel watches for Shopee SG product pages, extracts the listing (title,
price, specifications, seller gallery images and customer review photos), and
returns a 0–100 trust score with a diagnostic breakdown:

| Dimension | What it checks |
|---|---|
| **Visual integrity** | AI-generation artefacts, reused stock imagery, foreign watermarks — and whether the seller's gallery matches what buyers actually photographed |
| **Spec consistency** | Whether title, spec table and images describe one coherent product; whether weight is plausible for the stated dimensions and material |
| **Price sanity** | Whether the price is explicable for the category — weighed as corroborating evidence, never as proof on its own |
| **Scale fidelity** | Whether the product is really the size the listing implies — see below |

The badge is colour-coded: **green** ≥75, **yellow** 45–74, **red** <45.

The strongest signal is the comparison between seller gallery images and
verified customer review photos, because review photos show what buyers
actually received.

### Scale fidelity, and its one hard limit

This catches the "ordered a 180 cm Christmas tree, received a 22 cm desk
ornament" scam — a small item photographed to look full-sized. Three numbers
are triangulated:

| Source | Where it comes from |
|---|---|
| **Claimed** | Parsed from the listing's specs by [`dimensions.py`](backend/app/dimensions.py) |
| **Expected** | The model's own knowledge of what this product actually measures |
| **Apparent** | Estimated from the images against a reference object in frame |

**Absolute size cannot be recovered from a photograph.** A miniature shot close
up is pixel-for-pixel identical to a full-size object shot from further away.
Estimating apparent size therefore requires something of known size in the same
frame — a hand, a coin, a doorway, a person.

So the model inventories *every* usable object in the scene and reports what
each independently implies about the product:

```
two-seat sofa in gallery image         -> 175 cm
adult hand in customer review photo    ->  22 cm
dining table in customer review photo  ->  24 cm
```

When no such reference exists, `scaleConfidence` is `NONE`, the estimates are
`null`, and the UI says the size could not be verified. It does not guess, and
it does not treat "unknown" as either reassuring or damning. Listings with only
white-background studio shots are extremely common and are not suspicious for
lacking scale cues.

### Conflicting references mean the image is fake

Reading several objects at once buys a second, independent signal. If a person
in the frame implies the product is 95 cm but a wall socket in the *same* frame
implies 34 cm, no real photograph can produce both — the image has been
composited or generated.

That is reported as `referenceAgreement: CONFLICT`, and it is a different
finding from the product merely being smaller than advertised: it catches a
doctored image even when the listing's stated size is honest. Tolerance is
deliberately generous, since perspective and lens choice shift apparent sizes
legitimately.

---

## Quickstart (60 seconds, no AWS account, no Node)

```bash
# 1. Backend
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # Linux/macOS: .venv/bin/pip
.venv/Scripts/python -m uvicorn app.main:app --reload

# 2. Verify — runs entirely offline
python scripts/e2e_demo.py
cd backend && .venv/Scripts/python -m pytest -q
```

Then load the extension:

1. Open `chrome://extensions`
2. Enable **Developer mode**
3. **Load unpacked** → select the `extension/` folder
4. Visit any `https://shopee.sg/…-i.<shopId>.<itemId>` page

To see the UI with no backend running at all, open
`extension/test/fixture-page.html` in the browser — it exercises the DOM
extractor and renders the badge from a canned verdict.

`MOCK_AWS=true` is the default, so nothing above touches AWS.

---

## Layout

```
extension/   Chrome MV3 extension — loads unpacked, no build step
backend/     FastAPI service; Bedrock + DynamoDB, Mangum-wrapped for Lambda
infra/       AWS CDK (Python) — written and reviewable, not yet deployed
scripts/     run_local.py, e2e_demo.py, make_icons.py
```

### Why the extension has no build step

Node is not installed on the development machine this was scaffolded on, so the
extension is plain MV3 JavaScript that Chrome loads directly. The full
TypeScript + Vite + Tailwind config is committed alongside it
(`package.json`, `vite.config.ts`, `tsconfig.json`, `tailwind.config.js`) and
marked dormant — run `npm install && npm run build` once Node is available. The
popup's hand-written CSS deliberately mirrors Tailwind's scale and palette so
that migration is cosmetic.

---

## API

`POST /api/v1/analyze`

```jsonc
{
  "platform": "shopee",
  "itemId": "22334455",
  "shopId": "998877",          // Shopee's PDP API is keyed on (shop, item)
  "title": "Wireless Earbuds Pro ANC …",
  "price": 59.90,
  "originalPrice": 329.00,
  "sellerRating": 4.1,
  "shopLocation": "Singapore",
  "specs": { "Brand": "SoundMax", "Storage Capacity": "512GB" },
  "imageUrls": ["https://down-sg.img.susercontent.com/file/…"],
  "reviewImageUrls": ["https://down-sg.img.susercontent.com/file/…"]
}
```

Response adds `riskLevel`, `subScores`, `findings`, `imageAnalysis`,
`specDiscrepancies`, and `cached`. Full schema at
<http://localhost:8000/docs>.

Also available: `GET /health`, `GET /api/v1/presentation` (badge colours and
labels, so frontend and backend cannot disagree about them).

---

## Design notes

Four decisions that aren't obvious from the code:

**`riskLevel` is computed by the backend, never returned by the model.**
Asking an LLM to keep a 0–100 score and a three-value enum mutually consistent
reliably produces a green badge next to a score of 31. The model returns the
score; [`scoring.py`](backend/app/scoring.py) derives the level.

**The cache invalidates on price change, not just on a 24h TTL.** Bait-and-switch
listings mutate after banking reviews, and serving a stale "safe" verdict across
that change is the exact failure Sentinel exists to prevent. Entries store price
and a spec hash; a >2% price move or any title/spec edit is treated as a miss.
See [`cache.py`](backend/app/cache.py).

**Backend calls go through the background service worker, never the content
script.** A `fetch` issued from page context is subject to Shopee's
Content-Security-Policy and fails with no useful error.

**Listing extraction prefers Shopee's PDP JSON API over the DOM.** Shopee is an
SPA with obfuscated, rotating class names, so DOM scraping is brittle by
construction. [`extract.js`](extension/src/shared/extract.js) tries
`/api/v4/pdp/get_pc` first (same-origin from the page, so cookies attach), then
falls back to DOM heuristics anchored on semantic structure and text shape. Two
details that bite: prices come back scaled by 100 000, and images are CDN
hashes rather than URLs.

---

## Turning on real AI

Mock mode is the default. To use real Claude analysis:

1. Put credentials in `.env` — `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`,
   plus `AWS_SESSION_TOKEN` if they are temporary SSO credentials (they start
   with `ASIA` and expire within hours).
2. Set `MOCK_BEDROCK=false`.
3. Find a model this account can actually invoke:
   `python scripts/list_models.py --features`
4. Verify the whole path: `python scripts/check_aws.py`

Leave `USE_DYNAMODB=false` until the CDK stack is deployed — the in-memory
cache works fine, and pointing at a table that doesn't exist only fills the
logs with errors.

Note that real analysis costs money per listing, and images are token-heavy.

### Two things that bite on restricted AWS accounts

**Listed ≠ entitled.** `ListFoundationModels` will happily advertise every
Claude model while the account is entitled to a handful. The only reliable test
is to invoke each one, which is what `scripts/list_models.py` does.

**`bedrock-mantle` may be denied outright.** Managed AWS Organizations
frequently carry a service control policy denying the newer Messages-API
endpoint, which no account-level permission can override. `BEDROCK_API=runtime`
uses the older `bedrock-runtime` path instead and works in more environments.
The two take different model-id forms — `us.anthropic.claude-opus-4-6-v1`
versus `anthropic.claude-opus-5`.

## Going live on AWS

```bash
cd infra
pip install -r requirements.txt
cdk deploy
```

Then set `MOCK_AWS=false` and point `extension/src/shared/config.js` at the
deployed API URL (and add that origin to `host_permissions` in the manifest).

Two prerequisites that are not automatic:

- **Node is required for `cdk deploy`** — the CDK CLI is a Node application even
  for a Python CDK app. Nothing else in this repo needs Node. If you would
  rather avoid it, AWS SAM is pip-installable and could replace the CDK app.
- **Bedrock model access must be enabled** for `anthropic.claude-opus-5` in your
  account, in the target region.

---

## Scope and conduct

Sentinel analyses a page the user is already viewing — user-initiated,
user-visible, one listing at a time. It is closer to an accessibility overlay
than a crawler, and should stay that way: no bulk crawling, no background
enumeration of the catalogue.

Scores are advisory. A low score means "look more carefully", not proof of
fraud.
