"""
Investment Committee meeting preparation workflow.

Task 8.0c: IC Meeting Prep — automates the full evidence package
analysts need before presenting to the Investment Committee.

For each company, generates:
  - Justifications for all 7 dimensions (or a focused subset)
  - Executive summary paragraph
  - Top 3 strengths (Level 4+ with evidence)
  - Critical gaps (Level 2 or below)
  - Risk factors (talent concentration, weak evidence, negative position)
  - Investment recommendation (PROCEED / CAUTION / FURTHER DILIGENCE)

Uses asyncio.gather() for parallel justification generation.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

import structlog

from src.config import CS4Settings, get_cs4_settings
from src.services.integration.cs1_client import CS1Client, Company
from src.services.integration.cs3_client import (
    CS3Client,
    CompanyAssessment,
    Dimension,
)
from src.services.justification.generator import (
    JustificationGenerator,
    ScoreJustification,
)

logger = structlog.get_logger()


# ============================================================================
# IC Meeting Package
# ============================================================================


@dataclass
class ICMeetingPackage:
    """Complete IC meeting preparation package."""
    company: Company
    assessment: CompanyAssessment
    dimension_justifications: Dict[Dimension, ScoreJustification]

    executive_summary: str
    key_strengths: List[str]
    key_gaps: List[str]
    risk_factors: List[str]
    recommendation: str

    generated_at: str
    total_evidence_count: int
    avg_evidence_strength: str


# ============================================================================
# IC Prep Workflow
# ============================================================================


class ICPrepWorkflow:
    """
    Prepare complete IC meeting evidence package.

    Orchestrates CS1 (company) → CS3 (scores) → CS4 (justifications)
    into a single coherent package for investment committee review.

    Usage:
        workflow = ICPrepWorkflow()
        package = await workflow.prepare_meeting("NVDA")
    """

    def __init__(
        self,
        cs1: CS1Client = None,
        cs3: CS3Client = None,
        generator: JustificationGenerator = None,
        settings: CS4Settings = None,
    ):
        self._settings = settings or get_cs4_settings()
        self._cs1 = cs1 or CS1Client(base_url=self._settings.cs3_api_url)
        self._cs3 = cs3 or CS3Client(base_url=self._settings.cs3_api_url)
        self._generator = generator or JustificationGenerator(
            cs3=self._cs3, settings=self._settings
        )

    @property
    def generator(self) -> JustificationGenerator:
        """Access the justification generator (for indexing from outside)."""
        return self._generator

    async def prepare_meeting(
        self,
        company_id: str,
        focus_dimensions: Optional[List[Dimension]] = None,
    ) -> ICMeetingPackage:
        """
        Generate complete IC meeting package.

        Args:
            company_id: Company ticker (e.g. "NVDA")
            focus_dimensions: Subset of dimensions to analyze.
                              Defaults to all 7 dimensions.

        Returns:
            ICMeetingPackage with justifications, summary, and recommendation.
        """
        ticker = company_id.upper()
        if focus_dimensions is None:
            focus_dimensions = list(Dimension)

        logger.info(
            "ic_prep_started",
            company=ticker,
            dimensions=len(focus_dimensions),
        )

        # 1. Fetch company from CS1
        company = await self._cs1.get_company(ticker)

        # 2. Fetch assessment from CS3
        assessment = await self._cs3.get_assessment(ticker)

        # 3. Generate justifications for each dimension (parallel)
        justifications = await self._generate_all_justifications(
            ticker, focus_dimensions
        )

        # 4. Synthesize findings
        strengths = self._identify_strengths(assessment, justifications)
        gaps = self._identify_gaps(justifications)
        risks = self._assess_risks(assessment, justifications)

        # 5. Generate executive summary
        summary = self._generate_summary(company, assessment, justifications)

        # 6. Generate recommendation
        recommendation = self._generate_recommendation(
            assessment, strengths, gaps
        )

        # 7. Calculate stats
        total_evidence = sum(
            len(j.supporting_evidence) for j in justifications.values()
        )
        avg_strength = self._average_strength(justifications)

        package = ICMeetingPackage(
            company=company,
            assessment=assessment,
            dimension_justifications=justifications,
            executive_summary=summary,
            key_strengths=strengths,
            key_gaps=gaps,
            risk_factors=risks,
            recommendation=recommendation,
            generated_at=datetime.now().isoformat(),
            total_evidence_count=total_evidence,
            avg_evidence_strength=avg_strength,
        )

        logger.info(
            "ic_prep_completed",
            company=ticker,
            dimensions=len(justifications),
            evidence=total_evidence,
            recommendation=recommendation,
        )
        return package

    # ── Parallel Justification ──────────────────────────────────

    async def _generate_all_justifications(
        self,
        company_id: str,
        dimensions: List[Dimension],
    ) -> Dict[Dimension, ScoreJustification]:
        """Generate justifications for all dimensions in parallel."""
        tasks = [
            self._generator.generate_justification(company_id, dim)
            for dim in dimensions
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        justifications = {}
        for dim, result in zip(dimensions, results):
            if isinstance(result, Exception):
                logger.warning(
                    "justification_failed",
                    company=company_id,
                    dimension=dim.value,
                    error=str(result),
                )
                continue
            justifications[dim] = result

        return justifications

    # ── Strengths ───────────────────────────────────────────────

    @staticmethod
    def _identify_strengths(
        assessment: CompanyAssessment,
        justifications: Dict[Dimension, ScoreJustification],
    ) -> List[str]:
        """
        Identify top 3 strengths.

        Criteria: Level 4+ with strong or moderate evidence.
        """
        strengths = []
        for dim, j in justifications.items():
            if j.level >= 4 and j.evidence_strength in ("strong", "moderate"):
                dim_name = dim.value.replace("_", " ").title()
                strengths.append(
                    f"{dim_name}: Level {j.level} ({j.level_name}) "
                    f"— {len(j.supporting_evidence)} evidence items, "
                    f"{j.evidence_strength} support"
                )

        # Sort by level descending
        strengths.sort(key=lambda x: -int(x.split("Level ")[1][0]))
        return strengths[:3]

    # ── Gaps ────────────────────────────────────────────────────

    @staticmethod
    def _identify_gaps(
        justifications: Dict[Dimension, ScoreJustification],
    ) -> List[str]:
        """
        Identify critical gaps across dimensions.

        Criteria: Level 2 or below needs investment.
        Also includes top gaps from individual justifications.
        """
        gaps = []
        for dim, j in justifications.items():
            dim_name = dim.value.replace("_", " ").title()
            if j.level <= 2:
                gaps.append(
                    f"{dim_name}: Level {j.level} ({j.level_name}) "
                    f"— needs investment"
                )
            # Add dimension-specific gaps
            for gap in j.gaps_identified[:2]:
                gaps.append(gap)

        return gaps[:5]

    # ── Risks ───────────────────────────────────────────────────

    @staticmethod
    def _assess_risks(
        assessment: CompanyAssessment,
        justifications: Dict[Dimension, ScoreJustification],
    ) -> List[str]:
        """Assess execution risks based on scores and evidence."""
        risks = []

        # Talent concentration risk
        if assessment.talent_concentration > 0.25:
            risks.append(
                f"High talent concentration "
                f"({assessment.talent_concentration:.2f}) — key person risk"
            )

        # Weak evidence dimensions
        weak_dims = [
            dim for dim, j in justifications.items()
            if j.evidence_strength == "weak"
        ]
        if weak_dims:
            dim_names = ", ".join(d.value.replace("_", " ") for d in weak_dims)
            risks.append(f"Weak evidence for: {dim_names}")

        # Below-average sector position
        if assessment.position_factor < 0:
            risks.append(
                f"Below-average sector position "
                f"(factor={assessment.position_factor:.2f})"
            )

        # Low overall evidence count
        total_evidence = sum(
            len(j.supporting_evidence) for j in justifications.values()
        )
        if total_evidence < 5:
            risks.append(
                f"Limited evidence base ({total_evidence} items total)"
            )

        return risks[:5]

    # ── Executive Summary ───────────────────────────────────────

    @staticmethod
    def _generate_summary(
        company: Company,
        assessment: CompanyAssessment,
        justifications: Dict[Dimension, ScoreJustification],
    ) -> str:
        """Generate executive summary paragraph."""
        strong_dims = [
            d for d, j in justifications.items() if j.level >= 4
        ]
        weak_dims = [
            d for d, j in justifications.items() if j.level <= 2
        ]

        parts = [
            f"{company.name} ({company.ticker}) scores "
            f"{assessment.org_air_score:.0f} on Org-AI-R "
            f"({assessment.confidence_interval[0]:.0f}-"
            f"{assessment.confidence_interval[1]:.0f} 95% CI). "
            f"VR={assessment.vr_score:.0f}, HR={assessment.hr_score:.0f}.",
        ]

        if strong_dims:
            names = ", ".join(
                d.value.replace("_", " ") for d in strong_dims[:2]
            )
            parts.append(f"Strengths in {names}.")

        if weak_dims:
            names = ", ".join(
                d.value.replace("_", " ") for d in weak_dims[:2]
            )
            parts.append(f"Gaps in {names}.")

        parts.append(
            f"Position factor: {assessment.position_factor:+.2f} vs sector peers."
        )

        return " ".join(parts)

    # ── Recommendation ──────────────────────────────────────────

    @staticmethod
    def _generate_recommendation(
        assessment: CompanyAssessment,
        strengths: List[str],
        gaps: List[str],
    ) -> str:
        """
        Generate investment recommendation.

        PROCEED:          org_air >= 70 AND 2+ strengths
        PROCEED W/CAUTION: org_air >= 50
        FURTHER DILIGENCE: below 50
        """
        if assessment.org_air_score >= 70 and len(strengths) >= 2:
            return "PROCEED — Strong AI readiness with solid evidence base"
        elif assessment.org_air_score >= 50:
            return "PROCEED WITH CAUTION — Moderate AI readiness, gaps addressable"
        else:
            return "FURTHER DILIGENCE — Significant AI capability gaps identified"

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _average_strength(
        justifications: Dict[Dimension, ScoreJustification],
    ) -> str:
        """Calculate average evidence strength across dimensions."""
        if not justifications:
            return "weak"

        strength_scores = {"strong": 3, "moderate": 2, "weak": 1}
        total = sum(
            strength_scores.get(j.evidence_strength, 1)
            for j in justifications.values()
        )
        avg = total / len(justifications)

        if avg >= 2.5:
            return "strong"
        elif avg >= 1.5:
            return "moderate"
        return "weak"
