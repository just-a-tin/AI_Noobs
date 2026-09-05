"""Deterministic mapping from trust score to risk level.

Kept out of the model's hands on purpose: asking an LLM to keep a 0-100 score
and a three-value enum mutually consistent is a reliable way to end up with a
green badge sitting next to a score of 31.
"""

from __future__ import annotations

from .schemas import RiskLevel

# Boundaries are inclusive-low: >=75 LOW, 45-74 MEDIUM, <45 HIGH.
LOW_THRESHOLD = 75
MEDIUM_THRESHOLD = 45


def derive_risk_level(trust_score: int) -> RiskLevel:
    if trust_score >= LOW_THRESHOLD:
        return RiskLevel.LOW
    if trust_score >= MEDIUM_THRESHOLD:
        return RiskLevel.MEDIUM
    return RiskLevel.HIGH


#: Badge presentation, colocated with the thresholds so the two stay in step.
RISK_PRESENTATION = {
    RiskLevel.LOW: {"color": "green", "label": "Verified authentic profile"},
    RiskLevel.MEDIUM: {"color": "yellow", "label": "Caution: spec inconsistencies"},
    RiskLevel.HIGH: {"color": "red", "label": "High risk: probable bait-and-switch"},
}
