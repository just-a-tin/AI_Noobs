"""Runtime configuration, read once from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load the repo-root .env if present. Lambda supplies real env vars instead.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    mock_aws: bool = field(default_factory=lambda: _bool("MOCK_AWS", True))
    aws_region: str = field(default_factory=lambda: os.getenv("AWS_REGION", "us-east-1"))
    model_id: str = field(
        default_factory=lambda: os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-opus-5")
    )
    table_name: str = field(
        default_factory=lambda: os.getenv("DDB_TABLE_NAME", "SentinelAnalysisCache")
    )
    cache_ttl_hours: int = field(
        default_factory=lambda: int(os.getenv("CACHE_TTL_HOURS", "24"))
    )
    cache_price_tolerance: float = field(
        default_factory=lambda: float(os.getenv("CACHE_PRICE_TOLERANCE", "0.02"))
    )
    max_images: int = field(default_factory=lambda: int(os.getenv("MAX_IMAGES", "8")))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    @property
    def cache_ttl_seconds(self) -> int:
        return self.cache_ttl_hours * 3600


settings = Settings()
