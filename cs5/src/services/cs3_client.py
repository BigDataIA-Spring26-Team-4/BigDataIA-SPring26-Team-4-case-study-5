from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import httpx

class CS3Client:
    """Client for interacting with the CS3 service."""

    def __init__(self, base_url: str):
        self.base_url = base_url

    async def get_assessment(self, company_ticker: str) -> dict:
        """Fetch ESG assessment data for a company by ID."""
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{self.base_url}/api/v1/pipeline/score", json={"ticker": company_ticker})
        return response.json()

