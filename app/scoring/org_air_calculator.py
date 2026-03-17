"""
Full Org-AI-R Calculator.

CS3 Task 6.4: Integrates VR, HR, and Synergy into the final score:
  Org-AI-R = (1 - beta) * [alpha * VR + (1 - alpha) * HR] + beta * Synergy

  alpha = 0.60 (idiosyncratic weight)
  beta  = 0.12 (synergy weight)
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


ALPHA = Decimal("0.60")
BETA = Decimal("0.12")


@dataclass
class OrgAIRResult:
    final_score: Decimal
    vr_score: Decimal
    hr_score: Decimal
    synergy_score: Decimal
    vr_contribution: Decimal
    hr_contribution: Decimal
    synergy_contribution: Decimal


class OrgAIRCalculator:

    def calculate(
        self,
        vr_score: Decimal,
        hr_score: Decimal,
        synergy_score: Decimal,
    ) -> OrgAIRResult:
        weighted_components = ALPHA * vr_score + (Decimal("1") - ALPHA) * hr_score
        final = (Decimal("1") - BETA) * weighted_components + BETA * synergy_score

        final = max(Decimal("0"), min(Decimal("100"), final))

        return OrgAIRResult(
            final_score=final.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            vr_score=vr_score,
            hr_score=hr_score,
            synergy_score=synergy_score,
            vr_contribution=(ALPHA * vr_score * (Decimal("1") - BETA)).quantize(Decimal("0.01")),
            hr_contribution=((Decimal("1") - ALPHA) * hr_score * (Decimal("1") - BETA)).quantize(Decimal("0.01")),
            synergy_contribution=(BETA * synergy_score).quantize(Decimal("0.01")),
        )
