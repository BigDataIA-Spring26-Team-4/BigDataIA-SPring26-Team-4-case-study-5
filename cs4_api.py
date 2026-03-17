"""
CS4 RAG & Search — FastAPI Application.

Separate API server for CS4 RAG capabilities.
Run with: uvicorn cs4_api:app --reload --port 8003

All shared components (retriever, generator, collector, etc.) are
initialized once at startup via the lifespan and stored in app.state.
Routers access them via request.app.state.
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from src.config import get_cs4_settings
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

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application startup — initialize all shared components.

    Components stored in app.state so routers can access them
    via request.app.state without global variables.
    """
    settings = get_cs4_settings()

    log.info(
        "cs4_startup",
        llm_configured=settings.is_llm_configured,
        embedding_model=settings.embedding_model,
        chroma_dir=settings.chroma_persist_dir,
        cs3_api=settings.cs3_api_url,
    )

    # Integration clients
    cs1 = CS1Client(base_url=settings.cs3_api_url)
    cs2 = CS2Client(base_url=settings.cs3_api_url)
    cs3 = CS3Client(base_url=settings.cs3_api_url)

    # RAG infrastructure
    llm_router = ModelRouter(settings)
    vector_store = VectorStore(settings)
    retriever = HybridRetriever(settings, vector_store)
    mapper = DimensionMapper()

    # PE workflows
    generator = JustificationGenerator(
        cs3=cs3, retriever=retriever, router=llm_router, settings=settings,
    )
    ic_workflow = ICPrepWorkflow(
        cs1=cs1, cs3=cs3, generator=generator, settings=settings,
    )
    collector = AnalystNotesCollector(retriever)

    # Store in app.state for router access
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

    log.info("cs4_ready", providers=settings.provider_summary)

    yield

    # Shutdown — close HTTP clients
    await cs1.close()
    await cs2.close()
    await cs3.close()
    log.info("cs4_shutdown")


# ============================================================================
# Create App
# ============================================================================

app = FastAPI(
    title="PE Org-AI-R CS4 — RAG & Search",
    version="1.0.0",
    description=(
        "Evidence retrieval and score justification for PE investment committees. "
        "Connects to CS1/CS2/CS3 via HTTP clients. "
        "Provides hybrid search (dense + sparse + RRF), score justifications, "
        "IC meeting prep, and analyst notes collection."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Mount routers
app.include_router(search_router)
app.include_router(justification_router)


# ============================================================================
# Root & Health
# ============================================================================

@app.get("/", tags=["root"])
async def root():
    """CS4 API information."""
    return {
        "name": "PE Org-AI-R CS4 — RAG & Search",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "endpoints": {
            "search": "/api/v1/search",
            "index": "/api/v1/index",
            "justification": "/api/v1/justification/{company_id}/{dimension}",
            "ic_prep": "/api/v1/ic-prep/{company_id}",
            "analyst_notes": "/api/v1/analyst-notes/{company_id}",
            "llm_status": "/api/v1/llm/status",
        },
    }


@app.get("/health", tags=["health"])
async def health():
    """Health check with component status."""
    settings = app.state.settings
    retriever_stats = app.state.retriever.get_stats()

    return {
        "status": "healthy",
        "service": "cs4-rag-search",
        "llm_configured": settings.is_llm_configured,
        "index": {
            "documents": retriever_stats["dense"]["total_documents"],
            "bm25_ready": retriever_stats["sparse"]["bm25_initialized"],
        },
        "notes": app.state.collector.get_stats()["total_notes"],
    }
