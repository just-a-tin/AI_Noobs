/**
 * Risk-level presentation. Mirrors backend/app/scoring.py — the backend is the
 * source of truth for which level a score maps to; this is only how we paint it.
 */
(function (root) {
  root.Sentinel = root.Sentinel || {};

  const PRESENTATION = {
    LOW: {
      color: "#15803d",
      surface: "#dcfce7",
      label: "Verified authentic profile",
      short: "Looks genuine",
      icon: "✓",
    },
    MEDIUM: {
      color: "#a16207",
      surface: "#fef9c3",
      label: "Caution: spec inconsistencies",
      short: "Check carefully",
      icon: "!",
    },
    HIGH: {
      color: "#b91c1c",
      surface: "#fee2e2",
      label: "High risk: probable bait-and-switch",
      short: "High risk",
      icon: "✕",
    },
    UNAVAILABLE: {
      color: "#475569",
      surface: "#e2e8f0",
      label: "Could not verify this listing",
      short: "Unverified",
      icon: "?",
    },
  };

  root.Sentinel.presentation = (riskLevel) =>
    PRESENTATION[riskLevel] || PRESENTATION.UNAVAILABLE;

  root.Sentinel.PRESENTATION = PRESENTATION;
})(typeof self !== "undefined" ? self : globalThis);
