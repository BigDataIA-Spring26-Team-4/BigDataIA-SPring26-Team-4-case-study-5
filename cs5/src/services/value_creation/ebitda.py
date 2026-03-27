"""
Task 9.2 (tool #4): EBITDA Impact Projector.

Projects EBITDA uplift from AI-readiness improvements
using the Org-AI-R v2.0 scoring parameters.

Used by MCP tool: project_ebitda_impact
"""

from dataclasses import dataclass
import structlog

logger = structlog.get_logger()

# Org-AI-R v2.0 scoring parameters
ALPHA = 0.60    # V^R weight
BETA = 0.12     # Synergy coefficient
GAMMA_0 = 0.0025  # Base EBITDA multiplier per Org-AI-R point
GAMMA_1 = 0.05    # Conservative discount
GAMMA_2 = 0.025   # Base case factor
GAMMA_3 = 0.01    # Optimistic bonus


@dataclass
class EBITDAProjection:
    """EBITDA impact projection result."""
    company_id: str
    entry_score: float
    exit_score: float
    delta_air: float
    h_r_score: float
    conservative_pct: float
    base_pct: float
    optimistic_pct: float
    risk_adjusted_pct: float
    requires_approval: bool  # HITL trigger: > 5%


class EBITDACalculator:
    """
    Projects EBITDA impact from Org-AI-R score improvements.

    The model uses v2.0 parameters to compute three scenarios
    (conservative, base, optimistic) and a risk-adjusted figure.

    Formula:
      delta_air = exit_score - entry_score
      base_pct = delta_air * GAMMA_0 * (1 + GAMMA_2 * h_r_adjustment)
      conservative_pct = base_pct * (1 - GAMMA_1)
      optimistic_pct = base_pct * (1 + GAMMA_3 * delta_air)
      risk_adjusted = base_pct * risk_factor(h_r_score)
    """

    def project(
        self,
        company_id: str,
        entry_score: float,
        exit_score: float,
        h_r_score: float,
    ) -> EBITDAProjection:
        """
        Project EBITDA impact from AI-readiness improvement.

        Args:
            company_id: Company ticker
            entry_score: Org-AI-R at portfolio entry
            exit_score: Target Org-AI-R at exit
            h_r_score: Current H^R (systematic readiness) score

        Returns:
            EBITDAProjection with 3 scenarios + risk-adjusted
        """
        delta_air = exit_score - entry_score

        # H^R adjustment: higher H^R = more favorable environment
        h_r_adjustment = h_r_score / 100.0

        # Base case: each point of Org-AI-R improvement → GAMMA_0% EBITDA uplift
        # modulated by systematic readiness (H^R)
        base_pct = delta_air * GAMMA_0 * 100 * (1 + GAMMA_2 * h_r_adjustment)

        # Conservative: discount by GAMMA_1
        conservative_pct = base_pct * (1 - GAMMA_1)

        # Optimistic: bonus scales with magnitude of improvement
        optimistic_pct = base_pct * (1 + GAMMA_3 * delta_air)

        # Risk adjustment based on H^R
        # Low H^R (< 50) → higher risk → more discount
        # High H^R (> 70) → lower risk → less discount
        if h_r_score >= 70:
            risk_factor = 0.90
        elif h_r_score >= 50:
            risk_factor = 0.75
        else:
            risk_factor = 0.60

        risk_adjusted_pct = base_pct * risk_factor

        # HITL trigger: projections > 5% require human approval
        requires_approval = risk_adjusted_pct > 5.0

        projection = EBITDAProjection(
            company_id=company_id,
            entry_score=entry_score,
            exit_score=exit_score,
            delta_air=round(delta_air, 2),
            h_r_score=h_r_score,
            conservative_pct=round(conservative_pct, 2),
            base_pct=round(base_pct, 2),
            optimistic_pct=round(optimistic_pct, 2),
            risk_adjusted_pct=round(risk_adjusted_pct, 2),
            requires_approval=requires_approval,
        )

        logger.info(
            "ebitda_projected",
            company_id=company_id,
            delta_air=projection.delta_air,
            base_pct=projection.base_pct,
            requires_approval=requires_approval,
        )

        return projection


# Module-level singleton (per PDF v4 FIX: init at module level)
ebitda_calculator = EBITDACalculator()
