"""
Tests for CS4 Phase 2: RAG Infrastructure.

Tests:
  - CS4 Config (env var loading, model config resolution)
  - LLM Router (budget tracking, model selection, unconfigured handling)
  - Vector Store (index, search, metadata filters) — uses temp ChromaDB
  - Hybrid Retriever (index, dense, sparse, RRF fusion math)
  - HyDE (fallback to normal search when LLM not configured)
"""

import asyncio
import os
import shutil
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ============================================================================
# Helper: run async functions in sync tests
# ============================================================================

def run_async(coro):
    """Run an async function in a sync test."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ============================================================================
# CS4 Config Tests
# ============================================================================


class TestCS4Config:
    """Test CS4 configuration loading from env vars."""

    def test_defaults_when_no_env(self):
        """Config has sensible defaults when no env vars are set."""
        from src.config import CS4Settings
        settings = CS4Settings()

        assert settings.dense_weight == 0.6
        assert settings.bm25_weight == 0.4
        assert settings.rrf_k == 60
        assert settings.daily_budget_usd == 50.0
        assert settings.embedding_model == "all-MiniLM-L6-v2"
        assert settings.chroma_persist_dir == "./chroma_data"

    def test_env_override(self):
        """Env vars override defaults."""
        with patch.dict(os.environ, {
            "CS4_PRIMARY_MODEL": "gpt-4o",
            "CS4_FALLBACK_MODEL": "ollama/llama3",
            "CS4_DENSE_WEIGHT": "0.7",
            "CS4_BM25_WEIGHT": "0.3",
        }):
            from src.config import CS4Settings
            settings = CS4Settings()

            assert settings.primary_model == "gpt-4o"
            assert settings.fallback_model == "ollama/llama3"
            assert settings.dense_weight == 0.7
            assert settings.bm25_weight == 0.3

    def test_is_llm_configured(self):
        """is_llm_configured reflects whether primary_model is set."""
        from src.config import CS4Settings

        with patch.dict(os.environ, {"CS4_PRIMARY_MODEL": ""}):
            s = CS4Settings()
            assert s.is_llm_configured is False

        with patch.dict(os.environ, {"CS4_PRIMARY_MODEL": "gpt-4o"}):
            s = CS4Settings()
            assert s.is_llm_configured is True

    def test_model_config_per_task(self):
        """Each task type gets appropriate temperature and max_tokens."""
        from src.config import CS4Settings

        with patch.dict(os.environ, {"CS4_PRIMARY_MODEL": "test-model"}):
            s = CS4Settings()

            extract = s.get_model_config("evidence_extraction")
            assert extract.temperature == 0.3
            assert extract.max_tokens == 4000

            justify = s.get_model_config("justification_generation")
            assert justify.temperature == 0.2
            assert justify.max_tokens == 2000

            chat = s.get_model_config("chat_response")
            assert chat.temperature == 0.7
            assert chat.max_tokens == 1000

    def test_task_specific_model_override(self):
        """Task-specific env var overrides primary model."""
        with patch.dict(os.environ, {
            "CS4_PRIMARY_MODEL": "default-model",
            "CS4_JUSTIFICATION_MODEL": "expensive-model",
        }):
            from src.config import CS4Settings
            s = CS4Settings()

            assert s.justification_model == "expensive-model"
            assert s.extraction_model == "default-model"

    def test_provider_summary(self):
        """provider_summary returns all configured models."""
        with patch.dict(os.environ, {"CS4_PRIMARY_MODEL": "gpt-4o"}):
            from src.config import CS4Settings
            s = CS4Settings()
            summary = s.provider_summary

            assert "primary" in summary
            assert "embedding" in summary
            assert summary["primary"] == "gpt-4o"


# ============================================================================
# LLM Router Tests
# ============================================================================


class TestModelRouter:
    """Test LLM Router (Task 7.1, 8 pts)."""

    def test_unconfigured_raises(self):
        """Router raises clear error when no LLM configured."""
        from src.config import CS4Settings
        from src.services.llm.router import ModelRouter, TaskType

        with patch.dict(os.environ, {"CS4_PRIMARY_MODEL": ""}):
            settings = CS4Settings()
            router = ModelRouter(settings)

            assert router.is_configured is False

            with pytest.raises(RuntimeError, match="No LLM provider configured"):
                run_async(router.complete(
                    TaskType.CHAT_RESPONSE,
                    [{"role": "user", "content": "hello"}],
                ))

    def test_budget_tracking(self):
        """DailyBudget tracks spend and enforces limit."""
        from src.services.llm.router import DailyBudget

        budget = DailyBudget(limit_usd=1.0)

        assert budget.can_spend(0.5) is True
        budget.record_spend(0.5)
        assert budget.spent_today == 0.5
        assert budget.remaining == 0.5

        assert budget.can_spend(0.6) is False
        assert budget.can_spend(0.5) is True

    def test_budget_daily_reset(self):
        """Budget resets when day changes."""
        from datetime import date
        from src.services.llm.router import DailyBudget

        budget = DailyBudget(limit_usd=10.0)
        budget.record_spend(8.0)
        assert budget.remaining == 2.0

        # Simulate day change
        budget._date = date(2020, 1, 1)
        assert budget.remaining == 10.0
        assert budget.spent_today == 0.0

    def test_get_status(self):
        """Router status includes configuration and budget."""
        from src.config import CS4Settings
        from src.services.llm.router import ModelRouter

        with patch.dict(os.environ, {"CS4_PRIMARY_MODEL": "test-model"}):
            settings = CS4Settings()
            router = ModelRouter(settings)
            status = router.get_status()

            assert status["configured"] is True
            assert "budget" in status
            assert "providers" in status


# ============================================================================
# Vector Store Tests (uses temp ChromaDB directory)
# ============================================================================


class TestVectorStore:
    """Test ChromaDB vector store (Task 7.2)."""

    @pytest.fixture
    def temp_store(self):
        """Create a VectorStore with a temporary directory."""
        from src.config import CS4Settings
        from src.services.search.vector_store import VectorStore

        tmpdir = tempfile.mkdtemp(prefix="cs4_test_chroma_")
        with patch.dict(os.environ, {"CS4_CHROMA_PERSIST_DIR": tmpdir}):
            settings = CS4Settings()
            store = VectorStore(settings)
            yield store
        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_index_and_count(self, temp_store):
        """Index documents and verify count."""
        docs = [
            {
                "doc_id": "doc_1",
                "content": "NVIDIA maintains world-class data infrastructure with Snowflake",
                "metadata": {"company_id": "NVDA", "dimension": "data_infrastructure", "confidence": 0.9},
            },
            {
                "doc_id": "doc_2",
                "content": "JPMorgan has invested heavily in AI governance frameworks",
                "metadata": {"company_id": "JPM", "dimension": "ai_governance", "confidence": 0.85},
            },
        ]
        count = temp_store.index_documents(docs)
        assert count == 2
        assert temp_store.count() == 2

    def test_search_basic(self, temp_store):
        """Basic semantic search returns relevant results."""
        docs = [
            {
                "doc_id": "doc_1",
                "content": "NVIDIA uses Snowflake data lakehouse for real-time analytics",
                "metadata": {"company_id": "NVDA", "dimension": "data_infrastructure", "confidence": 0.9},
            },
            {
                "doc_id": "doc_2",
                "content": "JPMorgan hiring machine learning engineers for NLP team",
                "metadata": {"company_id": "JPM", "dimension": "talent", "confidence": 0.8},
            },
            {
                "doc_id": "doc_3",
                "content": "Walmart supply chain optimization using traditional methods",
                "metadata": {"company_id": "WMT", "dimension": "use_case_portfolio", "confidence": 0.7},
            },
        ]
        temp_store.index_documents(docs)

        results = temp_store.search("data lakehouse real-time", top_k=2)
        assert len(results) >= 1
        assert results[0].doc_id == "doc_1"  # Most relevant

    def test_search_with_company_filter(self, temp_store):
        """Search filtered by company returns only that company's docs."""
        docs = [
            {
                "doc_id": "nvda_1",
                "content": "NVIDIA cloud infrastructure and AI platform",
                "metadata": {"company_id": "NVDA", "dimension": "technology_stack", "confidence": 0.9},
            },
            {
                "doc_id": "jpm_1",
                "content": "JPMorgan cloud infrastructure and AI platform",
                "metadata": {"company_id": "JPM", "dimension": "technology_stack", "confidence": 0.9},
            },
        ]
        temp_store.index_documents(docs)

        results = temp_store.search("cloud AI", company_id="NVDA")
        assert all(r.metadata["company_id"] == "NVDA" for r in results)

    def test_search_with_dimension_filter(self, temp_store):
        """Search filtered by dimension."""
        docs = [
            {
                "doc_id": "d1",
                "content": "Strong AI governance with CAIO reporting to board",
                "metadata": {"company_id": "NVDA", "dimension": "ai_governance", "confidence": 0.9},
            },
            {
                "doc_id": "d2",
                "content": "Strong talent pipeline with 20 ML engineers",
                "metadata": {"company_id": "NVDA", "dimension": "talent", "confidence": 0.9},
            },
        ]
        temp_store.index_documents(docs)

        results = temp_store.search("strong leadership", dimension="ai_governance")
        assert all(r.metadata["dimension"] == "ai_governance" for r in results)

    def test_search_scores_are_valid(self, temp_store):
        """Search result scores are between 0 and 1."""
        docs = [{
            "doc_id": "d1",
            "content": "Test document about artificial intelligence",
            "metadata": {"company_id": "TEST", "dimension": "talent", "confidence": 0.5},
        }]
        temp_store.index_documents(docs)

        results = temp_store.search("artificial intelligence")
        for r in results:
            assert 0.0 <= r.score <= 1.0

    def test_upsert_deduplicates(self, temp_store):
        """Indexing the same doc_id twice doesn't duplicate."""
        doc = {
            "doc_id": "dup_1",
            "content": "Original content",
            "metadata": {"company_id": "NVDA", "dimension": "talent", "confidence": 0.5},
        }
        temp_store.index_documents([doc])
        assert temp_store.count() == 1

        doc["content"] = "Updated content"
        temp_store.index_documents([doc])
        assert temp_store.count() == 1  # Still 1

    def test_get_stats(self, temp_store):
        """get_stats returns index info."""
        stats = temp_store.get_stats()
        assert "total_documents" in stats
        assert "embedding_model" in stats
        assert stats["embedding_model"] == "all-MiniLM-L6-v2"


