"""Start the Sentinel API locally.

    python scripts/run_local.py

Defaults to mock mode, so it needs no AWS account and no credentials.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("MOCK_AWS", "true")

import uvicorn  # noqa: E402


def main() -> None:
    mock = os.environ["MOCK_AWS"].lower() in {"1", "true", "yes"}
    print(f"Sentinel API  ·  mock mode: {mock}")
    print("  http://localhost:8000/health")
    print("  http://localhost:8000/docs\n")
    if not mock:
        print("MOCK_AWS is false — real Bedrock and DynamoDB calls will be made.\n")

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
