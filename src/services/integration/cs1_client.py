"""
CS1 Platform API client for company data.

Task 7.0a: Connect to CS1 Platform API.
CS1 provides company metadata needed for:
  - Filtering searches by portfolio companies
  - Getting sector for position_factor calculation
  - Fetching market_cap_percentile for peer comparison

Wraps the existing FastAPI company endpoints via async HTTP.
Falls back to local results/*.json files when the API is unavailable.
"""

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional

import httpx
import structlog

logger = structlog.get_logger()


# ============================================================================
# Enums & Dataclasses (per CS4 PDF Section 2)
# ============================================================================


class Sector(str, Enum):
    """Industry sectors for PE portfolio companies."""
    TECHNOLOGY = "technology"
    FINANCIAL_SERVICES = "financial_services"
    HEALTHCARE = "healthcare"
    MANUFACTURING = "manufacturing"
    RETAIL = "retail"
    BUSINESS_SERVICES = "business_services"
    CONSUMER = "consumer"


@dataclass
class Company:
    """Company metadata from CS1 Platform."""
    company_id: str
    ticker: str
    name: str
    sector: Sector
    sub_sector: str
    market_cap_percentile: float   # 0-1, derived from position_factor
    position_factor: float         # -1 to 1, raw from CS3


@dataclass
class Portfolio:
    """PE portfolio from CS1."""
    portfolio_id: str
    name: str
    company_ids: List[str]
    fund_vintage: int


# ============================================================================
# Sector Mapping (CS3 industry names → CS4 Sector enum)
# ============================================================================

_SECTOR_MAP = {
    "technology": Sector.TECHNOLOGY,
    "semiconductors": Sector.TECHNOLOGY,
    "financial_services": Sector.FINANCIAL_SERVICES,
    "financial": Sector.FINANCIAL_SERVICES,
    "banking": Sector.FINANCIAL_SERVICES,
    "healthcare": Sector.HEALTHCARE,
    "manufacturing": Sector.MANUFACTURING,
    "industrial": Sector.MANUFACTURING,
    "industrials": Sector.MANUFACTURING,
    "aerospace": Sector.MANUFACTURING,
    "retail": Sector.RETAIL,
    "consumer": Sector.CONSUMER,
    "consumer_discretionary": Sector.CONSUMER,
    "business_services": Sector.BUSINESS_SERVICES,
}

# Fallback metadata for the 5 portfolio companies
# Used when API fields are unavailable
_COMPANY_DEFAULTS = {
    "NVDA": {"sector": "technology", "sub_sector": "Semiconductors"},
    "JPM": {"sector": "financial_services", "sub_sector": "Banking"},
    "WMT": {"sector": "retail", "sub_sector": "Discount Stores"},
    "GE": {"sector": "manufacturing", "sub_sector": "Industrial Conglomerates"},
    "DG": {"sector": "retail", "sub_sector": "Discount Stores"},
}


def _resolve_sector(raw: str) -> Sector:
    """Map a raw sector/industry string to the Sector enum."""
    key = raw.lower().replace(" ", "_").replace("-", "_")
    return _SECTOR_MAP.get(key, Sector.BUSINESS_SERVICES)


# ============================================================================
# CS1 Client
# ============================================================================


