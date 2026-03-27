"""
Task 9.2 (tool #5): Gap Analyzer.

Analyzes gaps between current dimension scores and targets,
generates a 100-day improvement plan with prioritized initiatives.

Used by MCP tool: run_gap_analysis
"""

from typing import Dict, List
import structlog

logger = structlog.get_logger()


# Sector-specific benchmarks for gap severity
SECTOR_BENCHMARKS = {
    "technology":          {"data_infrastructure": 75, "ai_governance": 65, "technology_stack": 80, "talent": 75, "leadership": 70, "use_case_portfolio": 70, "culture": 65},
    "healthcare":          {"data_infrastructure": 60, "ai_governance": 70, "technology_stack": 60, "talent": 60, "leadership": 65, "use_case_portfolio": 55, "culture": 55},
    "financial_services":  {"data_infrastructure": 70, "ai_governance": 75, "technology_stack": 70, "talent": 65, "leadership": 70, "use_case_portfolio": 60, "culture": 60},
    "manufacturing":       {"data_infrastructure": 55, "ai_governance": 55, "technology_stack": 60, "talent": 55, "leadership": 55, "use_case_portfolio": 50, "culture": 50},
    "retail":              {"data_infrastructure": 55, "ai_governance": 50, "technology_stack": 55, "talent": 50, "leadership": 50, "use_case_portfolio": 50, "culture": 50},
    "energy":              {"data_infrastructure": 50, "ai_governance": 50, "technology_stack": 50, "talent": 45, "leadership": 45, "use_case_portfolio": 45, "culture": 45},
}

# Predefined initiative templates by dimension
_INITIATIVE_TEMPLATES = {
    "data_infrastructure": [
        "Implement enterprise data lake with governance layer",
        "Deploy data quality monitoring pipeline",
        "Migrate legacy systems to cloud-native architecture",
    ],
    "ai_governance": [
        "Establish AI ethics review board",
        "Implement model risk management framework",
        "Create responsible AI policy documentation",
    ],
    "technology_stack": [
        "Upgrade ML infrastructure (MLOps pipeline)",
        "Deploy feature store for model serving",
        "Modernize API layer for AI integration",
    ],
    "talent": [
        "Launch AI/ML upskilling program for engineers",
        "Hire senior ML engineering lead",
        "Partner with university AI research lab",
    ],
    "leadership": [
        "Appoint Chief AI Officer or AI Strategy Lead",
        "Board-level AI committee quarterly reviews",
        "Executive AI literacy program",
    ],
    "use_case_portfolio": [
        "Identify top-3 AI use cases by ROI potential",
        "Pilot AI project in highest-impact business unit",
        "Build AI use case scoring framework",
    ],
    "culture": [
        "Run AI innovation hackathon",
        "Establish data-driven decision-making KPIs",
        "Create cross-functional AI champions network",
    ],
}


class GapAnalyzer:
    """
    Analyzes gaps between current scores and target,
    generates prioritized 100-day improvement plan.

    Used by the MCP run_gap_analysis tool.
    All scoring data comes from CS3 via the MCP server.
    """

    def analyze(
        self,
        company_id: str,
        current_scores: Dict[str, float],
        target_org_air: float,
        sector: str = "technology",
    ) -> dict:
        """
        Analyze gaps and generate improvement plan.

        Args:
            company_id: Company ticker
            current_scores: Dict of dimension → current score (from CS3)
            target_org_air: Target overall Org-AI-R score
            sector: Company sector for benchmark comparison

        Returns:
            dict with gaps, priorities, initiatives, investment estimate
        """
        benchmarks = SECTOR_BENCHMARKS.get(sector, SECTOR_BENCHMARKS["technology"])

        # Calculate current average
        current_avg = sum(current_scores.values()) / max(len(current_scores), 1)

        # Calculate gap per dimension
        dimension_gaps: List[dict] = []
        for dim, score in current_scores.items():
            benchmark = benchmarks.get(dim, 60)
            # Gap to target is proportional: each dim should reach
            # a level that lifts the overall average to target_org_air
            gap_to_benchmark = max(0, benchmark - score)
            gap_to_target = max(0, target_org_air - score)

            severity = self._classify_severity(gap_to_benchmark)

            dimension_gaps.append({
                "dimension": dim,
                "current_score": round(score, 1),
                "benchmark": benchmark,
                "gap_to_benchmark": round(gap_to_benchmark, 1),
                "gap_to_target": round(gap_to_target, 1),
                "severity": severity,
            })

        # Sort by gap severity (largest gap first)
        dimension_gaps.sort(key=lambda g: g["gap_to_target"], reverse=True)

        # Priority ranking — top 3 dimensions with largest gaps
        priorities = [g["dimension"] for g in dimension_gaps[:3]]

        # Generate initiatives for priority dimensions
        initiatives: List[dict] = []
        for i, dim in enumerate(priorities):
            templates = _INITIATIVE_TEMPLATES.get(dim, ["General improvement initiative"])
            for j, initiative in enumerate(templates[:2]):  # 2 initiatives per priority dim
                initiatives.append({
                    "priority": i + 1,
                    "dimension": dim,
                    "initiative": initiative,
                    "timeline_days": 30 * (i + 1),  # 30d, 60d, 90d
                    "estimated_score_lift": round(5.0 + (3 - i) * 2.0, 1),
                })

        # Investment estimate (rough: $50K-$200K per initiative)
        total_investment_k = len(initiatives) * 125  # avg $125K per initiative

        # Projected EBITDA impact (simplified)
        projected_lift = sum(init["estimated_score_lift"] for init in initiatives)
        projected_ebitda_pct = round(projected_lift * 0.10, 2)  # ~0.1% per point

        result = {
            "company_id": company_id,
            "current_org_air": round(current_avg, 1),
            "target_org_air": target_org_air,
            "overall_gap": round(max(0, target_org_air - current_avg), 1),
            "dimension_gaps": dimension_gaps,
            "priority_dimensions": priorities,
            "initiatives": initiatives,
            "projected_score_lift": round(projected_lift, 1),
            "projected_ebitda_pct": projected_ebitda_pct,
            "estimated_investment_k": total_investment_k,
            "plan_horizon_days": 100,
        }

        logger.info(
            "gap_analysis_complete",
            company_id=company_id,
            overall_gap=result["overall_gap"],
            priorities=priorities,
        )

        return result

    @staticmethod
    def _classify_severity(gap: float) -> str:
        """Classify gap severity."""
        if gap >= 20:
            return "critical"
        elif gap >= 10:
            return "major"
        elif gap > 0:
            return "minor"
        return "none"


# Module-level singleton (per PDF v4 FIX)
gap_analyzer = GapAnalyzer()
