import os
import sys
from pathlib import Path

# Force mock mode before app modules read settings at import time.
os.environ.setdefault("MOCK_AWS", "true")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