class CS1Client:
    """
    Client for CS1 Platform API (company metadata).

    Connects to the existing FastAPI app at the given base_url.
    When the API is unavailable, falls back to local results/*.json.
    """

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)

    # ── Core API Methods ────────────────────────────────────────

    async def get_company(self, ticker: str) -> Company:
        """
        Fetch company by ticker symbol.

        Calls: GET /api/v1/companies/by-ticker/{ticker}
        Falls back to local results/{ticker}.json on failure.
        """
        try:
            response = await self.client.get(
                f"{self.base_url}/api/v1/companies/by-ticker/{ticker.upper()}"
            )
            response.raise_for_status()
            data = response.json()
            return self._parse_company(data, ticker)

        except (httpx.HTTPError, httpx.ConnectError) as e:
            logger.warning("cs1_api_unavailable", ticker=ticker, error=str(e))
            return self._load_from_local(ticker)

    async def list_companies(
        self,
        sector: Optional[Sector] = None,
    ) -> List[Company]:
        """
        List companies with optional sector filter.

        Calls: GET /api/v1/companies
        """
        try:
            params = {"page_size": 100}
            response = await self.client.get(
                f"{self.base_url}/api/v1/companies",
                params=params,
            )
            response.raise_for_status()
            data = response.json()

            companies = []
            for item in data.get("items", []):
                try:
                    company = self._parse_company(item, item.get("ticker", ""))
                    if sector is None or company.sector == sector:
                        companies.append(company)
                except Exception:
                    continue
            return companies

        except (httpx.HTTPError, httpx.ConnectError) as e:
            logger.warning("cs1_api_unavailable_list", error=str(e))
            return self._load_all_local(sector)

    async def get_portfolio_companies(
        self,
        portfolio_id: str = "default",
    ) -> List[Company]:
        """
        Get all companies in the PE portfolio.

        For the default portfolio, returns all 5 CS3 companies.
        """
        tickers = ["NVDA", "JPM", "WMT", "GE", "DG"]
        companies = []
        for ticker in tickers:
            try:
                companies.append(await self.get_company(ticker))
            except Exception as e:
                logger.warning("portfolio_company_failed", ticker=ticker, error=str(e))
        return companies

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    # ── Parsing & Fallback ──────────────────────────────────────

    def _parse_company(self, data: dict, ticker: str) -> Company:
        """Parse API response into Company dataclass."""
        ticker = (data.get("ticker") or ticker).upper()
        defaults = _COMPANY_DEFAULTS.get(ticker, {})

        raw_sector = data.get("sector", defaults.get("sector", "business_services"))
        position_factor = float(data.get("position_factor", 0.0))

        return Company(
            company_id=data.get("company_id", data.get("id", "")),
            ticker=ticker,
            name=data.get("name", ticker),
            sector=_resolve_sector(raw_sector),
            sub_sector=data.get("sub_sector", defaults.get("sub_sector", raw_sector)),
            market_cap_percentile=data.get(
                "market_cap_percentile",
                max(0.0, min(1.0, (position_factor + 1) / 2)),
            ),
            position_factor=position_factor,
        )

    def _load_from_local(self, ticker: str) -> Company:
        """
        Fallback: load company data from results/{ticker}.json.

        This allows CS4 to function during development even when
        the CS3 API is not running.
        """
        ticker = ticker.upper()
        results_path = Path("results") / f"{ticker.lower()}.json"

        if results_path.exists():
            with open(results_path) as f:
                data = json.load(f)

            defaults = _COMPANY_DEFAULTS.get(ticker, {})
            raw_sector = data.get("sector", defaults.get("sector", "business_services"))
            position_factor = float(data.get("position_factor", 0.0))

            return Company(
                company_id=ticker,
                ticker=ticker,
                name={"NVDA": "NVIDIA", "JPM": "JPMorgan Chase", "WMT": "Walmart",
                       "GE": "GE Aerospace", "DG": "Dollar General"}.get(ticker, ticker),
                sector=_resolve_sector(raw_sector),
                sub_sector=defaults.get("sub_sector", raw_sector),
                market_cap_percentile=max(0.0, min(1.0, (position_factor + 1) / 2)),
                position_factor=position_factor,
            )

        raise ValueError(f"No data available for ticker '{ticker}'")

    def _load_all_local(self, sector: Optional[Sector] = None) -> List[Company]:
        """Fallback: load all companies from local results/*.json."""
        companies = []
        for ticker in _COMPANY_DEFAULTS:
            try:
                company = self._load_from_local(ticker)
                if sector is None or company.sector == sector:
                    companies.append(company)
            except Exception:
                continue
        return companies
