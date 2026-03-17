"""Tests for scoring decimal utilities."""

import pytest
from decimal import Decimal
from app.scoring.utils import (
    to_decimal,
    clamp,
    weighted_mean,
    weighted_std_dev,
    coefficient_of_variation,
)


class TestToDecimal:
    def test_basic_conversion(self):
        assert to_decimal(3.14) == Decimal("3.1400")

    def test_custom_places(self):
        assert to_decimal(3.14159, places=2) == Decimal("3.14")

    def test_zero(self):
        assert to_decimal(0.0) == Decimal("0.0000")

    def test_negative(self):
        assert to_decimal(-5.5) == Decimal("-5.5000")

    def test_rounding(self):
        assert to_decimal(0.12345, places=4) == Decimal("0.1235")


class TestClamp:
    def test_within_range(self):
        assert clamp(Decimal("50")) == Decimal("50")

    def test_below_min(self):
        assert clamp(Decimal("-5")) == Decimal("0")

    def test_above_max(self):
        assert clamp(Decimal("150")) == Decimal("100")

    def test_at_boundaries(self):
        assert clamp(Decimal("0")) == Decimal("0")
        assert clamp(Decimal("100")) == Decimal("100")

    def test_custom_range(self):
        result = clamp(Decimal("1.5"), Decimal("-1"), Decimal("1"))
        assert result == Decimal("1")


class TestWeightedMean:
    def test_equal_weights(self):
        vals = [Decimal("60"), Decimal("80")]
        wts = [Decimal("1"), Decimal("1")]
        assert weighted_mean(vals, wts) == Decimal("70.0000")

    def test_unequal_weights(self):
        vals = [Decimal("80"), Decimal("60")]
        wts = [Decimal("0.75"), Decimal("0.25")]
        result = weighted_mean(vals, wts)
        assert result == Decimal("75.0000")

    def test_zero_total_weight(self):
        vals = [Decimal("50")]
        wts = [Decimal("0")]
        assert weighted_mean(vals, wts) == Decimal("0")

    def test_length_mismatch(self):
        with pytest.raises(ValueError):
            weighted_mean([Decimal("1")], [Decimal("1"), Decimal("2")])

    def test_seven_dimensions(self):
        # Simulates the 7 AI-readiness dimensions with framework weights
        vals = [Decimal("70")] * 7
        wts = [
            Decimal("0.25"), Decimal("0.20"), Decimal("0.15"),
            Decimal("0.15"), Decimal("0.10"), Decimal("0.10"),
            Decimal("0.05"),
        ]
        result = weighted_mean(vals, wts)
        assert result == Decimal("70.0000")


class TestWeightedStdDev:
    def test_uniform_scores(self):
        vals = [Decimal("70")] * 4
        wts = [Decimal("1")] * 4
        result = weighted_std_dev(vals, wts, Decimal("70"))
        assert result == Decimal("0.0000")

    def test_spread_scores(self):
        vals = [Decimal("20"), Decimal("80")]
        wts = [Decimal("1"), Decimal("1")]
        mean = Decimal("50")
        result = weighted_std_dev(vals, wts, mean)
        assert result == Decimal("30.0000")

    def test_zero_weight(self):
        vals = [Decimal("50")]
        wts = [Decimal("0")]
        result = weighted_std_dev(vals, wts, Decimal("50"))
        assert result == Decimal("0")


class TestCoefficientOfVariation:
    def test_basic(self):
        result = coefficient_of_variation(Decimal("10"), Decimal("50"))
        assert result == Decimal("0.2000")

    def test_zero_mean(self):
        result = coefficient_of_variation(Decimal("10"), Decimal("0"))
        assert result == Decimal("0")

    def test_zero_std(self):
        result = coefficient_of_variation(Decimal("0"), Decimal("50"))
        assert result == Decimal("0.0000")
