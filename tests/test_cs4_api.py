"""
Tests for CS4 Phase 4: API Endpoints.

Tests the FastAPI endpoints via TestClient:
  - Search API (8 pts): search, index stats, LLM status
  - Justification API (7 pts): justification, IC prep, analyst notes
  - Validation: invalid dimensions, missing companies

Uses a test app with temp ChromaDB and pre-indexed sample evidence.
No real API server or LLM required.
"""

import asyncio
import os
import shutil
import tempfile
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


# ============================================================================
# Test App Factory
# ============================================================================


@pytest.fixture(scope="module")
def test_app():
    """
    Create a fully wired CS4 FastAPI app for testing.

    Uses temp ChromaDB, no LLM, and pre-indexed sample evidence.
    Scope=module so the app and index are reused across all tests.
    """
    tmpdir = tempfile.mkdtemp(prefix="cs4_test_api_")

    with patch.dict(os.environ, {
        "CS4_PRIMARY_MODEL": "",
        "CS4_CHROMA_PERSIST_DIR": tmpdir,
    }):
        from src.config import CS4Settings
        from src.services.integration.cs1_client import CS1Client
        from src.services.integration.cs2_client import CS2Client
        from src.services.integration.cs3_client import CS3Client
        from src.services.llm.router import ModelRouter
        from src.services.search.vector_store import VectorStore
        from src.services.retrieval.hybrid import HybridRetriever
        from src.services.retrieval.dimension_mapper import DimensionMapper
        from src.services.justification.generator import JustificationGenerator
        from src.services.workflows.ic_prep import ICPrepWorkflow
        from src.services.collection.analyst_notes import AnalystNotesCollector

        from src.api.search import router as search_router
        from src.api.justification import router as justification_router
        from fastapi import FastAPI

        settings = CS4Settings()

        # Build components
        cs1 = CS1Client()
        cs2 = CS2Client()
        cs3 = CS3Client()
        llm_router = ModelRouter(settings)
        vector_store = VectorStore(settings)
        retriever = HybridRetriever(settings, vector_store)
        mapper = DimensionMapper()
        generator = JustificationGenerator(
            cs3=cs3, retriever=retriever, router=llm_router, settings=settings,
        )
        ic_workflow = ICPrepWorkflow(
            cs1=cs1, cs3=cs3, generator=generator, settings=settings,
        )
        collector = AnalystNotesCollector(retriever)

        # Index sample evidence
        sample_docs = [
            {
                "doc_id": "nvda_di_1",
                "content": (
                    "NVIDIA operates a comprehensive Snowflake data lakehouse "
                    "with real-time streaming pipelines, achieving 95% data quality "
                    "across all business units. API-first data mesh architecture."
                ),
                "metadata": {
                    "company_id": "NVDA",
                    "source_type": "sec_10k_item_1",
                    "dimension": "data_infrastructure",
                    "confidence": 0.9,
                },
            },
            {
                "doc_id": "nvda_talent_1",
                "content": (
                    "NVIDIA hiring 50 machine learning engineers and data "
                    "scientists. Active recruitment for AI research team "
                    "with retention programs."
                ),
                "metadata": {
                    "company_id": "NVDA",
                    "source_type": "job_posting_linkedin",
                    "dimension": "talent",
                    "confidence": 0.85,
                },
            },
            {
                "doc_id": "nvda_gov_1",
                "content": (
                    "NVIDIA appointed CAIO reporting to board. Responsible AI "
                    "governance framework with model risk management."
                ),
                "metadata": {
                    "company_id": "NVDA",
                    "source_type": "board_proxy_def14a",
                    "dimension": "ai_governance",
                    "confidence": 0.9,
                },
            },
            {
                "doc_id": "nvda_tech_1",
                "content": (
                    "NVIDIA uses SageMaker MLOps with feature store and model "
                    "registry. Automated CI/CD for ML with MLflow tracking."
                ),
                "metadata": {
                    "company_id": "NVDA",
                    "source_type": "sec_10k_item_1",
                    "dimension": "technology_stack",
                    "confidence": 0.88,
                },
            },
            {
                "doc_id": "nvda_lead_1",
                "content": (
                    "CEO has made AI a strategic priority with multi-year "
                    "AI investment plan and digital transformation roadmap."
                ),
                "metadata": {
                    "company_id": "NVDA",
                    "source_type": "press_release",
                    "dimension": "leadership",
                    "confidence": 0.8,
                },
            },
            {
                "doc_id": "nvda_uc_1",
                "content": (
                    "5+ AI use cases in production generating revenue including "
                    "autonomous driving and recommendation systems with ROI."
                ),
                "metadata": {
                    "company_id": "NVDA",
                    "source_type": "sec_10k_item_7",
                    "dimension": "use_case_portfolio",
                    "confidence": 0.85,
                },
            },
            {
                "doc_id": "nvda_culture_1",
                "content": (
                    "Data-driven culture with continuous learning programs, "
                    "experimentation mindset, and growth mindset encouraged."
                ),
                "metadata": {
                    "company_id": "NVDA",
                    "source_type": "glassdoor_review",
                    "dimension": "culture",
                    "confidence": 0.7,
                },
            },
            {
                "doc_id": "jpm_di_1",
                "content": (
                    "JPMorgan invested in cloud data warehouse with Azure "
                    "hybrid cloud migration and ETL pipelines for analytics."
                ),
                "metadata": {
                    "company_id": "JPM",
                    "source_type": "sec_10k_item_7",
                    "dimension": "data_infrastructure",
                    "confidence": 0.85,
                },
            },
        ]
        retriever.index_documents(sample_docs)

        # Build test app (no lifespan — we set state manually)
        app = FastAPI(title="CS4 Test")
        app.include_router(search_router)
        app.include_router(justification_router)

        app.state.settings = settings
        app.state.cs1 = cs1
        app.state.cs2 = cs2
        app.state.cs3 = cs3
        app.state.router = llm_router
        app.state.vector_store = vector_store
        app.state.retriever = retriever
        app.state.mapper = mapper
        app.state.generator = generator
        app.state.ic_workflow = ic_workflow
        app.state.collector = collector

        client = TestClient(app)
        yield client

    shutil.rmtree(tmpdir, ignore_errors=True)


