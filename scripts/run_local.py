"""Start the Sentinel API locally.

    python scripts/run_local.py            # honours .env
    python scripts/run_local.py --mock     # force canned verdicts

With no .env and no flags this runs in mock mode, so it needs no AWS account
and no credentials.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv  # noqa: E402

# Load .env BEFORE touching os.environ.
#
# This used to be `os.environ.setdefault("MOCK_AWS", "true")`, which ran first
# and therefore always won: load_dotenv does not override variables that are
# already set, so .env could never turn mock mode off. The server reported
# canned verdicts while .env plainly said MOCK_AWS=false, and nothing in the
# output said why.
load_dotenv(ROOT / ".env")

if "--mock" in sys.argv:
    os.environ["MOCK_BEDROCK"] = "true"

from app.config import settings  # noqa: E402

import uvicorn  # noqa: E402


def main() -> None:
    # Print what was actually resolved, not what was intended. A server whose
    # mode disagrees with its .env should be obvious from the first line of
    # output rather than from the content of a verdict.
    print("Sentinel API")
    print(f"  analysis : {'MOCK (canned verdicts)' if settings.mock_bedrock else 'REAL Bedrock'}")
    if not settings.mock_bedrock:
        print(f"  model    : {settings.model_id}")
        print(f"  api      : {settings.bedrock_api}  ({settings.aws_region})")
    print(f"  cache    : {'DynamoDB' if settings.use_dynamodb else 'in-memory'}")
    print("  http://localhost:8000/health")
    print("  http://localhost:8000/docs")

    if not settings.mock_bedrock:
        print("\n  Real model calls cost money per listing.")
    print()

    # Watch only our own source. Without reload_dirs, uvicorn watches the whole
    # project including backend/.venv, and restarts on library files that never
    # change — the server ends up thrashing instead of serving.
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_dirs=[str(ROOT / "backend" / "app")],
    )


if __name__ == "__main__":
    main()
