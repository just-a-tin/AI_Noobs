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
  const { config, extract, presentation } = self.Sentinel;

  const HOST_ID = "sentinel-badge-host";
  let currentHref = null;
  let currentToken = 0;
  let navTimer = null;
  // Held module-wide so teardown can stop a ticker started in run().
  let stopLoadingTicker = null;

  // --- Badge UI -------------------------------------------------------------

  function removeBadge() {
    // Stop any running loading ticker first, or it repaints into a detached
    // shadow root once a second for the life of the page.
    stopLoadingTicker?.();
    stopLoadingTicker = null;
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
      .refs { margin-top: 8px; padding-top: 8px; border-top: 1px solid #e2e8f0; }
      .refs.conflict { border-top-color: #fca5a5; }
      .ref-head {
        font-size: 10px; text-transform: uppercase; letter-spacing: .04em;
        color: #64748b; margin-bottom: 5px;
      }
      .refs.conflict .ref-head { color: #b91c1c; }
      .ref-row {
        display: flex; justify-content: space-between; gap: 8px;
        font-size: 11px; color: #475569; padding: 2px 0;
      }
      .ref-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .ref-implies { color: #0f172a; font-weight: 600; flex: none; }
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

  /**
   * Loading state with an elapsed counter.
   *
   * Real analysis takes 30-60s: several images are fetched, downscaled and
   * reasoned over. A motionless spinner for that long reads as broken, and
   * the user reloads and blames the extension.
   *
   * Returns a stop function; callers must invoke it before rendering.
   */
  function renderLoading(shadow) {
    const started = Date.now();

    const paint = () => {
      const elapsed = Date.now() - started;
      const secs = Math.floor(elapsed / 1000);
      const note =
        elapsed < config.showElapsedAfterMs
          ? "Sentinel is analysing this product"
          : `Inspecting images — ${secs}s (this can take up to a minute)`;

      shadow.innerHTML = `
        <style>${styles()}</style>
        <div class="wrap"><div class="pill">
          <div class="spinner"></div>
          <div class="headline">
            <div class="score">Checking listing…</div>
            <div class="label">${note}</div>
          </div>
        </div></div>`;
    };

    paint();
    const ticker = setInterval(paint, 1000);
    const stop = () => clearInterval(ticker);
    stopLoadingTicker = stop;
    return stop;
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

    const refs = sa.sceneReferences || [];
    const conflict = sa.referenceAgreement === "CONFLICT";

    // Show what each object in the scene independently implies. When they
    // disagree, that disagreement is the finding — a single real photograph
    // cannot produce contradictory scales.
    const refRows = refs
      .map(
        (r) => `
        <div class="ref-row">
          <span class="ref-name">${escapeHtml(r.objectName)}</span>
          <span class="ref-implies">→ ${(+r.impliedProductCm).toFixed(0)} cm</span>
        </div>`
      )
      .join("");

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
          refs.length
            ? `<div class="refs ${conflict ? "conflict" : ""}">
                 <div class="ref-head">${
                   conflict
                     ? "⚠ Objects in frame contradict each other"
                     : "Measured against"
                 }</div>
                 ${refRows}
               </div>`
            : ""
        }
        <div class="size-ref">Confidence ${escapeHtml(sa.scaleConfidence)}</div>
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

  /**
   * Is this script still attached to a live extension?
   *
   * Reloading the extension orphans the content scripts already injected into
   * open tabs: `chrome.runtime` survives as an object but its id is gone, and
   * every call throws "Extension context invalidated". Without this check the
   * navigation timer below keeps firing forever in every open Shopee tab,
   * throwing once a second — noisy exactly during development, when the
   * extension is reloaded most.
   */
  function contextAlive() {
    try {
      return Boolean(chrome.runtime?.id);
    } catch {
      return false;
    }
  }

  /** Stop cleanly once orphaned; a page refresh loads the new version. */
  function shutdown() {
    clearInterval(navTimer);
    window.removeEventListener("popstate", onNavigation);
    removeBadge();
  }

  async function run() {
    const token = ++currentToken;
    const ids = extract.parseProductUrl();
    if (!ids) {
      removeBadge();
      return;
    }

    const shadow = createHost();
    // The loading ticker repaints once a second, so it MUST be stopped before
    // anything else renders or it will overwrite the result a moment later.
    const stopLoading = renderLoading(shadow);

    const fail = (message) => {
      stopLoading();
      renderError(shadow, message);
    };

    const listing = await extract.extractListing();
    if (token !== currentToken) return stopLoading(); // navigated away mid-flight

    if (!listing) {
      // The console line names the missing field; point at it rather than
      // leaving a dead end.
      return fail("Couldn't read this listing — see console for details");
    }

    if (!contextAlive()) {
      fail("Sentinel was updated — refresh this page");
      return shutdown();
    }

    try {
      chrome.runtime.sendMessage({ type: "SENTINEL_ANALYZE", listing }, (reply) => {
        if (token !== currentToken) return stopLoading();
        if (chrome.runtime.lastError || !reply) {
          return fail("Sentinel background service is unavailable");
        }
        if (!reply.ok) {
          return fail(reply.error || "Analysis unavailable");
        }
        stopLoading();
        renderResult(shadow, reply.result);
      });
    } catch (err) {
      // The extension was reloaded between the check above and this call.
      console.warn("[Sentinel] messaging failed:", String(err));
      fail("Sentinel was updated — refresh this page");
      shutdown();
    }
  }

  function onNavigation() {
    if (!contextAlive()) return shutdown();
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
  // Belt-and-braces for framework routers that bypass the history API.
  navTimer = setInterval(onNavigation, 1000);

  onNavigation();
})();
