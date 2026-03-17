"""
HR (Historical Readiness) Calculator.

CS3 Task 6.1:
  HR = HR_base * (1 + delta * PositionFactor)
  delta = 0.15 (corrected in v3.0)
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict

HR_BASE_BY_SECTOR: Dict[str, float] = {
    "technology": 85.0,
    "financial_services": 80.0,
    "financial": 80.0,
    "healthcare": 78.0,
    "business_services": 75.0,
    "services": 75.0,
    "retail": 70.0,
    "consumer": 70.0,
    "manufacturing": 72.0,
    "industrials": 72.0,
}

DELTA = Decimal("0.15")


class HRResult:
    def __init__(self, hr_score: Decimal, hr_base: Decimal, position_factor: Decimal):
        self.hr_score = hr_score
        self.hr_base = hr_base
        self.position_factor = position_factor


class HRCalculator:

    def calculate(
        self,
        sector: str,
        position_factor: float,
    ) -> HRResult:
        base = Decimal(str(HR_BASE_BY_SECTOR.get(sector.lower(), 72.0)))
        pf = Decimal(str(position_factor))

        hr = base * (Decimal("1") + DELTA * pf)
        hr = max(Decimal("0"), min(Decimal("100"), hr))

        return HRResult(
            hr_score=hr.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            hr_base=base,
            position_factor=pf,
        )
