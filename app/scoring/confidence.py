"""
SEM-based Confidence Calculator.

CS3 Task 6.2: Uses Spearman-Brown reliability to estimate
confidence intervals around Org-AI-R scores.

SEM = sigma * sqrt(1 - rho)
rho = (n * r) / (1 + (n - 1) * r)   [Spearman-Brown]
"""

import math
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


@dataclass
class ConfidenceResult:
    score: Decimal
    ci_lower: Decimal
    ci_upper: Decimal
    sem: Decimal
    reliability: Decimal
    confidence: Decimal


class ConfidenceCalculator:

    BASE_RELIABILITY = 0.70   # assumed inter-rater reliability
    SCORE_STD_DEV = 15.0      # assumed population std dev for scores

    def calculate(
        self,
        score: Decimal,
        score_type: str = "org_air",
        evidence_count: int = 1,
    ) -> ConfidenceResult:
        n = max(evidence_count, 1)
        r = self.BASE_RELIABILITY

        # Spearman-Brown stepped-up reliability
        rho = (n * r) / (1 + (n - 1) * r)
        rho = min(rho, 0.99)

        sigma = self.SCORE_STD_DEV
        sem = sigma * math.sqrt(1 - rho)

        z = 1.96  # 95% CI
        s = float(score)
        ci_lower = max(0, s - z * sem)
        ci_upper = min(100, s + z * sem)

        confidence = Decimal(str(round(rho, 4)))

        return ConfidenceResult(
            score=score,
            ci_lower=Decimal(str(round(ci_lower, 2))),
            ci_upper=Decimal(str(round(ci_upper, 2))),
            sem=Decimal(str(round(sem, 4))),
            reliability=Decimal(str(round(rho, 4))),
            confidence=confidence,
        )
