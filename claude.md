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
cd backend && .venv/Scripts/python -m pytest -q      # 34 tests
python scripts/e2e_demo.py                           # offline end-to-end
python scripts/run_local.py                          # API on :8000
python scripts/make_icons.py                         # regenerate icons
```

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
- **A failed analysis must surface as `UNAVAILABLE`, never a neutral score.** A
  trust product must not imply "fine" when it means "unknown".
- Backend calls go through the **service worker**, not the content script
  (Shopee's CSP blocks page-context fetches to our API).

## Model

`anthropic.claude-opus-5` on Bedrock via `AnthropicBedrockMantle`. Structured
output uses `output_config.format` (json_schema) — GA on Bedrock, so no
JSON-repair retry loop. `effort` and `format` are both keys of the single
`output_config` dict.
