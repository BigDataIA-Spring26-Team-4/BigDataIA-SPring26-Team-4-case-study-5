from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import httpx

class CS1Client:
    """Client for interacting with the CS1 service."""

    def __init__(self, base_url: str):
        self.base_url = base_url

    async def get_company(self, company_id: str) -> dict:
        """Fetch company data by ID."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/api/v1/companies/{company_id}")
        response.raise_for_status()
        return response.json()

    async def get_companies(self) -> List[dict]:
        """Fetch a list of all companies."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/api/v1/companies")
        response.raise_for_status()
        return response.json()["items"]

    async def get_company_industry(self, company_id: str) -> str:
        """Fetch the industry of a company by ID."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/api/v1/companies/{company_id}")
            response.raise_for_status()
            industry_id = response.json().get("industry_id")
            if industry_id:
                industry_response = await client.get(f"{self.base_url}/api/v1/industries/{industry_id}")
                industry_response.raise_for_status()
                return industry_response.json().get("name", "Unknown")
        return "Unknown"
