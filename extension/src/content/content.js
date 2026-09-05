/**
 * Injects the Sentinel badge into a Shopee product page.
 *
 * The badge lives in a shadow root so Shopee's stylesheet cannot bleed into it
 * (and ours cannot leak out). The whole thing re-runs on client-side
 * navigation: Shopee routes with pushState, which does not re-inject content
 * scripts, so without a watcher the badge would stick on the first product you
 * viewed and silently go stale.
 */
(function () {
  const { extract, presentation } = self.Sentinel;

  const HOST_ID = "sentinel-badge-host";
  let currentHref = null;
  let currentToken = 0;

  // --- Badge UI -------------------------------------------------------------

  function removeBadge() {
    document.getElementById(HOST_ID)?.remove();
  }

  function createHost() {
    removeBadge();
    const host = document.createElement("div");
    host.id = HOST_ID;
    host.style.cssText =
      "position:fixed;right:20px;bottom:20px;z-index:2147483647;";
    document.body.appendChild(host);
    return host.attachShadow({ mode: "open" });
  }

  function styles() {
    return `
      :host, * { box-sizing: border-box; }
      .wrap {
        font: 13px/1.45 -apple-system, "Segoe UI", Roboto, sans-serif;
        width: 300px;
        border-radius: 12px;
        background: #fff;
        box-shadow: 0 8px 28px rgba(0,0,0,.18), 0 0 0 1px rgba(0,0,0,.06);
        overflow: hidden;
      }
      .pill {
        display: flex; align-items: center; gap: 10px;
        padding: 12px 14px; cursor: pointer; user-select: none;
      }
      .dot {
        width: 30px; height: 30px; border-radius: 50%;
        display: grid; place-items: center;
        font-weight: 700; font-size: 15px; color: #fff; flex: none;
      }
      .headline { flex: 1; min-width: 0; }
      .score { font-weight: 700; font-size: 15px; color: #0f172a; }
      .label {
        font-size: 11px; color: #64748b;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
      }
      .chev { color: #94a3b8; font-size: 11px; flex: none; }
      .drawer { display: none; border-top: 1px solid #e2e8f0; padding: 12px 14px; }
      .drawer.open { display: block; }
      .bar-row { margin-bottom: 10px; }
      .bar-top {
        display: flex; justify-content: space-between;
        font-size: 11px; color: #475569; margin-bottom: 4px;
      }
      .track { height: 6px; border-radius: 3px; background: #e2e8f0; overflow: hidden; }
      .fill { height: 100%; border-radius: 3px; transition: width .3s ease; }
      h4 {
        margin: 12px 0 6px; font-size: 11px; text-transform: uppercase;
        letter-spacing: .04em; color: #64748b;
      }
      ul { margin: 0; padding-left: 16px; color: #334155; }
      li { margin-bottom: 4px; }
      .muted { color: #64748b; font-size: 11px; margin-top: 10px; }
      .size {
        margin: 12px 0 4px; padding: 10px; border-radius: 8px; background: #f8fafc;
      }
      .size-cmp {
        display: flex; align-items: baseline; gap: 8px; margin-bottom: 6px;
      }
      .size-cmp b { font-size: 15px; color: #0f172a; }
      .size-cmp s { color: #94a3b8; }
      .size-note { font-size: 11px; color: #475569; }
      .size-ref { font-size: 10px; color: #94a3b8; margin-top: 5px; }
      .spinner {
        width: 16px; height: 16px; border-radius: 50%;
        border: 2px solid #cbd5e1; border-top-color: #475569;
        animation: spin .8s linear infinite;
      }
      @keyframes spin { to { transform: rotate(360deg); } }
    `;
  }

  function bar(name, value, color) {
    return `
      <div class="bar-row">
        <div class="bar-top"><span>${name}</span><span>${value}</span></div>
        <div class="track"><div class="fill" style="width:${value}%;background:${color}"></div></div>
      </div>`;
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  function renderLoading(shadow) {
    shadow.innerHTML = `
      <style>${styles()}</style>
      <div class="wrap"><div class="pill">
        <div class="spinner"></div>
        <div class="headline">
          <div class="score">Checking listing…</div>
          <div class="label">Sentinel is analysing this product</div>
        </div>
      </div></div>`;
  }

  function renderError(shadow, message) {
    const p = presentation("UNAVAILABLE");
    shadow.innerHTML = `
      <style>${styles()}</style>
      <div class="wrap"><div class="pill">
        <div class="dot" style="background:${p.color}">${p.icon}</div>
        <div class="headline">
          <div class="score">${p.short}</div>
          <div class="label">${escapeHtml(message)}</div>
        </div>
      </div></div>`;
  }

  /**
   * Size comparison panel. Shown only when scale was actually determinable —
   * a missing estimate is reported as unknown rather than dressed up as a
   * measurement, since size cannot be recovered from a photo without a
   * reference object in frame.
   */
  function renderSize(result) {
    const sa = result.scaleAnalysis;
    if (!sa) return "";

    const fmt = (cm) => (cm == null ? null : `${(+cm).toFixed(0)} cm`);
    const apparent = fmt(sa.apparentLongestCm);
    const expected = fmt(sa.expectedLongestCm);
    const listed = fmt(result.listedLongestCm);

    if (sa.scaleConfidence === "NONE" || !apparent) {
      return `
        <div class="size">
          <div class="size-note"><b>Size could not be verified.</b>
          ${escapeHtml(sa.explanation || "")}</div>
        </div>`;
    }

    const claim = listed || expected;
    return `
      <div class="size">
        <div class="size-cmp">
          ${claim ? `<s>${claim}</s>` : ""}
          <b>${apparent}</b>
          <span class="size-note">${
            sa.mismatchDetected ? "actual size in photos" : "confirmed in photos"
          }</span>
        </div>
        <div class="size-note">${escapeHtml(sa.explanation || "")}</div>
        ${
          sa.scaleReference
            ? `<div class="size-ref">Measured against: ${escapeHtml(
                sa.scaleReference
              )} · confidence ${escapeHtml(sa.scaleConfidence)}</div>`
            : ""
        }
      </div>`;
  }

  function renderResult(shadow, result) {
    const p = presentation(result.riskLevel);
    const s = result.subScores || {};
    const findings = (result.findings || [])
      .map((f) => `<li>${escapeHtml(f)}</li>`)
      .join("");
    const discrepancies = (result.specDiscrepancies || [])
      .map((d) => `<li>${escapeHtml(d)}</li>`)
      .join("");

    shadow.innerHTML = `
      <style>${styles()}</style>
      <div class="wrap">
        <div class="pill" id="pill">
          <div class="dot" style="background:${p.color}">${p.icon}</div>
          <div class="headline">
            <div class="score">Trust score ${result.overallTrustScore}/100</div>
            <div class="label">${p.label}</div>
          </div>
          <div class="chev" id="chev">▼</div>
        </div>
        <div class="drawer" id="drawer">
          ${bar("Visual integrity", s.visualIntegrity ?? 0, p.color)}
          ${bar("Spec consistency", s.specConsistency ?? 0, p.color)}
          ${bar("Price sanity", s.priceSanity ?? 0, p.color)}
          ${bar("Scale fidelity", s.scaleFidelity ?? 0, p.color)}
          ${renderSize(result)}
          ${findings ? `<h4>Findings</h4><ul>${findings}</ul>` : ""}
          ${discrepancies ? `<h4>Spec discrepancies</h4><ul>${discrepancies}</ul>` : ""}
          <div class="muted">
            ${result.imageAnalysis?.isAiGenerated ? "⚠ Images show signs of AI generation. " : ""}
            ${result.cached ? "Cached result." : "Freshly analysed."}
          </div>
        </div>
      </div>`;

    const drawer = shadow.getElementById("drawer");
    const chev = shadow.getElementById("chev");
    shadow.getElementById("pill").addEventListener("click", () => {
      const open = drawer.classList.toggle("open");
      chev.textContent = open ? "▲" : "▼";
    });
  }

  // --- Flow -----------------------------------------------------------------

  async function run() {
    const token = ++currentToken;
    const ids = extract.parseProductUrl();
    if (!ids) {
      removeBadge();
      return;
    }

    const shadow = createHost();
    renderLoading(shadow);

    const listing = await extract.extractListing();
    if (token !== currentToken) return; // navigated away mid-flight

    if (!listing) {
      renderError(shadow, "Could not read this listing's details");
      return;
    }

    chrome.runtime.sendMessage({ type: "SENTINEL_ANALYZE", listing }, (reply) => {
      if (token !== currentToken) return;
      if (chrome.runtime.lastError || !reply) {
        renderError(shadow, "Sentinel background service is unavailable");
        return;
      }
      if (!reply.ok) {
        renderError(shadow, reply.error || "Analysis unavailable");
        return;
      }
      renderResult(shadow, reply.result);
    });
  }

  function onNavigation() {
    if (location.href === currentHref) return;
    currentHref = location.href;
    run();
  }

  // Cover both history API navigation and DOM-driven route changes.
  for (const method of ["pushState", "replaceState"]) {
    const original = history[method];
    history[method] = function (...args) {
      const result = original.apply(this, args);
      queueMicrotask(onNavigation);
      return result;
    };
  }
  window.addEventListener("popstate", onNavigation);
  setInterval(onNavigation, 1000); // belt-and-braces for framework routers

  onNavigation();
})();
