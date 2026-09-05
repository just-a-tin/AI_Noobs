"""Fetch listing images and turn them into Bedrock image blocks.

Bedrock needs image *bytes*: URL image sources are a first-party Messages API
feature and are not available on the Bedrock path. So we fetch, downscale and
base64-encode here.

Downscaling to a 1568px long edge is not arbitrary — Claude downsamples above
that internally, so sending larger images buys nothing and costs tokens and
latency.
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
from dataclasses import dataclass

import httpx
from PIL import Image

log = logging.getLogger(__name__)

MAX_EDGE_PX = 1568
JPEG_QUALITY = 82
PER_IMAGE_TIMEOUT = 8.0
MAX_ENCODED_BYTES = 4_500_000  # Bedrock caps at 5MB/image; leave headroom.

# Shopee's CDN is unhappy with obviously non-browser clients.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Referer": "https://shopee.sg/",
    "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
}


@dataclass
class PreparedImage:
    url: str
    kind: str  # "gallery" | "review"
    block: dict


def _to_jpeg_b64(raw: bytes) -> str | None:
    """Normalise arbitrary image bytes to a bounded JPEG, base64-encoded."""
    try:
        with Image.open(io.BytesIO(raw)) as img:
            img = img.convert("RGB")
            img.thumbnail((MAX_EDGE_PX, MAX_EDGE_PX), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    except Exception:
        log.warning("could not decode image", exc_info=True)
        return None

    data = buf.getvalue()
    if len(data) > MAX_ENCODED_BYTES:
        log.warning("image still %d bytes after downscale; skipping", len(data))
        return None
    return base64.standard_b64encode(data).decode("ascii")


async def _fetch_one(
    client: httpx.AsyncClient, url: str, kind: str
) -> PreparedImage | None:
    try:
        resp = await client.get(url, timeout=PER_IMAGE_TIMEOUT)
        resp.raise_for_status()
    except Exception:
        # One bad image must not sink the whole analysis.
        log.warning("image fetch failed: %s", url, exc_info=True)
        return None

    encoded = await asyncio.to_thread(_to_jpeg_b64, resp.content)
    if encoded is None:
        return None

    return PreparedImage(
        url=url,
        kind=kind,
        block={
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": encoded,
            },
        },
    )


async def prepare_images(
    gallery_urls: list[str],
    review_urls: list[str],
    max_images: int,
) -> list[PreparedImage]:
    """Fetch gallery and review images concurrently, preserving order.

    Budget is split so review images are always represented: they are the
    single strongest bait-and-switch signal, and dropping them in favour of a
    long gallery would blind the comparison the model is asked to make.
    """
    review_budget = min(len(review_urls), max(1, max_images // 2)) if review_urls else 0
    gallery_budget = max_images - review_budget

    targets = [(u, "gallery") for u in gallery_urls[:gallery_budget]]
    targets += [(u, "review") for u in review_urls[:review_budget]]

    if not targets:
        return []

    async with httpx.AsyncClient(headers=_HEADERS, follow_redirects=True) as client:
        results = await asyncio.gather(
            *(_fetch_one(client, url, kind) for url, kind in targets)
        )

    prepared = [r for r in results if r is not None]
    log.info("prepared %d/%d images", len(prepared), len(targets))
    return prepared
