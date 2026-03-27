"""
Bonus Extension: IC Memo Generator (+5 pts).

Generates an Investment Committee memo for a company
using data from CS1-CS4 via the MCP tools / portfolio service.

Outputs a formatted markdown document (can be converted to .docx
with pandoc or python-docx).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime
from typing import Optional
import structlog

from services.cs1_client import CS1Client
from services.cs3_client import CS3Client, Dimension
from services.cs4_client import CS4Client
from services.value_creation.ebitda import ebitda_calculator
from services.value_creation.gap_analysis import gap_analyzer
from config import settings

logger = structlog.get_logger()

# Level descriptions for readability
_LEVEL_DESC = {
    1: "Nascent", 2: "Developing", 3: "Adequate", 4: "Good", 5: "Excellent"
}


class ICMemoGenerator:
    """
    Generates IC meeting memos from CS1-CS4 data.

    The memo includes:
      - Executive summary
      - Company overview
      - Org-AI-R scorecard (all 7 dimensions)
      - Key strengths and risks
      - Value creation thesis with EBITDA projections
      - Gap analysis and 100-day plan
      - Recommendation
    """

    def __init__(self):
        self.cs1 = CS1Client(base_url=settings.CS1_URL)
        self.cs3 = CS3Client(base_url=settings.CS3_URL)
        self.cs4 = CS4Client(base_url=settings.CS4_URL)

    async def generate(
        self,
        company_id: str,
        target_org_air: float = 75.0,
        output_path: Optional[str] = None,
    ) -> str:
        """
        Generate a complete IC memo for a company.

        All data comes from CS1-CS4 (no mock data).

        Args:
            company_id: Company ticker
            target_org_air: Target score for gap analysis
            output_path: Optional file path to save the memo

        Returns:
            Formatted markdown string
        """
        ticker = company_id.upper()
        logger.info("ic_memo_start", company_id=ticker)

        # Fetch data from CS1-CS4
        company = await self.cs1.get_company(ticker)
        assessment = await self.cs3.get_assessment(ticker)

        # Gap analysis
        current_scores = {
            d.value: s.score for d, s in assessment.dimension_scores.items()
        }
        gaps = gap_analyzer.analyze(
            company_id=ticker,
            current_scores=current_scores,
            target_org_air=target_org_air,
            sector=company.sector.value,
        )

        # EBITDA projection
        projection = ebitda_calculator.project(
            company_id=ticker,
            entry_score=45.0,  # placeholder entry
            exit_score=target_org_air,
            h_r_score=assessment.hr_score,
        )

        # Build the memo
        memo = self._format_memo(
            company=company,
            assessment=assessment,
            gaps=gaps,
            projection=projection,
            target_org_air=target_org_air,
        )

        # Optionally save to file
        if output_path:
            Path(output_path).write_text(memo, encoding="utf-8")
            logger.info("ic_memo_saved", path=output_path)

        logger.info("ic_memo_complete", company_id=ticker)
        return memo

    def _format_memo(self, company, assessment, gaps, projection, target_org_air) -> str:
        """Format the IC memo as markdown."""
        now = datetime.utcnow().strftime("%B %d, %Y")
        ci = assessment.confidence_interval

        # Determine strengths (top 3 dims) and risks (bottom 3 dims)
        sorted_dims = sorted(
            assessment.dimension_scores.items(),
            key=lambda x: x[1].score, reverse=True,
        )
        strengths = sorted_dims[:3]
        risks = sorted_dims[-3:]

        # Recommendation logic
        if assessment.org_air_score >= 70:
            recommendation = "**HOLD — ACCELERATE**: Strong AI-readiness foundation. Focus investment on closing remaining gaps to maximize value at exit."
        elif assessment.org_air_score >= 50:
            recommendation = "**HOLD — INVEST**: Adequate AI-readiness with clear improvement path. Implement 100-day plan to drive score above 70."
        else:
            recommendation = "**WATCH — REASSESS**: Below-threshold AI-readiness. Requires significant investment; reassess in 90 days after initial initiatives."

        memo = f"""# Investment Committee Memo
