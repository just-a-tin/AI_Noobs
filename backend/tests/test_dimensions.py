"""Sellers write dimensions a dozen ways. The parser feeds the model its
ground truth, so a wrong parse becomes a wrong scam verdict."""

import pytest

from app.dimensions import listed_longest_cm, parse_longest_cm


@pytest.mark.parametrize(
    "text,expected",
    [
        ("12x8x3 cm", 12.0),
        ("12 x 8 x 3 cm", 12.0),
        ("12*8*3cm", 12.0),
        ("12×8×3 cm", 12.0),
        ("30 x 20 cm", 30.0),
        ("15cm", 15.0),
        ("15 cm", 15.0),
        ("150mm", 15.0),
        ("150 millimeters", 15.0),
        ("1.8m", 180.0),
        ("2 meters", 200.0),
        ('6"', 15.24),
        ("6 inch", 15.24),
        ("6 inches", 15.24),
        ("1,5 cm", 1.5),
    ],
)
def test_parses_common_formats(text, expected):
    assert parse_longest_cm(text) == pytest.approx(expected, abs=0.02)


@pytest.mark.parametrize("text", ["", "one size", "Large", "N/A", "512GB", "black"])
def test_returns_none_when_no_dimension(text):
    assert parse_longest_cm(text) is None


def test_longest_edge_wins_regardless_of_order():
    assert parse_longest_cm("3 x 20 x 8 cm") == 20.0


def test_bare_series_assumes_centimetres():
    """Sellers routinely omit the unit; cm is the Shopee convention."""
    assert parse_longest_cm("40 x 25 x 10") == 40.0


def test_reads_only_size_fields():
    specs = {
        "Dimensions": "12x8x3 cm",
        "Weight": "2.4 kg",
        "Storage Capacity": "512GB",
        "Battery Life": "40 hours",
    }
    assert listed_longest_cm(specs) == 12.0


def test_weight_and_capacity_are_not_sizes():
    """'2.4 kg' and '512GB' contain no length, and must not be read as one."""
    assert listed_longest_cm({"Weight": "2.4 kg", "Capacity": "512GB"}) is None


def test_takes_largest_across_multiple_size_fields():
    specs = {"Height": "180 cm", "Width": "60cm", "Package Size": "1.9m"}
    assert listed_longest_cm(specs) == 190.0


def test_missing_specs_are_safe():
    assert listed_longest_cm({}) is None
