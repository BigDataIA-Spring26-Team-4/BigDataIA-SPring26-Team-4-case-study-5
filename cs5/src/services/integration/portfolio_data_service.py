from dataclasses import dataclass

from services.cs1_client import CS1Client
from services.cs2_client import CS2Client
from services.cs3_client import CS3Client
from services.cs4_client import CS4Client
from config import settings

@dataclass
class PortfolioView:
    company_id: str
    ticker: str
    name: str
    industry: str
    org_air: float
    vr_score: float
    hr_score: float
    synergy_score: float
    dimension_scores: dict
    confidence_interval: tuple
    evidence_count: int

class PortfolioDataService:
    def __init__(
            self,
            cs1_url: str,
            cs2_url: str,
            cs3_url: str,
            cs4_url: str
    ):
        self.cs1 = CS1Client(cs1_url)
        self.cs2 = CS2Client(cs2_url)
        self.cs3 = CS3Client(cs3_url)
        self.cs4 = CS4Client(cs4_url)

    async def get_portfolio_view(self):
        companies = await self.cs1.get_companies()
        views = []
        for company in companies:
            assessment = await self.cs3.get_assessment(company["ticker"])
            industry = await self.cs1.get_company_industry(company["id"])
            
            view = PortfolioView(
                company_id=company["id"],
                ticker=company["ticker"],
                name=company["name"],
                industry=industry,
                org_air=assessment["final_score"],
                vr_score=assessment["vr_score"],
                hr_score=assessment["hr_score"],
                synergy_score=assessment["synergy_score"],
                dimension_scores=assessment["dimension_scores"],
                confidence_interval=(assessment["ci_lower"], assessment["ci_upper"]),
                evidence_count=assessment["evidence_count"]
            )
            views.append(view)
        return views

portfolio_data_service = PortfolioDataService(
    cs1_url=settings.CS1_URL,
    cs2_url=settings.CS2_URL,
    cs3_url=settings.CS3_URL,
    cs4_url=settings.CS4_URL
)

