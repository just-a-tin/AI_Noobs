"""Threshold boundaries. An off-by-one here mislabels a badge colour, which is
the one thing a trust product cannot get wrong."""

import pytest

from app.schemas import RiskLevel
from app.scoring import derive_risk_level


@pytest.mark.parametrize(
    "score,expected",
    [
        (100, RiskLevel.LOW),
        (75, RiskLevel.LOW),
        (74, RiskLevel.MEDIUM),
        (45, RiskLevel.MEDIUM),
        (44, RiskLevel.HIGH),
        (0, RiskLevel.HIGH),
    ],
)
def test_risk_boundaries(score, expected):
    assert derive_risk_level(score) is expected
