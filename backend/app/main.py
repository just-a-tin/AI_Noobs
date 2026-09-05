"""Sentinel API."""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .bedrock import analyzer
from .cache import build_cache
from .config import settings
from .schemas import AnalysisResult, AnalyzeRequest
from .scoring import RISK_PRESENTATION, derive_risk_level

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("sentinel")

app = FastAPI(
    title="Sentinel API",
    version="0.1.0",
    description="Scam-risk analysis for Shopee SG (and Lazada / Amazon SG) listings.",
)

# The extension calls from a chrome-extension:// origin. Chrome sends
# `Origin: chrome-extension://<id>`; the id is only known after packing, so
# allow the scheme by regex rather than pinning an id we do not have yet.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^chrome-extension://.*$|^http://localhost(:\d+)?$|^null$",
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

cache = build_cache()


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "mockMode": settings.mock_aws,
        "model": settings.model_id if not settings.mock_aws else "mock",
    }


@app.get("/api/v1/presentation")
def presentation() -> dict:
    """Badge colours and labels, so the extension and backend agree on them."""
    return {level.value: meta for level, meta in RISK_PRESENTATION.items()}


@app.post("/api/v1/analyze", response_model=AnalysisResult)
async def analyze(request: AnalyzeRequest) -> AnalysisResult:
    started = time.perf_counter()

    cached = cache.get(request)
    if cached is not None:
        log.info("cache hit for %s", request.cache_key())
        return cached

    try:
        core = await analyzer.analyze(request)
    except Exception as exc:
        log.exception("analysis failed for %s", request.cache_key())
        # Deliberately not a fabricated neutral score: the extension must be
        # able to tell "we could not verify this" from "this looks fine".
        raise HTTPException(status_code=502, detail=f"Analysis failed: {exc}") from exc

    result = AnalysisResult(
        **core.model_dump(),
        riskLevel=derive_risk_level(core.overallTrustScore),
        cached=False,
        modelId="mock" if settings.mock_aws else settings.model_id,
        analyzedAt=int(time.time()),
    )

    cache.put(request, result)
    log.info(
        "analyzed %s score=%d risk=%s in %.0fms",
        request.cache_key(),
        result.overallTrustScore,
        result.riskLevel.value,
        (time.perf_counter() - started) * 1000,
    )
    return result
