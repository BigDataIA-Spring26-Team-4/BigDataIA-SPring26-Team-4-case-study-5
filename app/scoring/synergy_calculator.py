"""
Synergy Calculator.

CS3 Task 6.3:
  Synergy = VR * HR / 100 * Alignment * TimingFactor
  TimingFactor in [0.8, 1.2]
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


@dataclass
class SynergyResult:
    synergy_score: Decimal
    alignment: Decimal
    timing_factor: Decimal


class SynergyCalculator:

    def calculate(
        self,
        vr_score: Decimal,
        hr_score: Decimal,
        alignment: float = 1.0,
        timing_factor: float = 1.0,
    ) -> SynergyResult:
        align = Decimal(str(max(0, min(1, alignment))))
        timing = Decimal(str(max(0.8, min(1.2, timing_factor))))

        synergy = vr_score * hr_score / Decimal("100") * align * timing
        synergy = max(Decimal("0"), min(Decimal("100"), synergy))

        return SynergyResult(
            synergy_score=synergy.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            alignment=align,
            timing_factor=timing,
        )
