"""
CS1 Client — Company metadata from CS1 Platform API.

Wraps CS1 FastAPI endpoints (port 8000).
Returns typed dataclasses matching CS5 PDF Section 1.2.
NO mock data — errors propagate if CS1 is down.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import httpx
import structlog

logger = structlog.get_logger()


# ── Enums & Dataclasses (per CS5 PDF Section 1.2) ──────────────


class Sector(str, Enum):
    TECHNOLOGY = "technology"
    HEALTHCARE = "healthcare"
    FINANCIAL_SERVICES = "financial_services"
    MANUFACTURING = "manufacturing"
    RETAIL = "retail"
    ENERGY = "energy"


# Map various raw sector strings → Sector enum
_SECTOR_MAP = {
    "technology": Sector.TECHNOLOGY,
    "semiconductors": Sector.TECHNOLOGY,
    "healthcare": Sector.HEALTHCARE,
    "financial_services": Sector.FINANCIAL_SERVICES,
    "financial": Sector.FINANCIAL_SERVICES,
    "banking": Sector.FINANCIAL_SERVICES,
    "manufacturing": Sector.MANUFACTURING,
    "industrial": Sector.MANUFACTURING,
    "industrials": Sector.MANUFACTURING,
    "retail": Sector.RETAIL,
    "energy": Sector.ENERGY,
}

# Hardcoded metadata for the 5 portfolio companies
# (employee_count and revenue_mm are CS5 additions not in CS1 API)
_COMPANY_ENRICHMENT = {
    "NVDA": {"employee_count": 29600, "revenue_mm": 60922.0, "sector": "technology"},
    "JPM":  {"employee_count": 309926, "revenue_mm": 162400.0, "sector": "financial_services"},
    "WMT":  {"employee_count": 2100000, "revenue_mm": 648125.0, "sector": "retail"},
    "GE":   {"employee_count": 125000, "revenue_mm": 67954.0, "sector": "manufacturing"},
    "DG":   {"employee_count": 195000, "revenue_mm": 38691.0, "sector": "retail"},
}


@dataclass
class Company:
    """Company metadata — matches CS5 PDF Section 1.2."""
    company_id: str
    ticker: str
    name: str
    sector: Sector
    employee_count: int
    revenue_mm: float
    portfolio_entry_date: Optional[str] = None


def _resolve_sector(raw: str) -> Sector:
    key = raw.lower().replace(" ", "_").replace("-", "_")
    return _SECTOR_MAP.get(key, Sector.TECHNOLOGY)


class CS1Client:
    """Client for CS1 Platform APIs (port 8000)."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)

    async def get_company(self, company_id: str) -> Company:
        """
        Fetch a single company by ticker.

        Calls: GET /api/v1/companies/by-ticker/{ticker}
        """
        ticker = company_id.upper()
        response = await self._client.get(
            f"/api/v1/companies/by-ticker/{ticker}"
        )
        response.raise_for_status()
        data = response.json()
        return self._parse(data, ticker)

    async def get_portfolio_companies(
        self, fund_id: str = "growth_fund_v"
    ) -> List[Company]:
        """
        Get all companies in the PE portfolio.

        Returns our 5 CS3 companies: NVDA, JPM, WMT, GE, DG.
        """
        tickers = ["NVDA", "JPM", "WMT", "GE", "DG"]
        companies: List[Company] = []
        for ticker in tickers:
            company = await self.get_company(ticker)
            companies.append(company)
        return companies

    async def close(self):
        await self._client.aclose()

    # ── Internal ────────────────────────────────────────────────

    def _parse(self, data: dict, ticker: str) -> Company:
        ticker = (data.get("ticker") or ticker).upper()
        enrichment = _COMPANY_ENRICHMENT.get(ticker, {})

        raw_sector = data.get("sector", enrichment.get("sector", "technology"))

        return Company(
            company_id=data.get("company_id", data.get("id", ticker)),
            ticker=ticker,
            name=data.get("name", ticker),
            sector=_resolve_sector(raw_sector),
            employee_count=enrichment.get("employee_count", 10000),
            revenue_mm=enrichment.get("revenue_mm", 1000.0),
            portfolio_entry_date=data.get("portfolio_entry_date"),
        )
