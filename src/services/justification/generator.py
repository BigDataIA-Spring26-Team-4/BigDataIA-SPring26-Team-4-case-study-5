"""
Generate score justifications with cited evidence.

Task 8.0b: Score Justification Generator — the core PE use case.

IC Member: "Why did TechCorp score 72 on Data Infrastructure?"

Pipeline:
  1. Fetch dimension score from CS3
  2. Fetch rubric criteria for that level (keywords, thresholds)
  3. Build search query from rubric keywords
  4. Hybrid search for evidence (filtered by company + dimension)
  5. Match evidence to rubric keywords
  6. Identify gaps (next-level criteria not found in evidence)
  7. Generate LLM summary in PE memo style
  8. Assess evidence strength (strong / moderate / weak)

Output: ScoreJustification with cited evidence, gaps, and strength.
"""

from dataclasses import dataclass, field
from typing import List, Optional

import structlog

from src.config import CS4Settings, get_cs4_settings
from src.services.integration.cs3_client import (
    CS3Client,
    Dimension,
    DimensionScore,
    RubricCriteria,
    ScoreLevel,
)
from src.services.retrieval.hybrid import HybridRetriever, RetrievedDocument
from src.services.llm.router import ModelRouter, TaskType

logger = structlog.get_logger()


# ============================================================================
# Dataclasses
# ============================================================================


@dataclass
class CitedEvidence:
    """Evidence with citation details for IC presentation."""
    evidence_id: str
    content: str            # Truncated to 500 chars
    source_type: str
    source_url: Optional[str]
    confidence: float
    matched_keywords: List[str]
    relevance_score: float


@dataclass
class ScoreJustification:
    """Complete score justification for IC presentation."""
    company_id: str
    dimension: Dimension
    score: float
    level: int
    level_name: str
    confidence_interval: tuple

    rubric_criteria: str
    rubric_keywords: List[str]

    supporting_evidence: List[CitedEvidence]
    gaps_identified: List[str]

    generated_summary: str
    evidence_strength: str   # "strong", "moderate", "weak"


# ============================================================================
# Justification Prompt
# ============================================================================


JUSTIFICATION_PROMPT = """You are a PE analyst preparing score justification for an investment committee.

COMPANY: {company_id}
DIMENSION: {dimension}
SCORE: {score}/100 (Level {level} - {level_name})

RUBRIC CRITERIA FOR THIS LEVEL:
{rubric_criteria}

RUBRIC KEYWORDS TO MATCH:
{rubric_keywords}

SUPPORTING EVIDENCE FOUND:
{evidence_text}

Generate a concise IC-ready justification (150-200 words) that:
1. States why the score matches this rubric level
2. Cites specific evidence with source references [Source Type, FY]
3. Identifies gaps preventing a higher score
4. Assesses evidence strength (strong/moderate/weak)

Write in professional PE memo style."""


# ============================================================================
# Justification Generator
# ============================================================================


