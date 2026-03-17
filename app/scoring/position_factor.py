"""
Position Factor Calculator.

CS3 Task 6.0a:
  PF = 0.6 * VR_component + 0.4 * MCap_component
  Bounded to [-1, 1]
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict


SECTOR_AVG_VR: Dict[str, float] = {
    "technology": 65.0,
    "financial_services": 55.0,
    "financial": 55.0,
    "healthcare": 52.0,
    "business_services": 50.0,
    "services": 50.0,
    "retail": 48.0,
    "consumer": 48.0,
    "manufacturing": 45.0,
    "industrials": 45.0,
}


class PositionFactorCalculator:

    def calculate_position_factor(
        self,
        vr_score: float,
        sector: str,
        market_cap_percentile: float,
    ) -> Decimal:
        sector_avg = SECTOR_AVG_VR.get(sector.lower(), 50.0)

        vr_diff = vr_score - sector_avg
        vr_component = max(-1.0, min(1.0, vr_diff / 50.0))

        mcap_component = (market_cap_percentile - 0.5) * 2.0

        pf = 0.6 * vr_component + 0.4 * mcap_component
        pf = max(-1.0, min(1.0, pf))

        return Decimal(str(pf)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
