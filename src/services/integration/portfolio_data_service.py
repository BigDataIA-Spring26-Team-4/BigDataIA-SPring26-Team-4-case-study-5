from dataclasses import dataclass
from typing import Any, Dict, List

from app.services.integration.cs1_client import CS1Client
from app.services.integration.cs2_client import CS2Client
from app.services.integration.cs3_client import CS3Client


@dataclass
class PortfolioCompanyView:
    ticker: str
    name: str
    sector: str
    org_air: float
    vr: float
    hr: float
    synergy: float
    dimensions: Dict[str, Any]
    confidence_interval: List[float]
    delta: float
    evidence_count: int


class PortfolioDataService:
    def __init__(self):
        self.cs1 = CS1Client()
        self.cs2 = CS2Client()
        self.cs3 = CS3Client()

    def _get_entry_score(self, ticker: str) -> float:
        return 45.0

    async def get_portfolio_view(self, fund_id: str = "default") -> List[PortfolioCompanyView]:
        default_tickers = ["NVDA", "JPM", "WMT", "GE", "DG"]
        portfolio_view: List[PortfolioCompanyView] = []

        for ticker in default_tickers:
            try:
                company = await self.cs1.get_company(ticker)
            except Exception:
                company = {"ticker": ticker, "name": ticker, "sector": "Unknown"}

            if isinstance(company, dict):
                ticker_val = company.get("ticker", ticker)
                name = company.get("name", ticker_val)
                sector = company.get("sector", "Unknown")
            else:
                ticker_val = getattr(company, "ticker", ticker)
                name = getattr(company, "name", ticker_val)
                sector = getattr(company, "sector", "Unknown")

            try:
                assessment = await self.cs3.get_assessment(ticker_val)
                current_score = assessment.org_air_score
                vr = assessment.vr_score
                hr = assessment.hr_score
                synergy = assessment.synergy_score
                dimensions = assessment.dimension_scores
                ci = list(assessment.confidence_interval)
            except Exception:
                current_score = 0.0
                vr = 0.0
                hr = 0.0
                synergy = 0.0
                dimensions = {}
                ci = [0.0, 0.0]

            entry_score = self._get_entry_score(ticker_val)
            delta = current_score - entry_score

            try:
                evidence = await self.cs2.get_evidence_for_cs5(
                    company_id=ticker_val,
                    limit=10,
                )
                evidence_count = len(evidence)
            except Exception:
                evidence_count = 0

            portfolio_view.append(
                PortfolioCompanyView(
                    ticker=ticker_val,
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