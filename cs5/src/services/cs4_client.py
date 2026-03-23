from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import httpx

class CS4Client:
    """Client for interacting with the CS4 service."""

    def __init__(self, base_url: str):
        self.base_url = base_url

    async def get_justification(self, company_id: str, dimension: str) -> dict:
        """Fetch justification for a specific dimension of a company's Org-AIR score."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/api/v1/justifications/{company_id}/{dimension}")
        return response.json()
