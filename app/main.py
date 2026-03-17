"""
Main FastAPI application for PE Org-AI-R Platform.
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.logging import setup_logging
from app.routers import health, companies, assessments, scores, industries, config, rubrics
# CS2: Evidence Collection routers
from app.routers import documents, signals, pipeline
from app.routers.signals import evidence_router
# CS4: RAG & Search routers
from app.routers import search, justification

# CS4: RAG infrastructure imports
from app.config import get_cs4_settings
from app.services.integration.cs1_client import CS1Client
from app.services.integration.cs2_client import CS2Client
from app.services.integration.cs3_client import CS3Client
from app.services.llm.router import ModelRouter
from app.services.search.vector_store import VectorStore
from app.services.retrieval.hybrid import HybridRetriever
from app.services.retrieval.dimension_mapper import DimensionMapper
from app.services.justification.generator import JustificationGenerator
from app.services.workflows.ic_prep import ICPrepWorkflow
from app.services.collection.analyst_notes import AnalystNotesCollector

# Setup logging
setup_logging()
log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan events.
    Handles startup and shutdown tasks including CS4 RAG infrastructure.
    """
    # Startup
    log.info(
        "application_startup",
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        debug=settings.DEBUG
    )

    # Log configuration (without sensitive data)
    log.info(
        "configuration_loaded",
        snowflake_account=settings.SNOWFLAKE_ACCOUNT,
        snowflake_database=settings.SNOWFLAKE_DATABASE,
        redis_enabled=settings.REDIS_ENABLED,
        s3_enabled=settings.S3_ENABLED,
    )

    # CS4: Initialize RAG infrastructure
    cs4_settings = get_cs4_settings()

    log.info(
        "cs4_startup",
        llm_configured=cs4_settings.is_llm_configured,
        embedding_model=cs4_settings.embedding_model,
        chroma_dir=cs4_settings.chroma_persist_dir,
        cs3_api=cs4_settings.cs3_api_url,
    )

    # Integration clients
    cs1 = CS1Client(base_url=cs4_settings.cs3_api_url)
    cs2 = CS2Client(base_url=cs4_settings.cs3_api_url)
    cs3 = CS3Client(base_url=cs4_settings.cs3_api_url)

    # RAG infrastructure
    llm_router = ModelRouter(cs4_settings)
    vector_store = VectorStore(cs4_settings)
    retriever = HybridRetriever(cs4_settings, vector_store)
    mapper = DimensionMapper()

    # PE workflows
    generator = JustificationGenerator(
        cs3=cs3, retriever=retriever, router=llm_router, settings=cs4_settings,
    )
    ic_workflow = ICPrepWorkflow(
        cs1=cs1, cs3=cs3, generator=generator, settings=cs4_settings,
    )
    collector = AnalystNotesCollector(retriever)

    # Store in app.state for router access
    app.state.cs4_settings = cs4_settings
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

    log.info("cs4_ready", providers=cs4_settings.provider_summary)

    yield

    # Shutdown — close CS4 HTTP clients
    await cs1.close()
    await cs2.close()
    await cs3.close()
    log.info("application_shutdown")


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-Readiness Assessment Platform for Private Equity Portfolio Companies",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)


# ============================================================================
# Exception Handlers
# ============================================================================

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors."""
    log.warning(
        "validation_error",
        path=request.url.path,
        errors=exc.errors()
    )
    return JSONResponse(
        status_code=422,
        content={
            "detail": exc.errors(),
            "message": "Validation error"
        }
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions."""
    log.warning(
        "http_error",
        path=request.url.path,
        status_code=exc.status_code,
        detail=exc.detail
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected errors."""
    log.error(
        "unhandled_error",
        path=request.url.path,
        error=str(exc),
        exc_info=True
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


# ============================================================================
# Middleware
# ============================================================================

@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Log all requests and responses."""
    log.info(
        "request_started",
        method=request.method,
        path=request.url.path,
        query_params=dict(request.query_params)
    )
    
    response: Response = await call_next(request)
    
    log.info(
        "request_finished",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code
    )
    
    return response


# ============================================================================
# Routers
# ============================================================================

# Health check (no prefix)
app.include_router(health.router)

# API v1 routers
app.include_router(config.router)  # Configuration data (dimension weights)
app.include_router(industries.router)  # Industry reference data (cached)
app.include_router(companies.router)
app.include_router(assessments.router)
app.include_router(scores.router)  # Individual dimension score updates

# CS3→CS4: Rubric data for justification generation
app.include_router(rubrics.router)

# CS2: Evidence Collection routers
app.include_router(documents.router)
app.include_router(signals.router)
app.include_router(evidence_router)

# Pipeline execution (CS2 + CS3 evidence collection, scoring, weight config)
app.include_router(pipeline.router)

# CS4: RAG & Search routers
app.include_router(search.router)
app.include_router(justification.router)


# ============================================================================
# Root endpoint
# ============================================================================

@app.get("/", tags=["root"])
async def root():
    """Root endpoint with API information."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "search": "/api/v1/search",
            "index": "/api/v1/index",
            "justification": "/api/v1/justification/{company_id}/{dimension}",
            "ic_prep": "/api/v1/ic-prep/{company_id}",
            "analyst_notes": "/api/v1/analyst-notes/{company_id}",
            "llm_status": "/api/v1/llm/status",
        },
    }