# ============================================================================
# Search API Tests (8 pts)
# ============================================================================


class TestSearchAPI:
    """Test search endpoints."""

    def test_search_basic(self, test_app):
        """Basic search returns results."""
        resp = test_app.get("/api/v1/search", params={"q": "data lakehouse"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_results"] >= 1
        assert data["query"] == "data lakehouse"
        assert len(data["results"]) >= 1

    def test_search_with_company_filter(self, test_app):
        """Search filtered by company."""
        resp = test_app.get(
            "/api/v1/search",
            params={"q": "data infrastructure", "company_id": "NVDA"},
        )
        assert resp.status_code == 200
        data = resp.json()
        for r in data["results"]:
            assert r["metadata"]["company_id"] == "NVDA"

    def test_search_with_dimension_filter(self, test_app):
        """Search filtered by dimension."""
        resp = test_app.get(
            "/api/v1/search",
            params={"q": "governance", "dimension": "ai_governance"},
        )
        assert resp.status_code == 200
        data = resp.json()
        for r in data["results"]:
            assert r["metadata"]["dimension"] == "ai_governance"

    def test_search_with_top_k(self, test_app):
        """Search respects top_k limit."""
        resp = test_app.get(
            "/api/v1/search",
            params={"q": "NVIDIA AI", "top_k": 2},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) <= 2

    def test_search_empty_query_rejected(self, test_app):
        """Empty query returns 422 validation error."""
        resp = test_app.get("/api/v1/search", params={"q": ""})
        assert resp.status_code == 422

    def test_search_no_query_rejected(self, test_app):
        """Missing query returns 422."""
        resp = test_app.get("/api/v1/search")
        assert resp.status_code == 422

    def test_index_stats(self, test_app):
        """Index stats returns document counts."""
        resp = test_app.get("/api/v1/index/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "dense" in data
        assert "sparse" in data
        assert "weights" in data
        assert data["dense"]["total_documents"] >= 8  # We indexed 8 sample docs

    def test_llm_status(self, test_app):
        """LLM status reports configuration."""
        resp = test_app.get("/api/v1/llm/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "configured" in data
        assert "providers" in data
        assert "budget" in data
        # We didn't configure an LLM
        assert data["configured"] is False


# ============================================================================
# Justification API Tests (7 pts)
# ============================================================================


class TestJustificationAPI:
    """Test justification and IC prep endpoints."""

    def test_justification_nvda_data_infrastructure(self, test_app):
        """Get NVDA data infrastructure justification."""
        resp = test_app.get("/api/v1/justification/NVDA/data_infrastructure")
        assert resp.status_code == 200
        data = resp.json()
        assert data["company_id"] == "NVDA"
        assert data["dimension"] == "data_infrastructure"
        assert data["score"] > 0
        assert data["level"] >= 1
        assert data["level_name"] in (
            "Excellent", "Good", "Adequate", "Developing", "Nascent"
        )
        assert len(data["generated_summary"]) > 0
        assert data["evidence_strength"] in ("strong", "moderate", "weak")

    def test_justification_has_evidence(self, test_app):
        """Justification includes supporting evidence."""
        resp = test_app.get("/api/v1/justification/NVDA/data_infrastructure")
        data = resp.json()
        assert len(data["supporting_evidence"]) >= 1
        for e in data["supporting_evidence"]:
            assert "evidence_id" in e
            assert "content" in e
            assert "source_type" in e

    def test_justification_has_rubric(self, test_app):
        """Justification includes rubric keywords."""
        resp = test_app.get("/api/v1/justification/NVDA/data_infrastructure")
        data = resp.json()
        assert len(data["rubric_keywords"]) > 0

    def test_justification_invalid_dimension(self, test_app):
        """Invalid dimension returns 400."""
        resp = test_app.get("/api/v1/justification/NVDA/fake_dimension")
        assert resp.status_code == 400
        assert "Invalid dimension" in resp.json()["detail"]

    def test_justification_talent(self, test_app):
        """Justification works for talent dimension too."""
        resp = test_app.get("/api/v1/justification/NVDA/talent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["dimension"] == "talent"

    def test_ic_prep_nvda(self, test_app):
        """Generate IC meeting package for NVDA."""
        resp = test_app.get("/api/v1/ic-prep/NVDA")
        assert resp.status_code == 200
        data = resp.json()
        assert data["company_id"] == "NVDA"
        assert data["company_name"] == "NVIDIA"
        assert data["org_air_score"] > 0
        assert len(data["executive_summary"]) > 0
        assert data["recommendation"] != ""
        assert len(data["dimension_justifications"]) == 7

    def test_ic_prep_focused(self, test_app):
        """IC prep with focused dimensions."""
        resp = test_app.get(
            "/api/v1/ic-prep/NVDA",
            params={"focus_dimensions": "data_infrastructure,talent"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["dimension_justifications"]) == 2

    def test_ic_prep_recommendation(self, test_app):
        """NVDA should get PROCEED recommendation."""
        resp = test_app.get("/api/v1/ic-prep/NVDA")
        data = resp.json()
        assert "PROCEED" in data["recommendation"]


# ============================================================================
# Analyst Notes API Tests
# ============================================================================


class TestAnalystNotesAPI:
    """Test analyst notes endpoints."""

    def test_submit_interview(self, test_app):
        """Submit interview transcript via API."""
        resp = test_app.post(
            "/api/v1/analyst-notes/interview",
            json={
                "company_id": "NVDA",
                "interviewee": "Jane Smith",
                "interviewee_title": "CTO",
                "transcript": "We have invested heavily in data infrastructure and ML platform.",
                "assessor": "analyst@pe.com",
                "dimensions_discussed": ["data_infrastructure", "technology_stack"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["note_id"].startswith("interview_NVDA_")

    def test_submit_dd_finding(self, test_app):
        """Submit DD finding via API."""
        resp = test_app.post(
            "/api/v1/analyst-notes/dd-finding",
            json={
                "company_id": "JPM",
                "title": "Data Quality Gap",
                "finding": "Observed inconsistent data quality across business units requiring attention.",
                "dimension": "data_infrastructure",
                "severity": "major",
                "assessor": "analyst@pe.com",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["note_id"].startswith("dd_JPM_")

    def test_submit_data_room(self, test_app):
        """Submit data room summary via API."""
        resp = test_app.post(
            "/api/v1/analyst-notes/data-room",
            json={
                "company_id": "WMT",
                "document_name": "IT Architecture Overview.pdf",
                "summary": "Walmart uses Azure hybrid cloud with progressive migration from on-premise.",
                "dimension": "technology_stack",
                "assessor": "analyst@pe.com",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["note_id"].startswith("dataroom_WMT_")

    def test_submit_meeting(self, test_app):
        """Submit meeting notes via API."""
        resp = test_app.post(
            "/api/v1/analyst-notes/meeting",
            json={
                "company_id": "GE",
                "title": "CTO Alignment Meeting",
                "notes": "Discussed MLOps platform deployment timeline and resource allocation for AI team.",
                "attendees": ["CTO", "VP Engineering"],
                "dimensions_discussed": ["technology_stack", "talent"],
                "assessor": "analyst@pe.com",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["note_id"].startswith("meeting_GE_")

    def test_list_notes_for_company(self, test_app):
        """List notes after submitting some."""
        # Submit one more for NVDA
        test_app.post(
            "/api/v1/analyst-notes/dd-finding",
            json={
                "company_id": "NVDA",
                "title": "Talent Risk",
                "finding": "Key person dependency on the AI research lead requires mitigation.",
                "dimension": "talent",
                "severity": "critical",
                "assessor": "analyst@pe.com",
            },
        )

        resp = test_app.get("/api/v1/analyst-notes/NVDA")
        assert resp.status_code == 200
        notes = resp.json()
        assert isinstance(notes, list)
        # We submitted at least interview + dd finding for NVDA
        assert len(notes) >= 2

    def test_submitted_note_is_searchable(self, test_app):
        """Submitted notes should appear in search results."""
        # The interview we submitted earlier should be findable
        resp = test_app.get(
            "/api/v1/search",
            params={
                "q": "data infrastructure ML platform",
                "company_id": "NVDA",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        # Should find the interview transcript
        interview_found = any(
            "interview" in r["doc_id"] for r in data["results"]
        )
        assert interview_found, "Submitted interview should be searchable"

    def test_validation_short_transcript(self, test_app):
        """Short transcript rejected by validation."""
        resp = test_app.post(
            "/api/v1/analyst-notes/interview",
            json={
                "company_id": "NVDA",
                "interviewee": "A",
                "interviewee_title": "CTO",
                "transcript": "Short",  # < 10 chars
                "assessor": "a@b.com",
            },
        )
        assert resp.status_code == 422
