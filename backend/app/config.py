"""Runtime configuration, read once from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load the repo-root .env if present. Lambda supplies real env vars instead.
#
# Tests set SENTINEL_SKIP_DOTENV=1: without it, whatever a developer happens to
# have in their local .env silently changes test outcomes, so the suite would
# pass on one machine and fail on another for reasons nobody can see.
if os.getenv("SENTINEL_SKIP_DOTENV") != "1":
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Two independent switches, with MOCK_AWS as the master default.

    They are separate because the useful middle state is real Bedrock analysis
    with a local in-memory cache: you can have working AI long before the
    DynamoDB table is deployed, and pointing at a table that does not exist
    just fills the logs with errors.
    """

    mock_aws: bool = field(default_factory=lambda: _bool("MOCK_AWS", True))

    # Region matters: Bedrock model availability differs by region.
    aws_region: str = field(default_factory=lambda: os.getenv("AWS_REGION", "us-east-1"))
    model_id: str = field(
        default_factory=lambda: os.getenv(
            "BEDROCK_MODEL_ID", "us.anthropic.claude-opus-4-6-v1"
        )
    )

    # Which Bedrock API to talk to.
    #   "runtime" - bedrock-runtime InvokeModel, model ids like
    #               "us.anthropic.claude-opus-4-6-v1"
    #   "mantle"  - the newer Messages-API endpoint, ids like
    #               "anthropic.claude-opus-5"
    # Mantle is the modern default, but restricted accounts (managed AWS
    # Organizations, hackathon and student orgs) commonly carry a service
    # control policy denying bedrock-mantle:* outright, so "runtime" is the
    # default here because it works in strictly more environments.
    bedrock_api: str = field(
        default_factory=lambda: os.getenv("BEDROCK_API", "runtime").strip().lower()
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

    # Thinking depth, and the main latency lever: a full analysis measured
    # ~36s at "high" with 7 images. Drop to "medium" or "low" if a live demo
    # needs to feel quicker; raise to "max" when accuracy matters more.
    effort: str = field(
        default_factory=lambda: os.getenv("BEDROCK_EFFORT", "high").strip().lower()
    )
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    @property
    def cache_ttl_seconds(self) -> int:
        return self.cache_ttl_hours * 3600

    @property
    def mock_bedrock(self) -> bool:
        """Return canned verdicts instead of calling the model."""
        return _bool("MOCK_BEDROCK", self.mock_aws)

    @property
    def use_dynamodb(self) -> bool:
        """Use DynamoDB rather than the in-memory cache.

        Defaults to off even when MOCK_AWS is false, because the table only
        exists once the CDK stack is deployed. Turn it on deliberately.
        """
        return _bool("USE_DYNAMODB", False)


settings = Settings()
