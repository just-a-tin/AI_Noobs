/**
 * Runs in the PAGE's own JavaScript context (manifest `world: "MAIN"`), and
 * exists for one reason: to make Shopee's API calls look like Shopee's own.
 *
 * A fetch issued from a content script is attributed to the extension, not the
 * page. Shopee's v4 API rejects that with a bare HTTP 403 — which was silently
 * costing us every review on every listing. The same request made from page
 * context is an ordinary same-origin call and succeeds.
 *
 * Communication uses CustomEvents on `document`, NOT window.postMessage.
 * postMessage broadcasts to every message listener on the page, so a large
 * API response (a page of reviews is easily 100KB of JSON) would be delivered
 * into Shopee's own application code as well as ours. CustomEvents on private
 * event names reach only the listener we installed.
 *
 * Only URLs on Shopee's own origin are fetched — this must never become a
 * general-purpose proxy the page can drive.
 */
(function () {
  const REQUEST = "sentinel:api-request";
  const RESPONSE = "sentinel:api-response";

  // detail is JSON text, not an object: structured data handed across the
  // world boundary is subject to cloning rules that differ between browsers,
  // and a string is unambiguous.
  document.addEventListener(REQUEST, async (event) => {
    let request;
    try {
      request = JSON.parse(event.detail);
    } catch {
      return;
    }
    if (!request || !request.id || !request.url) return;

    const reply = (payload) =>
      document.dispatchEvent(
        new CustomEvent(RESPONSE, {
          detail: JSON.stringify({ id: request.id, ...payload }),
        })
      );

    let target;
    try {
      target = new URL(request.url, window.location.origin);
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

  // Announce readiness through the DOM rather than an event: this script runs
  // at document_start and the content script at document_idle, so any event
  // would fire long before anything was listening. The DOM is the one thing
  // the two JavaScript worlds share.
  document.documentElement.setAttribute("data-sentinel-bridge", "1");
})();