class JustificationGenerator:
    """
    Generate score justifications with cited evidence.

    Connects CS3 scores + CS3 rubrics + CS4 hybrid retrieval + LLM
    to produce IC-ready justifications for any company × dimension.

    Usage:
        generator = JustificationGenerator()
        justification = await generator.generate_justification("NVDA", Dimension.DATA_INFRASTRUCTURE)
    """

    def __init__(
        self,
        cs3: CS3Client = None,
        retriever: HybridRetriever = None,
        router: ModelRouter = None,
        settings: CS4Settings = None,
    ):
        self._settings = settings or get_cs4_settings()
        self._cs3 = cs3 or CS3Client(base_url=self._settings.cs3_api_url)
        self._retriever = retriever or HybridRetriever(self._settings)
        self._router = router or ModelRouter(self._settings)

    @property
    def retriever(self) -> HybridRetriever:
        """Access the retriever (for indexing from outside)."""
        return self._retriever

    async def generate_justification(
        self,
        company_id: str,
        dimension: Dimension,
    ) -> ScoreJustification:
        """
        Generate full justification for a dimension score.

        Steps:
          1. Fetch score from CS3
          2. Get rubric for that level
          3. Build search query from rubric keywords
          4. Search for evidence
          5. Match evidence to rubric keywords
          6. Identify gaps (next level criteria not found)
          7. Generate summary with LLM (or templated fallback)
          8. Assess evidence strength
        """
        ticker = company_id.upper()

        # 1. Fetch score from CS3
        score = await self._cs3.get_dimension_score(ticker, dimension)
        logger.info(
            "justification_score_fetched",
            company=ticker,
            dimension=dimension.value,
            score=score.score,
            level=score.level.value,
        )

        # 2. Get rubric for that level
        rubrics = await self._cs3.get_rubric(dimension, score.level)
        rubric = rubrics[0] if rubrics else None

        # 3. Build search query from rubric keywords
        if rubric and rubric.keywords:
            query = " ".join(rubric.keywords)
        else:
            query = dimension.value.replace("_", " ")

        # 4. Search for evidence via hybrid retrieval
        results = await self._retriever.retrieve(
            query=query,
            k=15,
            filter_metadata={
                "company_id": ticker,
                "dimension": dimension.value,
            },
        )

        # Also search without dimension filter for broader coverage
        if len(results) < 5:
            broader = await self._retriever.retrieve(
                query=query,
                k=10,
                filter_metadata={"company_id": ticker},
            )
            seen_ids = {r.doc_id for r in results}
            for r in broader:
                if r.doc_id not in seen_ids:
                    results.append(r)
                    seen_ids.add(r.doc_id)

        # 5. Match evidence to rubric keywords
        cited = self._match_to_rubric(results, rubric)

        # 6. Identify gaps (next level criteria not found)
        gaps = await self._identify_gaps(
            ticker, dimension, score.level, results
        )

        # 7. Generate summary (LLM or templated fallback)
        summary = await self._generate_summary(
            ticker, dimension, score, rubric, cited
        )

        # 8. Assess evidence strength
        strength = self._assess_strength(cited)

        justification = ScoreJustification(
            company_id=ticker,
            dimension=dimension,
            score=score.score,
            level=score.level.value,
            level_name=score.level.name_label,
            confidence_interval=score.confidence_interval,
            rubric_criteria=rubric.criteria_text if rubric else "",
            rubric_keywords=rubric.keywords if rubric else [],
            supporting_evidence=cited,
            gaps_identified=gaps,
            generated_summary=summary,
            evidence_strength=strength,
        )

        logger.info(
            "justification_generated",
            company=ticker,
            dimension=dimension.value,
            evidence_count=len(cited),
            strength=strength,
            gaps=len(gaps),
        )
        return justification

    # ── Evidence Matching ───────────────────────────────────────

    def _match_to_rubric(
        self,
        results: List[RetrievedDocument],
        rubric: Optional[RubricCriteria],
    ) -> List[CitedEvidence]:
        """
        Match retrieved documents to rubric keywords.

        Returns evidence sorted by keyword match count (descending),
        limited to top 5 for IC presentation clarity.
        """
        if not rubric:
            # No rubric — return top results by score
            return [
                CitedEvidence(
                    evidence_id=r.doc_id,
                    content=r.content[:500],
                    source_type=r.metadata.get("source_type", "unknown"),
                    source_url=r.metadata.get("source_url"),
                    confidence=float(r.metadata.get("confidence", 0.5)),
                    matched_keywords=[],
                    relevance_score=r.score,
                )
                for r in results[:5]
            ]

        # Pass 1: Collect evidence with keyword matches
        keyword_matched = []
        relevance_only = []

        for r in results:
            content_lower = r.content.lower()
            matched = [
                kw for kw in rubric.keywords
                if kw.lower() in content_lower
            ]

            entry = CitedEvidence(
                evidence_id=r.doc_id,
                content=r.content[:500],
                source_type=r.metadata.get("source_type", "unknown"),
                source_url=r.metadata.get("source_url"),
                confidence=float(r.metadata.get("confidence", 0.5)),
                matched_keywords=matched,
                relevance_score=r.score,
            )

            if matched:
                keyword_matched.append(entry)
            else:
                relevance_only.append(entry)

        # Sort keyword-matched by match count, relevance-only by score
        keyword_matched.sort(
            key=lambda x: (len(x.matched_keywords), x.relevance_score),
            reverse=True,
        )
        relevance_only.sort(key=lambda x: x.relevance_score, reverse=True)

        # Combine: keyword matches first, then fill remaining slots
        # with top relevance results (ensures IC always sees evidence)
        cited = keyword_matched[:5]
        remaining_slots = 5 - len(cited)
        if remaining_slots > 0:
            cited.extend(relevance_only[:remaining_slots])

        return cited

    # ── Gap Identification ──────────────────────────────────────

    async def _identify_gaps(
        self,
        company_id: str,
        dimension: Dimension,
        current_level: ScoreLevel,
        evidence: List[RetrievedDocument],
    ) -> List[str]:
        """
        Find criteria from next level not matched in evidence.

        If currently Level 4, fetch Level 5 rubric and identify
        keywords not found in any evidence text.
        """
        if current_level == ScoreLevel.LEVEL_5:
            return []  # Already at top

        try:
            next_level = ScoreLevel(current_level.value + 1)
        except ValueError:
            return []

        next_rubrics = await self._cs3.get_rubric(dimension, next_level)
        if not next_rubrics:
            return []

        next_rubric = next_rubrics[0]
        evidence_text = " ".join([e.content.lower() for e in evidence])

        gaps = []
        for kw in next_rubric.keywords:
            if kw.lower() not in evidence_text:
                gaps.append(
                    f"No evidence of '{kw}' "
                    f"(Level {next_level.value} {next_level.name_label} criterion)"
                )

        return gaps[:5]

    # ── Summary Generation ──────────────────────────────────────

    async def _generate_summary(
        self,
        company_id: str,
        dimension: Dimension,
        score: DimensionScore,
        rubric: Optional[RubricCriteria],
        cited: List[CitedEvidence],
    ) -> str:
        """
        Generate IC-ready summary via LLM, with templated fallback.

        If LLM is not configured, produces a structured template-based
        summary that still contains all the key information.
        """
        # Build evidence text for the prompt
        evidence_text = "\n".join([
            f"[{e.source_type}, conf={e.confidence:.2f}] "
            f"{e.content[:300]}..."
            for e in cited[:5]
        ]) or "No supporting evidence found."

        # Try LLM generation
        if self._router.is_configured:
            try:
                response = await self._router.complete(
                    task=TaskType.JUSTIFICATION_GENERATION,
                    messages=[{
                        "role": "user",
                        "content": JUSTIFICATION_PROMPT.format(
                            company_id=company_id,
                            dimension=dimension.value.replace("_", " ").title(),
                            score=score.score,
                            level=score.level.value,
                            level_name=score.level.name_label,
                            rubric_criteria=rubric.criteria_text if rubric else "N/A",
                            rubric_keywords=", ".join(rubric.keywords) if rubric else "N/A",
                            evidence_text=evidence_text,
                        ),
                    }],
                )
                return response.choices[0].message.content.strip()

            except Exception as e:
                logger.warning("llm_summary_failed", error=str(e))

        # Fallback: templated summary
        return self._templated_summary(
            company_id, dimension, score, rubric, cited
        )

    def _templated_summary(
        self,
        company_id: str,
        dimension: Dimension,
        score: DimensionScore,
        rubric: Optional[RubricCriteria],
        cited: List[CitedEvidence],
    ) -> str:
        """
        Generate a structured summary without LLM.

        Produces a professional PE memo format using available data.
        """
        dim_name = dimension.value.replace("_", " ").title()
        level_name = score.level.name_label

        parts = [
            f"{company_id} scores {score.score:.0f}/100 on {dim_name}, "
            f"placing it at Level {score.level.value} ({level_name}).",
        ]

        if rubric and rubric.criteria_text:
            parts.append(f"Rubric: {rubric.criteria_text}")

        if cited:
            source_types = set(e.source_type for e in cited)
            all_keywords = set()
            for e in cited:
                all_keywords.update(e.matched_keywords)

            parts.append(
                f"Supported by {len(cited)} evidence items from "
                f"{', '.join(source_types)}."
            )
            if all_keywords:
                parts.append(
                    f"Matched rubric keywords: {', '.join(sorted(all_keywords))}."
                )
        else:
            parts.append("Limited evidence found for this dimension.")

        ci = score.confidence_interval
        parts.append(
            f"95% CI: [{ci[0]:.0f}, {ci[1]:.0f}]."
        )

        return " ".join(parts)

    # ── Strength Assessment ─────────────────────────────────────

    @staticmethod
    def _assess_strength(evidence: List[CitedEvidence]) -> str:
        """
        Assess overall evidence strength.

        strong:   avg confidence >= 0.8 AND avg keyword matches >= 2
        moderate: avg confidence >= 0.6 OR avg keyword matches >= 1
        weak:     everything else
        """
        if not evidence:
            return "weak"

        avg_conf = sum(e.confidence for e in evidence) / len(evidence)
        avg_matches = (
            sum(len(e.matched_keywords) for e in evidence) / len(evidence)
        )

        if avg_conf >= 0.8 and avg_matches >= 2:
            return "strong"
        elif avg_conf >= 0.6 or avg_matches >= 1:
            return "moderate"
        return "weak"
