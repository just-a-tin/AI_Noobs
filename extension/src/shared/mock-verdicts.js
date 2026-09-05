/**
 * Client-side canned verdicts for `config.uiMockMode`, so the UI can be
 * demoed with no backend running at all. Mirrors backend/app/mocks.py,
 * including the deterministic pick — a demo that reshuffles its verdict
 * between rehearsal and judging is worse than no demo.
 */
(function (root) {
  root.Sentinel = root.Sentinel || {};

  const PERSONAS = [
    {
      overallTrustScore: 88,
      riskLevel: "LOW",
      subScores: { visualIntegrity: 92, specConsistency: 90, priceSanity: 82 },
      findings: [
        "Gallery images and customer review photos show a consistent product.",
        "Listed weight and dimensions agree with published specs.",
        "Price sits within the normal range for this category on Shopee SG.",
      ],
      imageAnalysis: {
        isAiGenerated: false,
        visualDiscrepancyDetected: false,
        explanation: "Natural lighting and consistent shadows across all images.",
      },
      specDiscrepancies: [],
      cached: false,
    },
    {
      overallTrustScore: 58,
      riskLevel: "MEDIUM",
      subScores: { visualIntegrity: 74, specConsistency: 38, priceSanity: 61 },
      findings: [
        "Title claims 'aluminium body' while the spec table says ABS plastic.",
        "Review photos show different port placement from the gallery images.",
      ],
      imageAnalysis: {
        isAiGenerated: false,
        visualDiscrepancyDetected: true,
        explanation:
          "Gallery imagery appears to be reused from a different model variant.",
      },
      specDiscrepancies: [
        "Title says aluminium; specs say ABS plastic.",
        "Stated weight implausible for stated dimensions.",
      ],
      cached: false,
    },
    {
      overallTrustScore: 17,
      riskLevel: "HIGH",
      subScores: { visualIntegrity: 12, specConsistency: 20, priceSanity: 19 },
      findings: [
        "Gallery images show malformed text on packaging and inconsistent reflections.",
        "Customer review photos show a visibly different, lower-grade product.",
        "Price is 82% below the category median.",
      ],
      imageAnalysis: {
        isAiGenerated: true,
        visualDiscrepancyDetected: true,
        explanation:
          "Primary images exhibit generative artefacts; review photos show a plain unbranded item.",
      },
      specDiscrepancies: [
        "Advertised capacity implausible at the listed price.",
        "Brand in the title does not appear on the product in review photos.",
      ],
      cached: false,
    },
  ];

  root.Sentinel.mockVerdict = function (itemId) {
    let hash = 0;
    for (const ch of String(itemId)) {
      hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
    }
    return structuredClone(PERSONAS[hash % PERSONAS.length]);
  };
})(typeof self !== "undefined" ? self : globalThis);
