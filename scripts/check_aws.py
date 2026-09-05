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
MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-opus-5")


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

    try:
        identity = boto3.client("sts", region_name=REGION).get_caller_identity()
    except (ClientError, BotoCoreError) as exc:
        print(f"    {BAD} {exc}")
        print(f"\n{DIM}    Add these to .env (AWS console → IAM → Users → Security")
        print(f"    credentials → Create access key):{RESET}")
        print("      AWS_ACCESS_KEY_ID=AKIA...")
        print("      AWS_SECRET_ACCESS_KEY=...")
        return False

    print(f"    {OK} authenticated as {identity['Arn']}")
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
    if any(MODEL_ID in i or i.startswith(MODEL_ID) for i in ids):
        print(f"    {OK} {MODEL_ID} is offered in {REGION}")
        return True

    print(f"    {BAD} {MODEL_ID} not offered in {REGION}")
    claude = sorted(i for i in ids if "claude" in i.lower())
    if claude:
        print(f"{DIM}    Claude models available here:{RESET}")
        for i in claude[:12]:
            print(f"      {i}")
    else:
        print(f"{DIM}    No Claude models in this region. Try us-east-1"
              f" or us-west-2.{RESET}")
    return False


def check_round_trip() -> bool:
    step(4, "Live model call")
    try:
        from anthropic import AnthropicBedrockMantle
    except ImportError:
        print(f"    {BAD} anthropic SDK not installed")
        return False

    try:
        client = AnthropicBedrockMantle(aws_region=REGION)
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
        if "accessdenied" in msg or "not authorized" in msg:
            print(f"\n{DIM}    Enable model access: AWS console → Bedrock →")
            print(f"    Model access → Manage → tick Claude → Save.")
            print(f"    Also ensure the IAM user has bedrock:InvokeModel.{RESET}")
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
