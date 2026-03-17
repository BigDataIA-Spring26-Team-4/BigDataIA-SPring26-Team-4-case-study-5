"""
Decimal-safe math utilities for the scoring engine.

All scoring calculations use Decimal to avoid floating-point drift.
"""

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import List
import math


def to_decimal(value: float, places: int = 4) -> Decimal:
    """Convert float to Decimal with explicit precision."""
    return Decimal(str(value)).quantize(
        Decimal(10) ** -places, rounding=ROUND_HALF_UP
    )


def clamp(
    value: Decimal,
    min_val: Decimal = Decimal("0"),
    max_val: Decimal = Decimal("100"),
) -> Decimal:
    """Clamp value to [min_val, max_val]."""
    return max(min_val, min(max_val, value))


def weighted_mean(values: List[Decimal], weights: List[Decimal]) -> Decimal:
    """
    Calculate weighted mean.
    Returns Decimal("0") if total weight is zero.
    """
    if len(values) != len(weights):
        raise ValueError("values and weights must have the same length")

    total_weight = sum(weights)
    if total_weight == Decimal("0"):
        return Decimal("0")

    numerator = sum(v * w for v, w in zip(values, weights))
    result = numerator / total_weight
    return result.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def weighted_std_dev(
    values: List[Decimal], weights: List[Decimal], mean: Decimal
) -> Decimal:
    """
    Calculate weighted standard deviation.
    Uses population formula: sqrt(sum(w_i * (x_i - mean)^2) / sum(w_i))
    """
    if len(values) != len(weights):
        raise ValueError("values and weights must have the same length")

    total_weight = sum(weights)
    if total_weight == Decimal("0"):
        return Decimal("0")

    variance_num = sum(w * (v - mean) ** 2 for v, w in zip(values, weights))
    variance = variance_num / total_weight

    # Decimal doesn't have sqrt, convert through float
    std = Decimal(str(math.sqrt(float(variance))))
    return std.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def coefficient_of_variation(std_dev: Decimal, mean: Decimal) -> Decimal:
    """
    Calculate CV = std_dev / mean.
    Returns Decimal("0") when mean is zero to avoid division errors.
    """
    if mean == Decimal("0"):
        return Decimal("0")

    cv = std_dev / mean
    return cv.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
