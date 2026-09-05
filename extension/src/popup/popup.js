/**
 * Popup: renders the verdict the content script already obtained for this tab.
 * It reads from chrome.storage.session rather than re-analysing, so opening the
 * popup never costs a second model call.
 */
(function () {
  const { presentation } = self.Sentinel;
  const root = document.getElementById("root");
  const footer = document.getElementById("footer");

  const esc = (text) => {
    const d = document.createElement("div");
    d.textContent = text ?? "";
    return d.innerHTML;
  };

  function empty(headline, detail) {
    root.innerHTML = `<div class="empty"><strong>${esc(headline)}</strong>${esc(detail)}</div>`;
  }

  function bar(name, value, color) {
    const v = Number.isFinite(value) ? value : 0;
    return `
      <div class="bar-row">
        <div class="bar-top"><span>${name}</span><b>${v}</b></div>
        <div class="track"><div class="fill" style="width:${v}%;background:${color}"></div></div>
      </div>`;
  }

  function render(entry) {
    const { result, listing } = entry;
    const p = presentation(result.riskLevel);
    const s = result.subScores || {};

    const findings = (result.findings || [])
      .map((f) => `<li>${esc(f)}</li>`)
      .join("");
    const discrepancies = (result.specDiscrepancies || [])
      .map((d) => `<li>${esc(d)}</li>`)
      .join("");

    root.innerHTML = `
      <div class="hero" style="background:${p.surface};color:${p.color}">
        <div class="dot" style="background:${p.color}">${p.icon}</div>
        <div>
          <div class="score">${result.overallTrustScore}<span style="font-size:12px;font-weight:500">/100</span></div>
          <div class="label">${esc(p.label)}</div>
        </div>
      </div>

      ${listing?.title ? `<div class="listing">${esc(listing.title)}</div>` : ""}

      <h4>Diagnostic breakdown</h4>
      ${bar("Visual integrity", s.visualIntegrity, p.color)}
      ${bar("Spec consistency", s.specConsistency, p.color)}
      ${bar("Price sanity", s.priceSanity, p.color)}

      ${findings ? `<h4>Findings</h4><ul>${findings}</ul>` : ""}
      ${discrepancies ? `<h4>Spec discrepancies</h4><ul>${discrepancies}</ul>` : ""}

      ${
        result.imageAnalysis?.isAiGenerated
          ? `<div class="flag"><span>⚠</span><span>${esc(
              result.imageAnalysis.explanation
            )}</span></div>`
          : ""
      }`;

    footer.textContent = result.cached
      ? "Cached result · click the on-page badge for details"
      : "Freshly analysed · click the on-page badge for details";
  }

  async function main() {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab) return empty("No active tab", "");

    if (!/^https:\/\/shopee\.sg\//.test(tab.url || "")) {
      return empty("Not a Shopee page", "Open a Shopee SG product listing to see its trust score.");
    }

    const key = `tab:${tab.id}`;
    const entry = (await chrome.storage.session.get(key))[key];

    if (!entry) {
      return empty("No analysis yet", "Open a product listing and give Sentinel a moment.");
    }
    if (!entry.ok) {
      footer.textContent = "Sentinel could not reach its analysis service.";
      return empty("Could not verify", entry.error || "Analysis unavailable.");
    }
    render(entry);
  }

  main().catch((err) => empty("Something went wrong", String(err)));
})();