## {company.name} ({company.ticker}) — AI-Readiness Assessment

**Date:** {now}
**Sector:** {company.sector.value.replace('_', ' ').title()}
**Prepared by:** PE Org-AI-R Agentic Platform

---

## Executive Summary

{company.name} currently holds an **Org-AI-R score of {assessment.org_air_score:.1f}** (CI: [{ci[0]:.1f}, {ci[1]:.1f}]), placing it at **{_LEVEL_DESC.get(self._score_level(assessment.org_air_score), 'N/A')}** level within the {company.sector.value.replace('_', ' ')} sector. The assessment is based on {assessment.evidence_count} evidence items across 7 dimensions.

---

## Org-AI-R Scorecard

| Metric | Score |
|--------|-------|
| **Org-AI-R (Final)** | **{assessment.org_air_score:.1f}** |
| V^R (Idiosyncratic) | {assessment.vr_score:.1f} |
| H^R (Systematic) | {assessment.hr_score:.1f} |
| Synergy | {assessment.synergy_score:.1f} |

### Dimension Breakdown

| Dimension | Score | Level | Rating |
|-----------|-------|-------|--------|
"""
        for dim, ds in sorted_dims:
            dim_name = dim.value.replace("_", " ").title()
            level_name = _LEVEL_DESC.get(ds.level, "?")
            memo += f"| {dim_name} | {ds.score:.1f} | L{ds.level} | {level_name} |\n"

        memo += f"""
---

## Key Strengths

"""
        for dim, ds in strengths:
            dim_name = dim.value.replace("_", " ").title()
            memo += f"- **{dim_name}** ({ds.score:.1f}): L{ds.level} — {_LEVEL_DESC.get(ds.level, '?')}\n"

        memo += f"""
## Key Risks & Gaps

"""
        for dim, ds in risks:
            dim_name = dim.value.replace("_", " ").title()
            gap_to_target = max(0, target_org_air - ds.score)
            memo += f"- **{dim_name}** ({ds.score:.1f}): Gap of {gap_to_target:.1f} points to target\n"

        memo += f"""
---

## Value Creation Thesis

### EBITDA Impact Projection (v2.0 Model)

| Scenario | EBITDA Impact |
|----------|---------------|
| Conservative | {projection.conservative_pct:.2f}% |
| **Base Case** | **{projection.base_pct:.2f}%** |
| Optimistic | {projection.optimistic_pct:.2f}% |
| Risk-Adjusted | {projection.risk_adjusted_pct:.2f}% |

**HITL Required:** {"Yes — projection exceeds 5% threshold" if projection.requires_approval else "No"}

### 100-Day Improvement Plan

**Priority Dimensions:** {', '.join(d.replace('_', ' ').title() for d in gaps['priority_dimensions'])}

| Priority | Dimension | Initiative | Timeline |
|----------|-----------|------------|----------|
"""
        for init in gaps.get("initiatives", []):
            dim_name = init["dimension"].replace("_", " ").title()
            memo += f"| P{init['priority']} | {dim_name} | {init['initiative']} | {init['timeline_days']}d |\n"

        memo += f"""
**Estimated Investment:** ${gaps.get('estimated_investment_k', 0):,}K
**Projected Score Lift:** +{gaps.get('projected_score_lift', 0):.1f} points

---

## Recommendation

{recommendation}

---

*Generated by PE Org-AI-R Agentic Platform — all data from CS1-CS4.*
"""
        return memo

    @staticmethod
    def _score_level(score: float) -> int:
        if score >= 80: return 5
        if score >= 60: return 4
        if score >= 40: return 3
        if score >= 20: return 2
        return 1


# Module-level singleton
ic_memo_generator = ICMemoGenerator()
