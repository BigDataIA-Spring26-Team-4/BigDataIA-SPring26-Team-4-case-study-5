"""
Task 10.5: Fund-AI-R Calculator (5 pts).

Aggregates company-level Org-AI-R scores into a portfolio-level metric
using EV-weighted averaging, quartile distribution, and sector HHI.

Classes:
  - FundMetrics: Portfolio-level AI-readiness dataclass
  - FundAIRCalculator: EV-weighted aggregation engine
"""

from dataclasses import dataclass
from typing import List, Dict
import structlog

from services.integration.portfolio_data_service import PortfolioCompanyView

logger = structlog.get_logger()


# Sector benchmarks for quartile calculation
SECTOR_BENCHMARKS = {
    "technology":         {"q1": 75, "q2": 65, "q3": 55, "q4": 45},
    "healthcare":         {"q1": 70, "q2": 58, "q3": 48, "q4": 38},
    "financial_services": {"q1": 72, "q2": 60, "q3": 50, "q4": 40},
    "manufacturing":      {"q1": 68, "q2": 55, "q3": 45, "q4": 35},
    "retail":             {"q1": 65, "q2": 52, "q3": 42, "q4": 32},
    "energy":             {"q1": 60, "q2": 48, "q3": 38, "q4": 28},
}


@dataclass
class FundMetrics:
    """Fund-level AI-readiness metrics."""
    fund_id: str
    fund_air: float            # EV-weighted average Org-AI-R
    company_count: int
    quartile_distribution: Dict[int, int]  # {1: count, 2: count, ...}
    sector_hhi: float          # Herfindahl-Hirschman Index (concentration)
    avg_delta_since_entry: float
    total_ev_mm: float
    ai_leaders_count: int      # Score >= 70
    ai_laggards_count: int     # Score < 50


class FundAIRCalculator:
    """
    Calculates Fund-AI-R using EV-weighted aggregation.

    Fund-AI-R = Σ(EV_i × OrgAIR_i) / Σ(EV_i)

    Also computes:
      - Quartile distribution using sector-specific benchmarks
      - Sector HHI for concentration risk
      - Leaders (≥70) and laggards (<50) counts
    """

    def calculate_fund_metrics(
        self,
        fund_id: str,
        companies: List[PortfolioCompanyView],
        enterprise_values: Dict[str, float],
    ) -> FundMetrics:
        """
        Calculate fund-level metrics from portfolio company data.

        Args:
            fund_id: Fund identifier
            companies: List of PortfolioCompanyView from portfolio_data_service
            enterprise_values: Dict of company_id → EV in $MM
                (defaults to 100.0 if not provided for a company)

        Returns:
            FundMetrics with all portfolio-level aggregations
        """
        if not companies:
            raise ValueError("Cannot calculate Fund-AI-R for empty portfolio")

        # ── EV-weighted Org-AI-R ────────────────────────────────
        total_ev = sum(
            enterprise_values.get(c.company_id, 100.0) for c in companies
        )
        weighted_sum = sum(
            enterprise_values.get(c.company_id, 100.0) * c.org_air
            for c in companies
        )
        fund_air = weighted_sum / total_ev if total_ev > 0 else 0.0

        # ── Quartile distribution ───────────────────────────────
        quartile_dist = {1: 0, 2: 0, 3: 0, 4: 0}
        for c in companies:
            q = self._get_quartile(c.org_air, c.sector)
            quartile_dist[q] += 1

        # ── Sector HHI (Herfindahl-Hirschman Index) ─────────────
        # HHI = Σ(sector_share²) where share = sector_ev / total_ev
        sector_ev: Dict[str, float] = {}
        for c in companies:
            ev = enterprise_values.get(c.company_id, 100.0)
            sector_ev[c.sector] = sector_ev.get(c.sector, 0.0) + ev

        hhi = sum(
            (ev / total_ev) ** 2 for ev in sector_ev.values()
        ) if total_ev > 0 else 0.0

        # ── Leaders & Laggards ──────────────────────────────────
        leaders = sum(1 for c in companies if c.org_air >= 70)
        laggards = sum(1 for c in companies if c.org_air < 50)

        # ── Average delta since entry ───────────────────────────
        avg_delta = sum(
            c.delta_since_entry for c in companies
        ) / len(companies)

        metrics = FundMetrics(
            fund_id=fund_id,
            fund_air=round(fund_air, 1),
            company_count=len(companies),
            quartile_distribution=quartile_dist,
            sector_hhi=round(hhi, 4),
            avg_delta_since_entry=round(avg_delta, 1),
            total_ev_mm=round(total_ev, 1),
            ai_leaders_count=leaders,
            ai_laggards_count=laggards,
        )

        logger.info(
            "fund_metrics_calculated",
            fund_id=fund_id,
            fund_air=metrics.fund_air,
            companies=metrics.company_count,
            leaders=leaders,
            laggards=laggards,
            hhi=metrics.sector_hhi,
        )

        return metrics

    def _get_quartile(self, score: float, sector: str) -> int:
        """
        Determine quartile based on sector-specific benchmarks.

        Q1 = top quartile (score >= sector Q1 threshold)
        Q4 = bottom quartile (score < sector Q3 threshold)
        """
        benchmarks = SECTOR_BENCHMARKS.get(
            sector, SECTOR_BENCHMARKS["technology"]
        )
        if score >= benchmarks["q1"]:
            return 1
        elif score >= benchmarks["q2"]:
            return 2
        elif score >= benchmarks["q3"]:
            return 3
        else:
            return 4


# Module-level singleton (per PDF v4 FIX)
fund_air_calculator = FundAIRCalculator()
