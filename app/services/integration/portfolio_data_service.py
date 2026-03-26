from dataclasses import dataclass
from typing import Any, Dict, List, Optional

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
        """
        Placeholder for entry score.
        CS5 plan says this can return 45.0 for now.
        """
        return 45.0

    def get_portfolio_view(self, fund_id: str = "default") -> List[PortfolioCompanyView]:
        companies = self.cs1_client.get_portfolio_companies()

        portfolio_view: List[PortfolioCompanyView] = []

        for company in companies:
            ticker = getattr(company, "ticker", None) or getattr(company, "company_id", None)
            name = getattr(company, "name", ticker)
            sector = getattr(company, "sector", "Unknown")

            assessment = self.cs3_client.get_assessment(ticker)
            entry_score = self._get_entry_score(ticker)
            current_score = assessment.org_air_score
            delta = current_score - entry_score

            evidence = self.cs2_client.get_evidence_for_cs5(
                company_id=ticker,
                dimension="all",
                limit=10,
            )

            evidence_count = len(evidence) if isinstance(evidence, list) else 0

            portfolio_view.append(
                PortfolioCompanyView(
                    ticker=ticker,
                    name=name,
                    sector=sector,
                    org_air=current_score,
                    vr=assessment.vr_score,
                    hr=assessment.hr_score,
                    synergy=assessment.synergy_score,
                    dimensions=assessment.dimension_scores,
                    confidence_interval=assessment.confidence_interval,
                    delta=delta,
                    evidence_count=evidence_count,
                )
            )

        return portfolio_view