# ============================================================================
# Hybrid Retriever Tests
# ============================================================================


class TestHybridRetriever:
    """Test Hybrid Retrieval with RRF Fusion (Task 8.1, 10 pts)."""

    @pytest.fixture
    def retriever(self):
        """Create a HybridRetriever with temp ChromaDB."""
        from src.config import CS4Settings
        from src.services.retrieval.hybrid import HybridRetriever
        from src.services.search.vector_store import VectorStore

        tmpdir = tempfile.mkdtemp(prefix="cs4_test_hybrid_")
        with patch.dict(os.environ, {"CS4_CHROMA_PERSIST_DIR": tmpdir}):
            settings = CS4Settings()
            store = VectorStore(settings)
            retriever = HybridRetriever(settings, store)
            yield retriever
        shutil.rmtree(tmpdir, ignore_errors=True)

    def _sample_docs(self):
        """Sample documents for testing."""
        return [
            {
                "doc_id": "nvda_infra_1",
                "content": "NVIDIA operates a Snowflake data lakehouse with real-time streaming pipelines and 95 percent data quality",
                "metadata": {"company_id": "NVDA", "dimension": "data_infrastructure", "confidence": 0.9},
            },
            {
                "doc_id": "nvda_talent_1",
                "content": "NVIDIA hiring 50 machine learning engineers and data scientists for AI platform team",
                "metadata": {"company_id": "NVDA", "dimension": "talent", "confidence": 0.85},
            },
            {
                "doc_id": "jpm_gov_1",
                "content": "JPMorgan established AI governance board with CAIO reporting directly to CEO",
                "metadata": {"company_id": "JPM", "dimension": "ai_governance", "confidence": 0.9},
            },
            {
                "doc_id": "wmt_culture_1",
                "content": "Walmart fostering data-driven culture with company-wide analytics training programs",
                "metadata": {"company_id": "WMT", "dimension": "culture", "confidence": 0.75},
            },
            {
                "doc_id": "ge_tech_1",
                "content": "GE deploying MLOps pipeline with model registry and automated CI/CD for ML models",
                "metadata": {"company_id": "GE", "dimension": "technology_stack", "confidence": 0.8},
            },
        ]

    def test_index_documents(self, retriever):
        """Index documents into both dense and sparse stores."""
        docs = self._sample_docs()
        count = retriever.index_documents(docs)
        assert count == 5

        stats = retriever.get_stats()
        assert stats["sparse"]["corpus_size"] == 5
        assert stats["sparse"]["bm25_initialized"] is True
        assert stats["dense"]["total_documents"] == 5

    def test_hybrid_retrieve(self, retriever):
        """Hybrid retrieve returns fused results."""
        retriever.index_documents(self._sample_docs())

        results = run_async(
            retriever.retrieve("Snowflake data lakehouse real-time", k=3)
        )

        assert len(results) >= 1
        assert results[0].retrieval_method == "hybrid"
        # Top result should be the NVDA data infrastructure doc
        assert results[0].doc_id == "nvda_infra_1"

    def test_hybrid_retrieve_with_filter(self, retriever):
        """Hybrid retrieve with metadata filter."""
        retriever.index_documents(self._sample_docs())

        results = run_async(
            retriever.retrieve(
                "AI governance board",
                k=3,
                filter_metadata={"company_id": "JPM"},
            )
        )

        assert len(results) >= 1
        # All results should be JPM (sparse filter applied)
        for r in results:
            assert r.metadata.get("company_id") == "JPM"

    def test_rrf_fusion_math(self, retriever):
        """RRF fusion correctly combines dense and sparse rankings."""
        from src.services.retrieval.hybrid import RetrievedDocument

        # Manually test fusion with known rankings
        dense = [
            RetrievedDocument("A", "content_a", {}, 0.95, "dense"),
            RetrievedDocument("B", "content_b", {}, 0.85, "dense"),
            RetrievedDocument("C", "content_c", {}, 0.75, "dense"),
        ]
        sparse = [
            RetrievedDocument("B", "content_b", {}, 10.0, "sparse"),
            RetrievedDocument("C", "content_c", {}, 8.0, "sparse"),
            RetrievedDocument("D", "content_d", {}, 6.0, "sparse"),
        ]

        fused = retriever._rrf_fusion(dense, sparse, k=4)

        # B should rank highest (appears in both)
        ids = [d.doc_id for d in fused]
        assert "B" in ids
        assert "A" in ids

        # B should have higher score than D (which only appears in sparse)
        b_score = next(d.score for d in fused if d.doc_id == "B")
        d_idx = next((i for i, d in enumerate(fused) if d.doc_id == "D"), None)
        if d_idx is not None:
            d_score = fused[d_idx].score
            assert b_score > d_score

    def test_rrf_scores_use_configured_weights(self):
        """RRF uses weights from CS4Settings."""
        from src.services.retrieval.hybrid import HybridRetriever, RetrievedDocument
        from src.config import CS4Settings

        with patch.dict(os.environ, {
            "CS4_DENSE_WEIGHT": "0.8",
            "CS4_BM25_WEIGHT": "0.2",
            "CS4_RRF_K": "10",
            "CS4_CHROMA_PERSIST_DIR": tempfile.mkdtemp(),
        }):
            settings = CS4Settings()
            retriever = HybridRetriever(settings)

            assert settings.dense_weight == 0.8
            assert settings.bm25_weight == 0.2

            # Doc only in dense at rank 0
            dense = [RetrievedDocument("X", "x", {}, 0.9, "dense")]
            sparse = []

            fused = retriever._rrf_fusion(dense, sparse, k=1)
            assert len(fused) == 1
            # Score = 0.8 / (10 + 0 + 1) = 0.8 / 11 ≈ 0.0727
            expected = 0.8 / 11
            assert abs(fused[0].score - expected) < 0.001

    def test_empty_corpus_returns_empty(self, retriever):
        """Retrieve on empty index returns empty list."""
        results = run_async(retriever.retrieve("anything", k=5))
        assert results == []

    def test_sparse_only_query(self, retriever):
        """BM25 finds exact keyword matches."""
        retriever.index_documents(self._sample_docs())

        # "CAIO" is an exact keyword in the JPM doc
        sparse_results = retriever._sparse_retrieve("CAIO", n=3, filter_metadata=None)
        assert len(sparse_results) >= 1
        assert any(r.doc_id == "jpm_gov_1" for r in sparse_results)


