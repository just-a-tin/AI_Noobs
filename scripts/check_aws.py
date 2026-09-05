"""Preflight for real Bedrock mode.

Checks the three things that actually go wrong, in the order they go wrong:
credentials, then model access, then a real round-trip. Each failure prints
what to do about it.

    python scripts/check_aws.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

# Windows pipes stdout as cp1252, which cannot encode the arrows below. This
# script's output is the thing people paste when asking for help, so it must
# survive being redirected to a file.
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
OK, BAD, WARN = f"{GREEN}OK{RESET}", f"{RED}FAIL{RESET}", f"{YELLOW}WARN{RESET}"

REGION = os.getenv("AWS_REGION", "us-east-1")
MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-opus-4-6-v1")
BEDROCK_API = os.getenv("BEDROCK_API", "runtime").strip().lower()


def step(n: int, title: str) -> None:
    print(f"\n{DIM}[{n}]{RESET} {title}")


def check_env() -> bool:
    step(1, "Configuration")
    print(f"    region   {REGION}")
    print(f"    model    {MODEL_ID}")

    mock = os.getenv("MOCK_BEDROCK", os.getenv("MOCK_AWS", "true")).lower()
    if mock in {"1", "true", "yes", "on"}:
        print(f"    {WARN} still in mock mode — set MOCK_BEDROCK=false in .env")
        return False
    print(f"    {OK} mock mode is off")
    return True


def check_credentials() -> bool:
    step(2, "AWS credentials")
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        print(f"    {BAD} boto3 not installed — run the backend pip install")
        return False

    key_id = os.getenv("AWS_ACCESS_KEY_ID", "")
    has_token = bool(os.getenv("AWS_SESSION_TOKEN"))

    # Temporary credentials start with ASIA and are useless without their
    # session token — a common and very confusing half-configured state.
    if key_id.startswith("ASIA") and not has_token:
        print(f"    {BAD} temporary credentials (ASIA...) without AWS_SESSION_TOKEN")
        print(f"{DIM}    SSO credentials need all three values. Copy the session"
              f" token too.{RESET}")
        return False

    try:
        identity = boto3.client("sts", region_name=REGION).get_caller_identity()
    except (ClientError, BotoCoreError) as exc:
        print(f"    {BAD} {exc}")
        msg = str(exc).lower()
        if "expired" in msg or "invalidclienttoken" in msg:
            print(f"\n{DIM}    These credentials have expired. Refresh them from"
                  f" the AWS SSO\n    Access Portal and update .env.{RESET}")
        else:
            print(f"\n{DIM}    Add these to .env (AWS console → IAM → Users →"
                  f" Security\n    credentials → Create access key):{RESET}")
            print("      AWS_ACCESS_KEY_ID=AKIA...")
            print("      AWS_SECRET_ACCESS_KEY=...")
        return False

    kind = "temporary (SSO)" if has_token else "permanent IAM"
    print(f"    {OK} authenticated as {identity['Arn']}")
    print(f"{DIM}    credential type: {kind}{RESET}")
    return True


def check_model_access() -> bool:
    step(3, "Bedrock model access")
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    try:
        client = boto3.client("bedrock", region_name=REGION)
        models = client.list_foundation_models()["modelSummaries"]
    except (ClientError, BotoCoreError) as exc:
        print(f"    {WARN} could not list models: {exc}")
        print(f"{DIM}    Needs bedrock:ListFoundationModels. Not fatal —"
              f" step 4 is the real test.{RESET}")
        return True

    ids = {m["modelId"] for m in models}

    # Inference-profile ids carry a region prefix ("us.", "global.") that
    # foundation-model ids do not, so compare on the bare id or this reports a
    # scary FAIL for a model that works perfectly.
    bare = MODEL_ID.split(".", 1)[1] if MODEL_ID.startswith(("us.", "global.", "eu.", "apac.")) else MODEL_ID

    if any(i == bare or i.startswith(bare + ":") for i in ids):
        print(f"    {OK} {MODEL_ID} is offered in {REGION}")
        return True

    # Advisory only — being listed is not the same as being entitled, and
    # step 4 is the authoritative test either way.
    print(f"    {WARN} {MODEL_ID} not found in the catalogue for {REGION}")
    print(f"{DIM}    Being listed and being entitled differ; step 4 decides."
          f"\n    Run scripts/list_models.py to see what is actually"
          f" invocable.{RESET}")
    return True


def check_round_trip() -> bool:
    step(4, f"Live model call (bedrock_api={BEDROCK_API})")
    try:
        from anthropic import AnthropicBedrock, AnthropicBedrockMantle
    except ImportError:
        print(f"    {BAD} anthropic SDK not installed")
        return False

    try:
        client = (
            AnthropicBedrockMantle(aws_region=REGION)
            if BEDROCK_API == "mantle"
            else AnthropicBedrock(aws_region=REGION)
        )
        response = client.messages.create(
            model=MODEL_ID,
            max_tokens=64,
            messages=[{"role": "user", "content": "Reply with exactly: SENTINEL OK"}],
        )
        text = next(
            (b.text for b in response.content if b.type == "text"), ""
        ).strip()
    except Exception as exc:
        print(f"    {BAD} {type(exc).__name__}: {exc}")
        msg = str(exc).lower()
        if "bedrock-mantle" in msg and "explicit deny" in msg:
            print(f"\n{DIM}    A service control policy denies bedrock-mantle."
                  f" Managed org accounts\n    often allow only the older API."
                  f" Set BEDROCK_API=runtime in .env and\n    use a model id of"
                  f" the form us.anthropic.claude-...{RESET}")
        elif "not available for this account" in msg:
            print(f"\n{DIM}    This account is not entitled to {MODEL_ID}."
                  f" Run\n    scripts/list_models.py to see what it can"
                  f" actually invoke.{RESET}")
        elif "legacy" in msg or "end of its life" in msg:
            print(f"\n{DIM}    That model is retired. Run"
                  f" scripts/list_models.py for current ones.{RESET}")
        elif "accessdenied" in msg or "not authorized" in msg:
            print(f"\n{DIM}    Enable model access: AWS console → Bedrock →")
            print(f"    Model access → Manage → tick Claude → Save.")
            print(f"    Also ensure the role has bedrock:InvokeModel.{RESET}")
        elif "could not connect" in msg or "endpoint" in msg:
            print(f"\n{DIM}    Bedrock may not exist in {REGION}."
                  f" Try us-east-1.{RESET}")
        return False

    print(f"    {OK} model replied: {text!r}")
    usage = getattr(response, "usage", None)
    if usage:
        print(
            f"{DIM}    tokens in={getattr(usage, 'input_tokens', '?')} "
            f"out={getattr(usage, 'output_tokens', '?')}{RESET}"
        )
    return True


def main() -> int:
    print(f"\n{DIM}Sentinel — AWS preflight{RESET}")

    if not check_env():
        return 1
    if not check_credentials():
        return 1
    check_model_access()  # advisory; step 4 is authoritative
    if not check_round_trip():
        return 1

    print(f"\n{GREEN}All checks passed — real Bedrock analysis is ready.{RESET}")
    print(f"{DIM}Start the server: python scripts/run_local.py{RESET}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
