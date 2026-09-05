"""Find which Bedrock models this account can actually invoke.

Listing a model is not the same as being entitled to it: a managed AWS
Organization can advertise every Claude model while permitting only a handful.
The only reliable test is to call each one, so this does exactly that and
reports which succeed, plus whether each supports the features Sentinel needs.

    python scripts/list_models.py            # availability only (cheap)
    python scripts/list_models.py --features # also probe feature support

Each invocation is a real, billable request, though a tiny one.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):  # pragma: no cover
    pass

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

GREEN, RED, YELLOW, DIM, RESET = (
    "\033[32m",
    "\033[31m",
    "\033[33m",
    "\033[90m",
    "\033[0m",
)

REGION = os.getenv("AWS_REGION", "us-east-1")
BEDROCK_API = os.getenv("BEDROCK_API", "runtime").strip().lower()

# Features Sentinel depends on. A model failing any of these needs code changes,
# not just a different id.
SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}
FEATURES = {
    "json_schema output": {
        "output_config": {"format": {"type": "json_schema", "schema": SCHEMA}}
    },
    "effort": {"output_config": {"effort": "high"}},
    "adaptive thinking": {"thinking": {"type": "adaptive"}},
}


def build_client():
    if BEDROCK_API == "mantle":
        from anthropic import AnthropicBedrockMantle

        return AnthropicBedrockMantle(aws_region=REGION)
    from anthropic import AnthropicBedrock

    return AnthropicBedrock(aws_region=REGION)


def candidate_ids() -> list[str]:
    """Claude inference profiles the account can see, newest-looking first."""
    import boto3

    try:
        bd = boto3.client("bedrock", region_name=REGION)
        profiles = bd.list_inference_profiles().get("inferenceProfileSummaries", [])
    except Exception as exc:
        print(f"{YELLOW}Could not list inference profiles: {exc}{RESET}")
        return []

    ids = [
        p["inferenceProfileId"]
        for p in profiles
        if "claude" in p["inferenceProfileId"].lower()
    ]
    # Prefer the regional (us.) profiles; global ones duplicate them.
    return [i for i in ids if not i.startswith("global.")]


def classify(exc: Exception) -> str:
    msg = str(exc)
    if "not available for this account" in msg:
        return "not entitled"
    if "Legacy" in msg or "end of its life" in msg:
        return "retired"
    if "explicit deny" in msg:
        return "denied by policy"
    if "not authorized" in msg or "AccessDenied" in msg:
        return "no permission"
    return f"{type(exc).__name__}"


def main() -> int:
    probe_features = "--features" in sys.argv
    client = build_client()
    ids = candidate_ids()

    if not ids:
        print("No Claude inference profiles visible in this region.")
        return 1

    print(f"\n{DIM}region {REGION} · bedrock_api {BEDROCK_API} · "
          f"{len(ids)} candidates{RESET}\n")

    working: list[str] = []
    for model in ids:
        try:
            client.messages.create(
                model=model,
                max_tokens=8,
                messages=[{"role": "user", "content": "Say OK"}],
            )
        except Exception as exc:
            print(f"  {DIM}—      {model}  ({classify(exc)}){RESET}")
            continue
        print(f"  {GREEN}usable{RESET} {model}")
        working.append(model)

    if not working:
        print(f"\n{RED}No usable models. Ask whoever administers this AWS "
              f"account which Claude models it is entitled to.{RESET}\n")
        return 1

    if probe_features:
        print(f"\n{DIM}Feature support{RESET}")
        for model in working:
            missing = []
            for label, kwargs in FEATURES.items():
                try:
                    client.messages.create(
                        model=model,
                        max_tokens=32,
                        messages=[{"role": "user", "content": "Reply briefly."}],
                        **kwargs,
                    )
                except Exception:
                    missing.append(label)
            if missing:
                print(f"  {YELLOW}{model}{RESET}  missing: {', '.join(missing)}")
            else:
                print(f"  {GREEN}{model}{RESET}  supports everything Sentinel uses")

    print(f"\n{DIM}Set the one you want in .env:{RESET}")
    print(f"  BEDROCK_MODEL_ID={working[0]}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
