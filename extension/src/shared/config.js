/**
 * Shared config. Written as a classic script (no ES modules) so the same file
 * works in a content script, in the service worker via importScripts(), and in
 * the popup via a plain <script> tag — no build step required.
 */
(function (root) {
  root.Sentinel = root.Sentinel || {};

  root.Sentinel.config = {
    apiUrl: "http://localhost:8000",
    analyzePath: "/api/v1/analyze",

    /**
     * Render canned verdicts without any backend at all. Useful for demoing
     * the UI on a machine with nothing running.
     */
    uiMockMode: false,

    /** Shopee product URLs end in `-i.{shopId}.{itemId}`. */
    productUrlPattern: /-i\.(\d+)\.(\d+)/,

    pdpApiTemplate:
      "https://shopee.sg/api/v4/pdp/get_pc?item_id={itemId}&shop_id={shopId}",

    /**
     * Written reviews, with their images correctly attributed.
     *
     * Paginated: Shopee returns a page at a time, and the reviews that
     * actually say something are often not on the first page — the default
     * ordering puts plenty of empty five-star ratings up front.
     */
    ratingsApiTemplate:
      "https://shopee.sg/api/v4/item/get_ratings?filter=0&flag=1" +
      "&itemid={itemId}&shopid={shopId}&type=0&limit={limit}&offset={offset}",

    /** Shopee rejects oversized pages; 20 is comfortably within its cap. */
    ratingsPageSize: 20,

    /**
     * Pages of reviews to request. ONE by default, deliberately.
     *
     * Requesting six pages in a burst tripped Shopee's traffic verification
     * and got a real session redirected to /verify/traffic/error. A person
     * reading reviews pages through them slowly; six requests in under a
     * second does not look like a person. Twenty reviews is enough to spot a
     * complaint pattern, and the cost of being wrong here is the user's Shopee
     * account, not ours.
     */
    maxRatingPages: 1,

    /** Minimum gap between any two Shopee API calls, in milliseconds. */
    minRequestIntervalMs: 1200,

    /**
     * Analyse automatically on page load, or wait to be asked.
     *
     * Automatic analysis means every product page a user opens costs API
     * requests. Manual keeps Sentinel at one request burst per deliberate
     * click, which is far more defensible traffic.
     */
    autoAnalyse: false,

    /**
     * Review text filtering.
     *
     * Empty and one-or-two-word reviews ("ok", "good", "nice") carry almost no
     * information about whether the product is what it claims to be, and they
     * are what review farms produce in bulk. Requiring a real sentence keeps
     * the signal and cuts the token cost.
     */
    minReviewWords: 5,
    minReviewChars: 20,
    maxReviews: 15,

    /** Shopee stores image hashes; the CDN URL is built from them. */
    imageCdnBase: "https://down-sg.img.susercontent.com/file/",

    maxGalleryImages: 6,
    maxReviewImages: 5,

    /** Shopee's v4 API returns prices scaled by 100_000. */
    priceScale: 100000,

    /**
     * Real analysis is slow: measured 29-36s for 3-7 images against
     * Claude Opus 4.6 at effort=high, before Shopee's larger images and
     * variable model latency. The old 30s ceiling sat right on that boundary
     * and aborted mid-flight. Generous headroom costs nothing — a request
     * that is going to fail fails on its own.
     */
    requestTimeoutMs: 120000,

    /** Show elapsed seconds after this, so a long wait doesn't look hung. */
    showElapsedAfterMs: 4000,
  };
})(typeof self !== "undefined" ? self : globalThis);
