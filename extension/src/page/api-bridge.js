/**
 * Runs in the PAGE's own JavaScript context (manifest `world: "MAIN"`), and
 * exists for one reason: to make Shopee's API calls look like Shopee's own.
 *
 * A fetch issued from a content script is attributed to the extension, not the
 * page. Shopee's v4 API rejects that with a bare HTTP 403 — which is what was
 * silently costing us every review on every listing. The same request made
 * from page context is an ordinary same-origin call and succeeds.
 *
 * The isolated content script cannot call into here directly (separate JS
 * worlds share only the DOM), so requests and responses go over
 * window.postMessage. Only same-window messages carrying our marker are
 * honoured, and only URLs on Shopee's own origin are fetched — this must never
 * become a general-purpose proxy that the page can drive.
 */
(function () {
  const CHANNEL = "__sentinel_api__";

  window.addEventListener("message", async (event) => {
    // Same-window only: reject anything posted by an iframe or another origin.
    if (event.source !== window) return;

    const msg = event.data;
    if (!msg || msg.channel !== CHANNEL || msg.kind !== "request") return;

    const reply = (payload) =>
      window.postMessage(
        { channel: CHANNEL, kind: "response", id: msg.id, ...payload },
        window.location.origin
      );

    // Never fetch anything off Shopee's own origin.
    let target;
    try {
      target = new URL(msg.url, window.location.origin);
    } catch {
      return reply({ ok: false, error: "invalid URL" });
    }
    if (target.origin !== window.location.origin) {
      return reply({ ok: false, error: "cross-origin request refused" });
    }

    try {
      const response = await fetch(target.href, {
        credentials: "include",
        headers: {
          "x-api-source": "pc",
          "x-requested-with": "XMLHttpRequest",
          accept: "application/json",
        },
      });
      const body = await response.text();
      reply({ ok: response.ok, status: response.status, body });
    } catch (err) {
      reply({ ok: false, error: String(err && err.message ? err.message : err) });
    }
  });

  // Announce readiness through the DOM, not postMessage.
  //
  // This script runs at document_start and the content script at
  // document_idle, so a "ready" message would be posted long before anything
  // is listening for it. The two JavaScript worlds share the DOM, so a marker
  // attribute is readable whenever the content script gets around to looking.
  document.documentElement.setAttribute("data-sentinel-bridge", "1");
})();
