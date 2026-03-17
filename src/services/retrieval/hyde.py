"""
Hypothetical Document Embeddings (HyDE) for query enhancement.

HyDE improves retrieval by generating a hypothetical "ideal" evidence
passage via LLM, then searching using THAT embedding instead of the
raw query embedding.

Example:
  Query:  "Why did NVDA score high on data infrastructure?"
  HyDE:   "NVIDIA maintains a comprehensive data lake architecture
           with real-time streaming pipelines, Snowflake-based
           warehouse, 95%+ data quality scores, and an API-first
           data mesh across business units."
  → Embed the HyDE text → search → much better semantic match

Falls back to raw query embedding if LLM is not configured or fails.
"""

from typing import Any, Dict, List, Optional

import structlog

from src.config import CS4Settings, get_cs4_settings
from src.services.llm.router import ModelRouter, TaskType
from src.services.search.vector_store import SearchResult, VectorStore

logger = structlog.get_logger()


# ============================================================================
# HyDE Prompt Templates
# ============================================================================


HYDE_SYSTEM_PROMPT = (
    "You are a PE analyst writing evidence passages for AI-readiness assessments. "
    "Given a question about a company's AI capabilities, generate a realistic "
    "evidence passage (100-150 words) that would answer the question. "
    "Write as if you are quoting from a company's SEC filing, job posting, "
    "or analyst report. Include specific technologies, metrics, and details. "
    "Do NOT include any preamble — output only the evidence passage."
)


HYDE_USER_TEMPLATE = (
    "Generate a hypothetical evidence passage that would answer this question "
    "about AI readiness:\n\n{query}"
)


# ============================================================================
# HyDE Enhancer
# ============================================================================


class HyDEEnhancer:
    """
    Enhance search queries using Hypothetical Document Embeddings.

    Usage:
        enhancer = HyDEEnhancer()
        results = await enhancer.search(
            query="Why did NVDA score high on data infrastructure?",
            vector_store=store,
            company_id="NVDA",
        )

    If LLM is not configured, transparently falls back to normal
    embedding search (no error, just slightly worse retrieval quality).
    """

    def __init__(
        self,
        router: ModelRouter = None,
        settings: CS4Settings = None,
    ):
        self._settings = settings or get_cs4_settings()
        self._router = router or ModelRouter(self._settings)

    async def generate_hypothetical_document(self, query: str) -> Optional[str]:
        """
        Generate a hypothetical evidence passage for a query.

        Returns None if LLM is not configured or generation fails.
        """
        if not self._router.is_configured:
            logger.debug("hyde_skipped_no_llm")
            return None

        try:
            response = await self._router.complete(
                task=TaskType.HYDE_GENERATION,
                messages=[
                    {"role": "system", "content": HYDE_SYSTEM_PROMPT},
                    {"role": "user", "content": HYDE_USER_TEMPLATE.format(query=query)},
                ],
            )
            hyde_text = response.choices[0].message.content.strip()

            logger.info(
                "hyde_generated",
                query_length=len(query),
                hyde_length=len(hyde_text),
            )
            return hyde_text

        except Exception as e:
            logger.warning("hyde_generation_failed", error=str(e))
            return None

    async def search(
        self,
        query: str,
        vector_store: VectorStore,
        top_k: int = 10,
        company_id: Optional[str] = None,
        dimension: Optional[str] = None,
    ) -> List[SearchResult]:
        """
        Search using HyDE-enhanced embedding.

        Flow:
          1. Generate hypothetical document via LLM
          2. Embed the hypothetical document
          3. Search using that embedding
          4. If HyDE fails, fall back to raw query search

        Args:
            query: User's search query
            vector_store: VectorStore instance to search
            top_k: Number of results
            company_id: Optional company filter
            dimension: Optional dimension filter

        Returns:
            List of SearchResult
        """
        # Try HyDE enhancement
        hyde_text = await self.generate_hypothetical_document(query)

        if hyde_text:
            # Embed the hypothetical document and search with it
            hyde_embedding = vector_store.encoder.encode(hyde_text).tolist()

            results = vector_store.search_by_embedding(
                embedding=hyde_embedding,
                top_k=top_k,
                company_id=company_id,
                dimension=dimension,
            )
            logger.info("hyde_search_complete", result_count=len(results))
            return results

        # Fallback: normal query search
        logger.info("hyde_fallback_to_normal_search")
        return vector_store.search(
            query=query,
            top_k=top_k,
            company_id=company_id,
            dimension=dimension,
        )
