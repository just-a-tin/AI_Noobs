/**
 * Drives the DOM-fallback extractor against fixture-page.html and renders a
 * badge from a mock verdict — no extension host, no backend, no network.
 *
 * The fixture is opened over file://, so there is no `-i.{shopId}.{itemId}`
 * in the URL; ids are supplied directly to exercise the scraper itself.
 */
(function () {
  const { extract, presentation, mockVerdict } = self.Sentinel;
  const rows = document.getElementById("rows");

  const line = (label, value, ok) =>
    `<div class="row"><span>${label}</span><span class="${
      ok === undefined ? "" : ok ? "ok" : "bad"
    }">${value}</span></div>`;

  const listing = extract.fromDom({ shopId: "998877", itemId: "22334455" });

  const checks = [
    ["title", listing.title, /Christmas Tree/.test(listing.title)],
    ["price", listing.price, Math.abs(listing.price - 12.9) < 0.01],
    [
      "originalPrice",
      listing.originalPrice,
      Math.abs(listing.originalPrice - 89) < 0.01,
    ],
    ["spec count", Object.keys(listing.specs).length, Object.keys(listing.specs).length === 5],
    // Exact counts: the gallery/review split is the signal the model relies on,
    // so a leak in either direction is a real failure, not a rounding issue.
    ["gallery images", listing.imageUrls.length, listing.imageUrls.length === 4],
    ["review images", listing.reviewImageUrls.length, listing.reviewImageUrls.length === 3],
    [
      "no review photo in gallery",
      listing.imageUrls.filter((u) => u.includes("review")).length,
      !listing.imageUrls.some((u) => u.includes("review")),
    ],
  ];

  rows.innerHTML =
    checks.map(([k, v, ok]) => line(k, `${v} ${ok ? "✓" : "✗"}`, ok)).join("") +
    line("specs", JSON.stringify(listing.specs)) +
    line("all passed", checks.every((c) => c[2]) ? "YES" : "NO", checks.every((c) => c[2]));

  // --- Badge preview --------------------------------------------------------

  const verdict = mockVerdict(listing);
  const p = presentation(verdict.riskLevel);
  const s = verdict.subScores;

  const host = document.createElement("div");
  host.style.cssText = "position:fixed;right:20px;bottom:20px;z-index:99999;";
  document.body.appendChild(host);

  const sizePanel = (v) => {
    const sa = v.scaleAnalysis;
    if (!sa) return "";
    if (sa.scaleConfidence === "NONE" || sa.apparentLongestCm == null) {
      return `<div style="margin-top:10px;padding:9px;border-radius:8px;background:#f1f5f9;
                          font-size:11px;color:#475569;line-height:1.5">
                <b>Size could not be verified.</b> ${sa.explanation}
              </div>`;
    }
    const claim = v.listedLongestCm ?? sa.expectedLongestCm;
    return `<div style="margin-top:10px;padding:9px;border-radius:8px;
                        background:${sa.mismatchDetected ? "#fef2f2" : "#f0fdf4"}">
              <div style="display:flex;align-items:baseline;gap:7px;margin-bottom:5px">
                ${claim ? `<s style="color:#94a3b8">${claim} cm</s><span style="color:#94a3b8">→</span>` : ""}
                <b style="font-size:18px;color:#0f172a">${sa.apparentLongestCm} cm</b>
              </div>
              <div style="font-size:11px;color:#334155;line-height:1.5">${sa.explanation}</div>
              ${sa.scaleReference ? `<div style="font-size:10px;color:#94a3b8;margin-top:5px">
                 Measured against ${sa.scaleReference}</div>` : ""}
            </div>`;
  };

  const bar = (name, value) => `
    <div style="margin-bottom:9px">
      <div style="display:flex;justify-content:space-between;font-size:11px;color:#475569;margin-bottom:4px">
        <span>${name}</span><span>${value}</span>
      </div>
      <div style="height:6px;border-radius:3px;background:#e2e8f0;overflow:hidden">
        <div style="height:100%;width:${value}%;background:${p.color}"></div>
      </div>
    </div>`;

  host.attachShadow({ mode: "open" }).innerHTML = `
    <div style="width:300px;border-radius:12px;background:#fff;overflow:hidden;
                box-shadow:0 8px 28px rgba(0,0,0,.18),0 0 0 1px rgba(0,0,0,.06);
                font:13px/1.45 -apple-system,'Segoe UI',Roboto,sans-serif">
      <div style="display:flex;align-items:center;gap:10px;padding:12px 14px">
        <div style="width:30px;height:30px;border-radius:50%;background:${p.color};
                    color:#fff;display:grid;place-items:center;font-weight:700">${p.icon}</div>
        <div>
          <div style="font-weight:700;font-size:15px;color:#0f172a">
            Trust score ${verdict.overallTrustScore}/100
          </div>
          <div style="font-size:11px;color:#64748b">${p.label}</div>
        </div>
      </div>
      <div style="border-top:1px solid #e2e8f0;padding:12px 14px">
        ${bar("Visual integrity", s.visualIntegrity)}
        ${bar("Spec consistency", s.specConsistency)}
        ${bar("Price sanity", s.priceSanity)}
        ${bar("Scale fidelity", s.scaleFidelity)}
        ${sizePanel(verdict)}
        <div style="font-size:11px;color:#64748b;margin-top:8px">Preview — mock verdict</div>
      </div>
    </div>`;
})();
