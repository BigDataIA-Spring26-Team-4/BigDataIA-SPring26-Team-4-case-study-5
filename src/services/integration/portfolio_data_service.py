import asyncio
from dataclasses import dataclass
from typing import Dict, List, Optional

from app.services.integration.cs1_client import CS1Client
from app.services.integration.cs2_client import CS2Client
from app.services.integration.cs3_client import CS3Client
from app.services.integration.cs4_client import CS4Client


@dataclass
class PortfolioCompanyView:
    ticker: str
    name: str
    sector: str
    org_air: float
    vr: float
    hr: float
    synergy: float
    dimensions: Dict[str, float]
    confidence_interval: List[float]
    delta: float
    evidence_count: int


class PortfolioDataService:
    def __init__(
        self,
        cs1_client: Optional[CS1Client] = None,
        cs2_client: Optional[CS2Client] = None,
        cs3_client: Optional[CS3Client] = None,
        cs4_client: Optional[CS4Client] = None,
    ):
        self.cs1_client = cs1_client or CS1Client()
        self.cs2_client = cs2_client or CS2Client()
        self.cs3_client = cs3_client or CS3Client()
        self.cs4_client = cs4_client or CS4Client()

    def _get_entry_score(self, ticker: str) -> float:
        return 45.0

    def _get_companies_sync(self, fund_id: str = "default"):
        async def _fetch():
            try:
                return await self.cs1_client.get_portfolio_companies(fund_id)
            except TypeError:
                return await self.cs1_client.get_portfolio_companies()

        return asyncio.run(_fetch())

    def _get_assessment_sync(self, ticker: str):
        async def _fetch():
            return await self.cs3_client.get_assessment(ticker)

        return asyncio.run(_fetch())

    def get_portfolio_view(self, fund_id: str = "default") -> List[PortfolioCompanyView]:
        companies = self._get_companies_sync(fund_id)
        portfolio_view: List[PortfolioCompanyView] = []

        for company in companies:
            ticker = getattr(company, "ticker", None) or getattr(company, "company_id", None)
            name = getattr(company, "name", ticker)
            sector = getattr(company, "sector", "Unknown")

            try:
                assessment = self._get_assessment_sync(ticker)
                current_score = assessment.org_air_score
                vr = assessment.vr_score
                hr = assessment.hr_score
                synergy = assessment.synergy_score
                dimensions = assessment.dimension_scores
                ci = assessment.confidence_interval
            except Exception:
                current_score = 0.0
                vr = 0.0
                hr = 0.0
                synergy = 0.0
                dimensions = {}
                ci = [0, 0]

            entry_score = self._get_entry_score(ticker)
            delta = current_score - entry_score

            try:
                evidence = self.cs2_client.get_evidence_for_cs5(
                    company_id=ticker,
                    dimension="all",
                    limit=10,
                )
                evidence_count = len(evidence) if isinstance(evidence, list) else 0
            except Exception:
                evidence_count = 0

            portfolio_view.append(
                PortfolioCompanyView(
                    ticker=ticker,
                    name=name,
                    sector=str(sector),
                    org_air=current_score,
                    vr=vr,
                    hr=hr,
                    synergy=synergy,
                    dimensions=dimensions,
                    confidence_interval=ci,
                    delta=delta,
                    evidence_count=evidence_count,
                )
            )

        return portfolio_view