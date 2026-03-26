import json
from typing import Any, Dict, List, Optional

from app.services.integration.cs2_client import CS2Client
from app.services.integration.cs3_client import CS3Client
from app.services.integration.cs4_client import CS4Client
from src.services.integration.portfolio_data_service import PortfolioDataService


class MCPServer:
    def __init__(
        self,
        cs2_client: Optional[CS2Client] = None,
        cs3_client: Optional[CS3Client] = None,
        cs4_client: Optional[CS4Client] = None,
        portfolio_data_service: Optional[PortfolioDataService] = None,
    ):
        self.cs2_client = cs2_client or CS2Client()
        self.cs3_client = cs3_client or CS3Client()
        self.cs4_client = cs4_client or CS4Client()
        self.portfolio_data_service = portfolio_data_service or PortfolioDataService()

    def _serialize_dimension_scores(self, dimension_scores: Dict[str, Any]) -> Dict[str, Any]:
        serialized = {}

        for key, value in dimension_scores.items():
            clean_key = getattr(key, "value", str(key))

            if hasattr(value, "score"):
                serialized[clean_key] = {
                    "score": getattr(value, "score", None),
                    "level": int(getattr(value, "level", 0).value) if hasattr(getattr(value, "level", None), "value") else str(getattr(value, "level", "")),
                    "confidence_interval": list(getattr(value, "confidence_interval", [])) if getattr(value, "confidence_interval", None) else [],
                    "evidence_count": getattr(value, "evidence_count", 0),
                    "last_updated": getattr(value, "last_updated", ""),
                }
            else:
                serialized[clean_key] = value

        return serialized

    def calculate_org_air_score(self, company_id: str) -> Dict[str, Any]:
        assessment = self.portfolio_data_service._get_assessment_sync(company_id)

        return {
            "company_id": company_id,
            "org_air_score": assessment.org_air_score,
            "vr_score": assessment.vr_score,
            "hr_score": assessment.hr_score,
            "synergy_score": assessment.synergy_score,
            "dimension_scores": self._serialize_dimension_scores(assessment.dimension_scores),
            "confidence_interval": list(assessment.confidence_interval) if assessment.confidence_interval else [],
        }

    def get_company_evidence(
        self,
        company_id: str,
        dimension: str = "all",
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        evidence = self.cs2_client.get_evidence_for_cs5(
            company_id=company_id,
            dimension=dimension,
            limit=limit,
        )

        results = []
        for item in evidence:
            results.append(
                {
                    "evidence_id": getattr(item, "evidence_id", ""),
                    "company_id": getattr(item, "company_id", company_id),
                    "source_type": str(getattr(item, "source_type", "")),
                    "signal_category": str(getattr(item, "signal_category", "")),
                    "content": getattr(item, "content", ""),
                    "confidence": getattr(item, "confidence", 0.0),
                    "fiscal_year": getattr(item, "fiscal_year", None),
                    "source_url": getattr(item, "source_url", None),
                    "page_number": getattr(item, "page_number", None),
                }
            )
        return results

    def generate_justification(self, company_id: str, dimension: str) -> Dict[str, Any]:
        return self.cs4_client.generate_justification(company_id, dimension)

    def project_ebitda_impact(
        self,
        company_id: str,
        base_ebitda: float,
        improvement_pct: float,
    ) -> Dict[str, Any]:
        projected_impact = base_ebitda * (improvement_pct / 100.0)
        projected_total = base_ebitda + projected_impact

        return {
            "company_id": company_id,
            "base_ebitda": base_ebitda,
            "improvement_pct": improvement_pct,
            "projected_impact": projected_impact,
            "projected_total_ebitda": projected_total,
        }

    def run_gap_analysis(self, company_id: str, current_score: float) -> Dict[str, Any]:
        gaps = []
        initiatives = []

        if current_score < 50:
            gaps.append("Overall Org-AI-R score is in the lagging range")
            initiatives.append("Prioritize foundational AI governance and operating model setup")
            initiatives.append("Establish data platform and enterprise AI roadmap")
        elif current_score < 60:
            gaps.append("Overall Org-AI-R score is below target threshold")
            initiatives.append("Improve AI governance and operating cadence")
            initiatives.append("Strengthen data infrastructure and platform readiness")
        elif current_score < 75:
            gaps.append("Overall Org-AI-R score is moderate with room for improvement")
            initiatives.append("Expand AI talent and value realization programs")
            initiatives.append("Scale priority use cases with stronger executive sponsorship")
        else:
            initiatives.append("Maintain leadership and optimize cross-functional AI scale-up")
            initiatives.append("Focus on monetization, repeatability, and portfolio-wide best practices")

        return {
            "company_id": company_id,
            "current_score": current_score,
            "gaps": gaps,
            "initiatives": initiatives,
        }

    def get_portfolio_summary(self, fund_id: str = "default") -> List[Dict[str, Any]]:
        portfolio = self.portfolio_data_service.get_portfolio_view(fund_id)

        return [
            {
                "ticker": row.ticker,
                "name": row.name,
                "sector": str(row.sector),
                "org_air": row.org_air,
                "vr": row.vr,
                "hr": row.hr,
                "synergy": row.synergy,
                "dimensions": self._serialize_dimension_scores(row.dimensions),
                "confidence_interval": list(row.confidence_interval) if row.confidence_interval else [],
                "delta": row.delta,
                "evidence_count": row.evidence_count,
            }
            for row in portfolio
        ]

    def call_tool(self, tool_name: str, **kwargs) -> str:
        tools = {
            "calculate_org_air_score": self.calculate_org_air_score,
            "get_company_evidence": self.get_company_evidence,
            "generate_justification": self.generate_justification,
            "project_ebitda_impact": self.project_ebitda_impact,
            "run_gap_analysis": self.run_gap_analysis,
            "get_portfolio_summary": self.get_portfolio_summary,
        }

        if tool_name not in tools:
            raise ValueError(f"Unknown tool: {tool_name}")

        result = tools[tool_name](**kwargs)
        return json.dumps(result, indent=2, default=str)