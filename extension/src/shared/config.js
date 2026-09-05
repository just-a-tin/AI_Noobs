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

    /** Shopee stores image hashes; the CDN URL is built from them. */
    imageCdnBase: "https://down-sg.img.susercontent.com/file/",

    maxGalleryImages: 6,
    maxReviewImages: 5,

    /** Shopee's v4 API returns prices scaled by 100_000. */
    priceScale: 100000,

    requestTimeoutMs: 30000,
  };
})(typeof self !== "undefined" ? self : globalThis);
