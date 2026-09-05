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
        reviewCredibility: 84,
      },
      scaleAnalysis: {
        identifiedProduct: "wireless earbuds charging case",
        scaleConfidence: "HIGH",
        sceneReferences: [
          { objectName: "adult hand holding the case", assumedRealCm: 18, impliedProductCm: 6.2 },
          { objectName: "desk keyboard beside the case", assumedRealCm: 44, impliedProductCm: 6 },
        ],
        referenceAgreement: "AGREE",
        expectedLongestCm: 6,
        apparentLongestCm: 6.1,
        mismatchDetected: false,
        explanation:
          "A review photo shows the case in an adult hand at about 6 cm, and a second photo beside a keyboard agrees. Both match the listed size.",
      },
      reviewAnalysis: {
        usableReviewCount: 11,
        complaintThemes: [],
        contradictsListing: false,
        suspectedFakeReviews: false,
        explanation:
          "Eleven reviews carried real text, mentioning specific details and varying in phrasing — what genuine feedback looks like.",
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
        reviewCredibility: 45,
      },
      scaleAnalysis: {
        identifiedProduct: "floor-standing air purifier",
        scaleConfidence: "MEDIUM",
        sceneReferences: [
          { objectName: "adult person beside the unit", assumedRealCm: 170, impliedProductCm: 95 },
          { objectName: "wall power socket behind it", assumedRealCm: 12, impliedProductCm: 34 },
          { objectName: "interior doorway in background", assumedRealCm: 200, impliedProductCm: 88 },
        ],
        referenceAgreement: "CONFLICT",
        expectedLongestCm: 70,
        apparentLongestCm: 90,
        mismatchDetected: true,
        explanation:
          "The person and doorway both put the unit near 90 cm, but the wall socket implies only 34 cm. No single real photograph can satisfy both, so the product was likely composited into the room scene.",
      },
      reviewAnalysis: {
        usableReviewCount: 6,
        complaintThemes: [
          "unit smaller than it looks in the listing photos",
          "feels like plastic despite the aluminium claim",
        ],
        contradictsListing: true,
        suspectedFakeReviews: false,
        explanation:
          "Six reviews had usable text and read as genuine, but two independently describe a smaller, cheaper-feeling product than the listing implies.",
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
        reviewCredibility: 9,
      },
      scaleAnalysis: {
        identifiedProduct: "artificial Christmas tree",
        scaleConfidence: "HIGH",
        sceneReferences: [
          { objectName: "two-seat sofa in gallery image", assumedRealCm: 180, impliedProductCm: 175 },
          { objectName: "adult hand in review photo", assumedRealCm: 18, impliedProductCm: 22 },
          { objectName: "dining table in review photo", assumedRealCm: 75, impliedProductCm: 24 },
        ],
        referenceAgreement: "AGREE",
        expectedLongestCm: 180,
        apparentLongestCm: 22,
        mismatchDetected: true,
        explanation:
          "The gallery stages the tree beside a sofa, implying 175 cm. Every review photo disagrees: 22 cm against a hand, 24 cm against a dining table. The review photos agree with each other, so the gallery is staged to make a desk ornament look like furniture.",
      },
      reviewAnalysis: {
        usableReviewCount: 4,
        complaintThemes: [
          "received a tiny desk ornament, not a floor tree",
          "nothing like the photos",
        ],
        contradictsListing: true,
        suspectedFakeReviews: true,
        explanation:
          "Only 4 of 312 reviews carried real text, all describing a hand-sized ornament. The rest are empty or one-word praise with repeated phrasings — a review farm padding the score.",
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
