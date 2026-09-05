"""Analysis cache: in-memory when mocking, DynamoDB in production.

Beyond the 24h TTL, an entry is invalidated when the listing's price moves
materially or its title/specs change. That matters for this product
specifically: a bait-and-switch listing mutates after it accumulates reviews,
and serving a stale "safe" verdict across that change is the exact failure
Sentinel exists to prevent.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Protocol

from .config import settings
from .schemas import AnalysisResult, AnalyzeRequest

log = logging.getLogger(__name__)


def _price_moved(cached_price: float, current_price: float, tolerance: float) -> bool:
    if cached_price <= 0:
        return current_price > 0
    return abs(current_price - cached_price) / cached_price > tolerance


class AnalysisCache(Protocol):
    def get(self, request: AnalyzeRequest) -> AnalysisResult | None: ...
    def put(self, request: AnalyzeRequest, result: AnalysisResult) -> None: ...


class _BaseCache:
    """Shared freshness rules; subclasses only supply raw storage."""

    def _read(self, key: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def _write(self, key: str, item: dict[str, Any]) -> None:
        raise NotImplementedError

    def get(self, request: AnalyzeRequest) -> AnalysisResult | None:
        item = self._read(request.cache_key())
        if item is None:
            return None

        now = int(time.time())
        if int(item.get("expiresAt", 0)) <= now:
            log.info("cache expired for %s", request.cache_key())
            return None

        if _price_moved(
            float(item.get("price", 0)), request.price, settings.cache_price_tolerance
        ):
            log.info("cache invalidated by price change for %s", request.cache_key())
            return None

        if item.get("specsHash") != request.specs_hash():
            log.info("cache invalidated by spec change for %s", request.cache_key())
            return None

        result = AnalysisResult.model_validate(item["result"])
        result.cached = True
        return result

    def put(self, request: AnalyzeRequest, result: AnalysisResult) -> None:
        now = int(time.time())
        self._write(
            request.cache_key(),
            {
                "pk": request.cache_key(),
                "expiresAt": now + settings.cache_ttl_seconds,
                "price": request.price,
                "specsHash": request.specs_hash(),
                "result": result.model_dump(mode="json"),
            },
        )


class InMemoryCache(_BaseCache):
    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    def _read(self, key: str) -> dict[str, Any] | None:
        return self._store.get(key)

    def _write(self, key: str, item: dict[str, Any]) -> None:
        self._store[key] = item

    def clear(self) -> None:
        self._store.clear()


class DynamoDBCache(_BaseCache):
    def __init__(self, table_name: str, region: str) -> None:
        import boto3  # imported lazily so mock mode needs no AWS SDK config

        self._table = boto3.resource("dynamodb", region_name=region).Table(table_name)

    def _read(self, key: str) -> dict[str, Any] | None:
        try:
            return self._table.get_item(Key={"pk": key}).get("Item")
        except Exception:
            # A cache read failure must degrade to a miss, never a 500.
            log.exception("DynamoDB read failed for %s", key)
            return None

    def _write(self, key: str, item: dict[str, Any]) -> None:
        try:
            # DynamoDB rejects float; Decimal via JSON round-trip is simplest.
            import json
            from decimal import Decimal

            self._table.put_item(
                Item=json.loads(json.dumps(item), parse_float=Decimal)
            )
        except Exception:
            log.exception("DynamoDB write failed for %s", key)


def build_cache() -> AnalysisCache:
    if not settings.use_dynamodb:
        log.info("cache: in-memory (set USE_DYNAMODB=true once the table exists)")
        return InMemoryCache()
    log.info("cache: DynamoDB table %s", settings.table_name)
    return DynamoDBCache(settings.table_name, settings.aws_region)
