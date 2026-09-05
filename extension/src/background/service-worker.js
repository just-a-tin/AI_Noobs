/**
 * Background service worker: the only place that talks to the Sentinel API.
 *
 * Routing backend calls through here rather than the content script matters:
 * a fetch issued from page context is subject to Shopee's Content-Security-
 * Policy and gets blocked with no useful error. The worker runs under the
 * extension's own origin with host_permissions, so it is unaffected.
 */

importScripts("../shared/config.js", "../shared/mock-verdicts.js");

const { config, mockVerdict } = self.Sentinel;

/** Per-tab verdicts so the popup can show what the badge is showing. */
async function remember(tabId, itemId, payload) {
  await chrome.storage.session.set({
    [`tab:${tabId}`]: { itemId, ...payload, at: Date.now() },
  });
}

async function callApi(listing) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), config.requestTimeoutMs);

  try {
    const response = await fetch(config.apiUrl + config.analyzePath, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        platform: listing.platform,
        itemId: listing.itemId,
        shopId: listing.shopId,
        title: listing.title,
        price: listing.price,
        originalPrice: listing.originalPrice,
        sellerRating: listing.sellerRating,
        shopLocation: listing.shopLocation,
        specs: listing.specs,
        imageUrls: listing.imageUrls,
        reviewImageUrls: listing.reviewImageUrls,
      }),
      signal: controller.signal,
    });

    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      throw new Error(`API ${response.status}${detail ? `: ${detail.slice(0, 120)}` : ""}`);
    }
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

function badgeFor(result) {
  if (!result) return { text: "?", color: "#475569" };
  const colors = { LOW: "#15803d", MEDIUM: "#a16207", HIGH: "#b91c1c" };
  return {
    text: String(result.overallTrustScore),
    color: colors[result.riskLevel] || "#475569",
  };
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type !== "SENTINEL_ANALYZE") return false;

  const tabId = sender.tab?.id;
  const { listing } = message;

  (async () => {
    try {
      const result = config.uiMockMode
        ? mockVerdict(listing)
        : await callApi(listing);

      if (tabId != null) {
        await remember(tabId, listing.itemId, { ok: true, result, listing });
        const { text, color } = badgeFor(result);
        chrome.action.setBadgeText({ tabId, text });
        chrome.action.setBadgeBackgroundColor({ tabId, color });
      }
      sendResponse({ ok: true, result });
    } catch (err) {
      const error = String(err?.message || err);
      console.warn("[Sentinel] analysis failed:", error);
      if (tabId != null) {
        await remember(tabId, listing.itemId, { ok: false, error, listing });
        chrome.action.setBadgeText({ tabId, text: "!" });
        chrome.action.setBadgeBackgroundColor({ tabId, color: "#475569" });
      }
      // Surfaced as an explicit failure, never a neutral-looking score: a
      // trust product must not imply "fine" when it means "unknown".
      sendResponse({ ok: false, error });
    }
  })();

  return true; // async sendResponse
});

chrome.tabs.onRemoved.addListener((tabId) => {
  chrome.storage.session.remove(`tab:${tabId}`);
});