# ============================================================================
# HyDE Tests
# ============================================================================


class TestHyDE:
    """Test HyDE Query Enhancement (7 pts)."""

    def test_fallback_when_llm_not_configured(self):
        """HyDE falls back to normal search when LLM is not configured."""
        from src.config import CS4Settings
        from src.services.retrieval.hyde import HyDEEnhancer
        from src.services.search.vector_store import VectorStore

        tmpdir = tempfile.mkdtemp(prefix="cs4_test_hyde_")
        try:
            with patch.dict(os.environ, {
                "CS4_PRIMARY_MODEL": "",
                "CS4_CHROMA_PERSIST_DIR": tmpdir,
            }):
                settings = CS4Settings()
                store = VectorStore(settings)
                enhancer = HyDEEnhancer(settings=settings)

                # Index a doc
                store.index_documents([{
                    "doc_id": "test_1",
                    "content": "NVIDIA data infrastructure with Snowflake",
                    "metadata": {"company_id": "NVDA", "dimension": "data_infrastructure", "confidence": 0.9},
                }])

                # HyDE search should still work (fallback to normal)
                results = run_async(
                    enhancer.search("data infrastructure", vector_store=store)
                )
                assert len(results) >= 1
                assert results[0].doc_id == "test_1"
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_generate_returns_none_when_unconfigured(self):
        """generate_hypothetical_document returns None without LLM."""
        from src.config import CS4Settings
        from src.services.retrieval.hyde import HyDEEnhancer

        with patch.dict(os.environ, {"CS4_PRIMARY_MODEL": ""}):
            settings = CS4Settings()
            enhancer = HyDEEnhancer(settings=settings)

            result = run_async(
                enhancer.generate_hypothetical_document("test query")
            )
            assert result is None

    def test_hyde_prompt_template(self):
        """HyDE prompt template includes the query."""
        from src.services.retrieval.hyde import HYDE_USER_TEMPLATE

        filled = HYDE_USER_TEMPLATE.format(query="Why did NVDA score high?")
        assert "Why did NVDA score high?" in filled

    def test_hyde_system_prompt_is_pe_focused(self):
        """System prompt is domain-specific to PE analysis."""
        from src.services.retrieval.hyde import HYDE_SYSTEM_PROMPT

        assert "PE analyst" in HYDE_SYSTEM_PROMPT
        assert "evidence" in HYDE_SYSTEM_PROMPT.lower()
