from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import httpx

class CS2Client:
    """Client for interacting with the CS2 service."""

    def __init__(self, base_url: str):
        self.base_url = base_url

    async def get_evidence(self, company_id: str) -> dict:
        """Fetch ESG evidence data for a company by ID."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/api/v1/evidence/companies/{company_id}")
        response.raise_for_status()
        return response.json()
