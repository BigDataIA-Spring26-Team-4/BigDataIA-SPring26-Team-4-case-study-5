from typing import Any, Dict, List, Optional

from src.mcp.server import MCPServer


class MCPToolCaller:
    def __init__(self, server: Optional[MCPServer] = None):
        self.server = server or MCPServer()

    def get_org_air_score(self, company_id: str) -> Dict[str, Any]:
        return self.server.calculate_org_air_score(company_id)

    def get_evidence(
        self,
        company_id: str,
        dimension: str = "all",
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        return self.server.get_company_evidence(
            company_id=company_id,
            dimension=dimension,
            limit=limit,
        )

    def get_justification(self, company_id: str, dimension: str) -> Dict[str, Any]:
        return self.server.generate_justification(
            company_id=company_id,
            dimension=dimension,
        )

    def get_gap_analysis(self, company_id: str, current_score: float) -> Dict[str, Any]:
        return self.server.run_gap_analysis(
            company_id=company_id,
            current_score=current_score,
        )

    def get_portfolio_summary(self, fund_id: str = "default") -> List[Dict[str, Any]]:
        return self.server.get_portfolio_summary(fund_id=fund_id)

    def project_ebitda_impact(
        self,
        company_id: str,
        base_ebitda: float,
        improvement_pct: float,
    ) -> Dict[str, Any]:
        return self.server.project_ebitda_impact(
            company_id=company_id,
            base_ebitda=base_ebitda,
            improvement_pct=improvement_pct,
        )