# Sentinel — working notes

Scam-prevention extension for Shopee SG. See [README.md](README.md) for what it
does and how to run it. This file covers things that are easy to get wrong.

## Environment constraints

- **Node.js is not installed.** The extension is deliberately zero-build MV3 —
  plain JS loaded unpacked. `package.json` / `vite.config.ts` / `tailwind.config.js`
  are committed but dormant. Do not introduce a build step without checking Node
  is available first.
- **Python 3.14 is installed**; backend venv at `backend/.venv`.
- **AWS CLI and CDK are not installed.** `cdk deploy` also needs Node (the CDK
  CLI is a Node app even for Python CDK).

## Commands

```bash
cd backend && .venv/Scripts/python -m pytest -q      # 78 tests
python scripts/e2e_demo.py                           # offline end-to-end
python scripts/run_local.py                          # API on :8000
python scripts/check_aws.py                          # preflight for real Bedrock
python scripts/make_icons.py                         # regenerate icons
```

## Mode switches

`MOCK_AWS` is the master default; `MOCK_BEDROCK` and `USE_DYNAMODB` override it
independently. The useful middle state is real Bedrock with the in-memory cache
(`MOCK_BEDROCK=false`, `USE_DYNAMODB=false`) — the DynamoDB table only exists
after a CDK deploy. Tests set `SENTINEL_SKIP_DOTENV=1` so a developer's local
`.env` cannot change test outcomes.

## Shopee specifics that bite

- Product URL is `-i.{shopId}.{itemId}` — **shopId first**. Both are needed;
  the PDP API is keyed on the pair.
- `/api/v4/pdp/get_pc` returns **prices scaled by 100 000**.
- `images` are **CDN hashes**, not URLs — prefix with
  `https://down-sg.img.susercontent.com/file/`.
- Shopee is an SPA: `pushState` does not re-run content scripts, so
  `content.js` watches for navigation. Class names are obfuscated and rotate —
  never anchor a selector on one.

## Invariants worth preserving

- **`riskLevel` is derived in `scoring.py`, never returned by the model.** If
  you ever add it to `AnalysisCore`, the badge colour and the score can drift
  apart. `test_api.py::test_risk_level_always_agrees_with_score` guards this.
- **Everything in `ANALYSIS_SCHEMA` is sent to the model as instruction.**
  Pydantic lifts class docstrings into schema descriptions; `_strictify` strips
  object-level descriptions and auto-titles for that reason. Field-level
  descriptions are written *for the model* and are kept.
  See `test_schema_hygiene.py`.
- **Cache invalidates on price/spec change, not just TTL** — bait-and-switch
  listings mutate after banking reviews.
- **Scale estimates must be null without a reference object.** Absolute size is
  not recoverable from a photo; only size *relative to something of known size
  in frame* is. `scaleConfidence: NONE` with empty `sceneReferences` and null
  estimates is the correct answer for white-background studio shots, and must
  not be scored as either pass or fail.
  Guarded by `test_schema.py::test_scale_estimates_are_nullable`.
- **`sceneReferences` is a list on purpose.** Reading several objects at once
  cross-checks the estimate *and* yields a second signal: references implying
  incompatible sizes (`referenceAgreement: CONFLICT`) means the image is a
  composite, which is distinct from the product being undersized and holds even
  when the stated size is honest.
- **`_strictify` merges `$ref` siblings rather than replacing.** Pydantic puts a
  field's own description beside its `$ref`; replacing drops it and leaves only
  the referenced class's docstring. This silently ate the "MUST be NONE" rule
  once. `test_schema_hygiene.py::test_ref_fields_keep_their_own_description`.
- **Only product imagery may reach the model.** Everything on a Shopee page is
  served from `susercontent.com` — avatars, vouchers, category icons, 11.11
  banners, the "you may also like" carousel. `rejectionReason()` in
  `extract.js` filters on rendered size, aspect ratio, page-furniture
  ancestors, circular border-radius and links to *other* product ids. A verdict
  about someone's profile picture is worse than no verdict. The fixture page
  carries one of each distractor and the harness asserts none leak through.
- **A failed analysis must surface as `UNAVAILABLE`, never a neutral score.** A
  trust product must not imply "fine" when it means "unknown".
- Backend calls go through the **service worker**, not the content script
  (Shopee's CSP blocks page-context fetches to our API).

## Model

Structured output uses `output_config.format` (json_schema), so there is no
JSON-repair retry loop. `effort` and `format` are both keys of the single
`output_config` dict.

**The wire schema must not carry validation keywords.** Bedrock 400s on
`minimum`/`maximum` for integers — which is exactly what `Field(ge=0, le=100)`
generates. `_strictify` strips those and similar keywords
(`_UNSUPPORTED_KEYWORDS`). Nothing is lost: the bounds remain on the Pydantic
model, so the response is still validated when parsed.
`test_schema.py::test_no_range_constraints_reach_the_api`.

**Two Bedrock APIs, selected by `BEDROCK_API`.** `mantle` is the modern
Messages-API endpoint (`AnthropicBedrockMantle`, ids like
`anthropic.claude-opus-5`); `runtime` is `bedrock-runtime` InvokeModel
(`AnthropicBedrock`, ids like `us.anthropic.claude-opus-4-6-v1`). Default is
`runtime`: managed AWS Organizations often deny `bedrock-mantle:*` via service
control policy, which account-level permissions cannot override.

**Listed ≠ entitled.** `ListFoundationModels` advertises models the account
cannot invoke. `scripts/list_models.py --features` probes what actually works
and which of `json_schema` / `effort` / adaptive thinking each supports.

Verified working on the hackathon account (2026-09-05):
`us.anthropic.claude-opus-4-6-v1` via `runtime`, supporting all three features.
Opus 5, Sonnet 5, Opus 4.8, Opus 4.7 and Fable 5 return "not available for this
account"; Claude 3.5 Sonnet is retired by AWS.
