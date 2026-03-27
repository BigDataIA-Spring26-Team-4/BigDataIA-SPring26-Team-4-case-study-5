"""
Task 9.1: Unified Portfolio Data Service — Integrates CS1, CS2, CS3, CS4.

This is the ONLY way to get data for agents and dashboards.
ALL data comes from YOUR CS1-CS4 implementations.
"""

from dataclasses import dataclass
from typing import List, Dict
import structlog

from services.cs1_client import CS1Client, Company, Sector
from services.cs2_client import CS2Client, Evidence
from services.cs3_client import CS3Client, CompanyAssessment, Dimension
from services.cs4_client import CS4Client, ScoreJustification
from config import settings

logger = structlog.get_logger()


@dataclass
class PortfolioCompanyView:
    """Complete view of a portfolio company from CS1-CS4."""
    company_id: str
    ticker: str
    name: str
    sector: str
    org_air: float
    vr_score: float
    hr_score: float
    synergy_score: float
    dimension_scores: Dict[str, float]
    confidence_interval: tuple
    entry_org_air: float
    delta_since_entry: float
    evidence_count: int


class PortfolioDataService:
    """Unified data service integrating CS1-CS4."""

    def __init__(
        self,
        cs1_url: str = "http://localhost:8000",
        cs2_url: str = "http://localhost:8000",
        cs3_url: str = "http://localhost:8000",
        cs4_url: str = "http://localhost:8000",
    ):
        self.cs1 = CS1Client(base_url=cs1_url)
        self.cs2 = CS2Client(base_url=cs2_url)
        self.cs3 = CS3Client(base_url=cs3_url)
        self.cs4 = CS4Client(base_url=cs4_url)
        logger.info("portfolio_data_service_initialized")

    async def get_portfolio_view(
        self,
        fund_id: str = "growth_fund_v",
    ) -> List[PortfolioCompanyView]:
        """
        Load portfolio from CS1, scores from CS3, evidence from CS2.

        Returns a unified view for each portfolio company.
        """
        # Call CS1 API for company list
        companies = await self.cs1.get_portfolio_companies(fund_id)

        views: List[PortfolioCompanyView] = []
        for company in companies:
            try:
                # Call CS3 API for scoring
                assessment = await self.cs3.get_assessment(company.ticker)

                # Call CS2 API for evidence count
                evidence = await self.cs2.get_evidence(
                    company.ticker, dimension="all", limit=100
                )

                entry_score = await self._get_entry_score(company.company_id)

                views.append(PortfolioCompanyView(
                    company_id=company.company_id,
                    ticker=company.ticker,
                    name=company.name,
                    sector=company.sector.value,
                    org_air=assessment.org_air_score,
                    vr_score=assessment.vr_score,
                    hr_score=assessment.hr_score,
                    synergy_score=assessment.synergy_score,
                    dimension_scores={
                        d.value: s.score
                        for d, s in assessment.dimension_scores.items()
                    },
                    confidence_interval=assessment.confidence_interval,
                    entry_org_air=entry_score,
                    delta_since_entry=round(
                        assessment.org_air_score - entry_score, 1
                    ),
                    evidence_count=len(evidence),
                ))

            except Exception as e:
                logger.error(
                    "portfolio_company_failed",
                    ticker=company.ticker,
                    error=str(e),
                )
                # Propagate errors — NO mock data
                raise

        return views

    async def _get_entry_score(self, company_id: str) -> float:
        """
        Get entry score from CS1 portfolio tracking.

        In production: query CS1's portfolio_positions table.
        Placeholder: returns 45.0 per PDF spec.
        """
        return 45.0


# Singleton instance using settings
portfolio_data_service = PortfolioDataService(
    cs1_url=settings.CS1_URL,
    cs2_url=settings.CS2_URL,
    cs3_url=settings.CS3_URL,
    cs4_url=settings.CS4_URL,
)
