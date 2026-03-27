import requests
from typing import Any, Dict, List


class CS4Client:
    def __init__(self, base_url: str = "http://localhost:8003"):
        self.base_url = base_url

    def generate_justification(self, company_id: str, dimension: str) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/justification/{company_id}/{dimension}"
        response = requests.get(url)
        response.raise_for_status()
        return response.json()

    def generate_justification_with_evidence(
        self,
        company_id: str,
        dimension: str,
        evidence: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        base = self.generate_justification(company_id, dimension)

        filtered = self._filter_evidence_for_dimension(evidence, dimension)
        supporting_evidence = self._build_supporting_evidence(filtered, limit=5)

        base["supporting_evidence"] = supporting_evidence

        evidence_count = len(supporting_evidence)

        if evidence_count >= 5:
            evidence_strength = "strong"
            note = "Strong evidence supports this assessment"
        elif evidence_count >= 2:
            evidence_strength = "moderate"
            note = "Moderate evidence supports this assessment"
        else:
            evidence_strength = "weak"
            note = "Limited evidence found"

        if supporting_evidence:
            snippets = [item["snippet"] for item in supporting_evidence[:2]]
            joined = " | ".join(snippets)
            summary = base.get("generated_summary", "")
            if joined not in summary:
                base["generated_summary"] = f"{summary} Supporting evidence: {joined}"

        return base

    def _filter_evidence_for_dimension(
        self,
        evidence: List[Dict[str, Any]],
        dimension: str,
    ) -> List[Dict[str, Any]]:
        keywords_by_dimension = {
            "data_infrastructure": [
                "data", "cloud", "platform", "infrastructure", "gpu",
                "dgx", "cuda", "data center", "analytics", "api",
                "lakehouse", "streaming", "real-time",
            ],
            "ai_governance": [
                "governance", "risk", "controls", "compliance",
                "policy", "audit", "oversight",
            ],
            "technology_stack": [
                "software", "platform", "stack", "framework",
                "sdk", "library", "architecture", "system",
            ],
            "talent": [
                "talent", "hiring", "skills", "engineers",
                "researchers", "developers", "training",
            ],
            "leadership": [
                "strategy", "leadership", "management",
                "executive", "vision", "investment", "innovation",
            ],
            "use_case_portfolio": [
                "use case", "applications", "customers",
                "products", "solutions", "automation",
            ],
            "culture": [
                "culture", "adoption", "developers",
                "ecosystem", "community", "collaboration",
            ],
        }

        dim_keywords = keywords_by_dimension.get(dimension, [])
        ranked = []

        for item in evidence:
            text = getattr(item, "content", "")
            if text:
                text = text.lower()
            matches = sum(1 for kw in dim_keywords if kw in text)
            if matches > 0:
                ranked.append((matches, item))

        ranked.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in ranked]

    def _build_supporting_evidence(
        self,
        evidence: List[Dict[str, Any]],
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        results = []

        for item in evidence[:limit]:
            text = getattr(item, "content", "") or ""
            text = text.strip()

            snippet = text[:300].replace("\n", " ")

            results.append(
                {
                    "evidence_id": getattr(item, "evidence_id", ""),
                    "company_id": getattr(item, "company_id", ""),
                    "source_type": getattr(item, "source_type", None),
                    "signal_category": getattr(item, "signal_category", None),
                    "confidence": getattr(item, "confidence", None),
                    "fiscal_year": getattr(item, "fiscal_year", None),
                    "snippet": snippet,
                }
            )
        return results