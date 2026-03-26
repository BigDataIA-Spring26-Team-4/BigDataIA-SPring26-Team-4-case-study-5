import requests
from typing import Dict, Any


class CS4Client:
    def __init__(self, base_url: str = "http://localhost:8003"):
        self.base_url = base_url

    def generate_justification(self, company_id: str, dimension: str) -> Dict[str, Any]:
        """
        Calls CS4 justification endpoint
        """
        url = f"{self.base_url}/api/v1/justification/{company_id}/{dimension}"
        response = requests.get(url)

        if response.status_code != 200:
            raise ValueError(f"CS4 justification failed: {response.text}")

        return response.json()

    def search_evidence(self, query: str, company_id: str, dimension: str) -> Dict[str, Any]:
        """
        Calls CS4 search endpoint
        """
        url = f"{self.base_url}/api/v1/search"
        params = {
            "query": query,
            "company_id": company_id,
            "dimension": dimension
        }

        response = requests.get(url, params=params)

        if response.status_code != 200:
            raise ValueError(f"CS4 search failed: {response.text}")

        return response.json()

    def prepare_ic_meeting(self, company_id: str) -> Dict[str, Any]:
        """
        Calls CS4 IC prep endpoint
        """
        url = f"{self.base_url}/api/v1/ic-prep/{company_id}"
        response = requests.get(url)

        if response.status_code != 200:
            raise ValueError(f"CS4 IC prep failed: {response.text}")

        return response.json()