import os
import sys
from pathlib import Path

# Ignore the developer's local .env. Without this, whoever has real AWS
# credentials configured gets different test results from everyone else.
os.environ["SENTINEL_SKIP_DOTENV"] = "1"

# Force mock mode before app modules read settings at import time.
os.environ.setdefault("MOCK_AWS", "true")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
