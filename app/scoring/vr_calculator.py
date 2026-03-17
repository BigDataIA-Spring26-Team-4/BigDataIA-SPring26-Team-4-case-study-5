"""
VR (Value-Readiness) Calculator.

CS3 Task 5.2: Implements the core VR formula:
  VR = Dw_bar * (1 - lambda * cvD) * TalentRiskAdj

Where:
  Dw_bar = weighted mean of 7 dimension scores
  lambda = 0.25 (non-compensatory penalty)
  cvD = coefficient of variation across dimensions
  TalentRiskAdj = 1 - 0.15 * max(0, TC - 0.25)
"""

import structlog
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict

from app.scoring.utils import (
    to_decimal,
    clamp,
    weighted_mean,
    weighted_std_dev,
    coefficient_of_variation,
)

logger = structlog.get_logger(__name__)

DIMENSION_WEIGHTS: Dict[str, Decimal] = {
    "data_infrastructure": Decimal("0.25"),
    "ai_governance": Decimal("0.20"),
    "technology_stack": Decimal("0.15"),
    "talent": Decimal("0.15"),
    "leadership": Decimal("0.10"),
    "use_case_portfolio": Decimal("0.10"),
    "culture": Decimal("0.05"),
}

LAMBDA = Decimal("0.25")
TC_PENALTY_COEFF = Decimal("0.15")
TC_THRESHOLD = Decimal("0.25")


@dataclass
class VRResult:
    vr_score: Decimal
    weighted_mean: Decimal
    cv_penalty: Decimal
    talent_risk_adj: Decimal
    dimension_scores: Dict[str, Decimal]
    dimension_weights: Dict[str, Decimal]
    std_dev: Decimal
    cv: Decimal


class VRCalculator:

    def calculate(
        self,
        dimension_scores: Dict[str, float],
        talent_concentration: float = 0.2,
        sector: str = "default",
    ) -> VRResult:

        weights = self._get_sector_weights(sector)

        dims = list(weights.keys())
        values = [to_decimal(dimension_scores.get(d, 50.0)) for d in dims]
        wts = [weights[d] for d in dims]

        d_bar = weighted_mean(values, wts)
        std = weighted_std_dev(values, wts, d_bar)
        cv = coefficient_of_variation(std, d_bar)

        cv_penalty = Decimal("1") - LAMBDA * cv
        cv_penalty = max(Decimal("0.5"), min(Decimal("1"), cv_penalty))

        tc = to_decimal(talent_concentration)
        talent_adj = Decimal("1") - TC_PENALTY_COEFF * max(Decimal("0"), tc - TC_THRESHOLD)
        talent_adj = max(Decimal("0.5"), min(Decimal("1"), talent_adj))

        vr = d_bar * cv_penalty * talent_adj
        vr = clamp(vr, Decimal("0"), Decimal("100"))

        result = VRResult(
            vr_score=vr.quantize(Decimal("0.01")),
            weighted_mean=d_bar,
            cv_penalty=cv_penalty.quantize(Decimal("0.0001")),
            talent_risk_adj=talent_adj.quantize(Decimal("0.0001")),
            dimension_scores={d: to_decimal(dimension_scores.get(d, 50.0)) for d in dims},
            dimension_weights=weights,
            std_dev=std,
            cv=cv,
        )

        logger.info(
            "vr_calculated",
            sector=sector,
            vr_score=float(result.vr_score),
            d_bar=float(d_bar),
            cv=float(cv),
            cv_penalty=float(cv_penalty),
            talent_adj=float(talent_adj),
        )

        return result

    def _get_sector_weights(self, sector: str) -> Dict[str, Decimal]:
        """Return dimension weights for VR calculation.

        Uses the framework default weights from CS1 Table 1 (page 5).
        The PDF mentions SectorConfigService for sector-specific weights,
        but does not provide sector-specific values — so we use the
        canonical defaults for all sectors to stay faithful to the spec.
        """
        return dict(DIMENSION_WEIGHTS)
