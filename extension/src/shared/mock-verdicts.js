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
      listedLongestCm: 6,
      subScores: {
        visualIntegrity: 92,
        specConsistency: 90,
        priceSanity: 82,
        scaleFidelity: 86,
      },
      scaleAnalysis: {
        identifiedProduct: "wireless earbuds charging case",
        scaleConfidence: "HIGH",
        scaleReference: "adult hand holding the case",
        expectedLongestCm: 6,
        apparentLongestCm: 6.2,
        mismatchDetected: false,
        explanation:
          "A review photo shows the case held in an adult hand, spanning about a third of the palm — roughly 6 cm, matching the listed size.",
      },
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
      listedLongestCm: null,
      subScores: {
        visualIntegrity: 74,
        specConsistency: 38,
        priceSanity: 61,
        scaleFidelity: 50,
      },
      scaleAnalysis: {
        identifiedProduct: "compact bluetooth speaker",
        scaleConfidence: "NONE",
        scaleReference: null,
        expectedLongestCm: 12,
        apparentLongestCm: null,
        mismatchDetected: false,
        explanation:
          "Every image is a studio shot on plain white with nothing of known size in frame, so the real size cannot be determined from the photos. Common, and not suspicious in itself.",
      },
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
      listedLongestCm: 180,
      subScores: {
        visualIntegrity: 12,
        specConsistency: 20,
        priceSanity: 19,
        scaleFidelity: 8,
      },
      scaleAnalysis: {
        identifiedProduct: "artificial Christmas tree",
        scaleConfidence: "HIGH",
        scaleReference: "adult hand in customer review photo",
        expectedLongestCm: 180,
        apparentLongestCm: 22,
        mismatchDetected: true,
        explanation:
          "Gallery images stage the tree beside a sofa, implying about 180 cm. A review photo shows the delivered item held in one hand — barely 22 cm. The photography is staged to make a desk ornament look like full-sized furniture.",
      },
      findings: [
        "Listing implies a 180 cm tree, but review photos show buyers holding a 22 cm version in one hand.",
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

  // Claims implausible for the categories these listings sit in.
  const IMPLAUSIBLE = /\b(\d{3,})\s?(gb|tb)\b|\bunlimited\b|\b100%\s?original\b/i;

  /** Mirrors _risk_signals in backend/app/mocks.py — keep the two in step. */
  function riskSignals(listing) {
    let signals = 0;

    if (listing.originalPrice > 0) {
      const discount = 1 - listing.price / listing.originalPrice;
      if (discount >= 0.75) signals += 2;
      else if (discount >= 0.5) signals += 1;
    }

    const specValues = Object.values(listing.specs || {});
    if (IMPLAUSIBLE.test([listing.title, ...specValues].join(" "))) signals += 2;
    if (listing.sellerRating != null && listing.sellerRating < 4.3) signals += 1;
    if (specValues.some((v) => String(v).toLowerCase().includes("no warranty"))) {
      signals += 1;
    }

    return signals;
  }

  /**
   * Deterministic AND plausible: heuristics first so a visibly dodgy listing
   * demos as high risk, hashing only as a tie-break when nothing stands out.
   */
  root.Sentinel.mockVerdict = function (listing) {
    // Tolerate being handed a bare id.
    if (typeof listing === "string" || typeof listing === "number") {
      listing = { itemId: String(listing), specs: {} };
    }

    const signals = riskSignals(listing);
    let index;
    if (signals >= 4) index = 2;
    else if (signals >= 2) index = 1;
    else if (signals === 1) index = 0;
    else {
      let hash = 0;
      for (const ch of String(listing.itemId)) {
        hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
      }
      index = hash % PERSONAS.length;
    }

    return structuredClone(PERSONAS[index]);
  };
})(typeof self !== "undefined" ? self : globalThis);
