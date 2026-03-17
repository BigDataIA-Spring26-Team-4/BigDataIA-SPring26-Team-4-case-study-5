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

# Setup logging
setup_logging()
log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan events.
    Handles startup and shutdown tasks.
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
    
    yield
    
    # Shutdown
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
        "health": "/health"
    }
