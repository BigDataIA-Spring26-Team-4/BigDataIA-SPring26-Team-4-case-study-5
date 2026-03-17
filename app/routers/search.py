"""
CS4 Search API — evidence search with filters.

Endpoints:
  GET  /api/v1/search          — Hybrid search with metadata filters
  POST /api/v1/index           — Trigger evidence indexing from CS2
  GET  /api/v1/index/stats     — Indexing statistics
  GET  /api/v1/llm/status      — LLM router health and budget
"""

from typing import List, Optional

import structlog
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1", tags=["search"])


# ============================================================================
# Response Models
# ============================================================================


class SearchResultResponse(BaseModel):
    """Single search result."""
    doc_id: str
    content: str
    score: float
    metadata: dict
    retrieval_method: str


class SearchResponse(BaseModel):
    """Search endpoint response."""
    query: str
    total_results: int
    results: List[SearchResultResponse]


class IndexStatsResponse(BaseModel):
    """Index statistics."""
    dense: dict
    sparse: dict
    weights: dict


class IndexRequest(BaseModel):
    """Request to index evidence for a company."""
    company_id: str = Field(..., description="Company ticker (e.g. NVDA)")
    min_confidence: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Minimum confidence threshold for evidence",
    )


class IndexResponse(BaseModel):
    """Indexing result."""
    company_id: str
    documents_indexed: int
    message: str


class LLMStatusResponse(BaseModel):
    """LLM router status."""
    configured: bool
    providers: dict
    budget: dict


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/search", response_model=SearchResponse)
async def search_evidence(
    request: Request,
    q: str = Query(..., min_length=1, description="Search query"),
    company_id: Optional[str] = Query(None, description="Filter by company ticker"),
    dimension: Optional[str] = Query(None, description="Filter by dimension"),
    source_types: Optional[str] = Query(
        None, description="Comma-separated source types filter",
    ),
    min_confidence: float = Query(
        0.0, ge=0.0, le=1.0, description="Minimum confidence",
    ),
    top_k: int = Query(10, ge=1, le=50, description="Number of results"),
):
    """
    Search evidence with hybrid retrieval (dense + sparse + RRF).

    Supports filtering by company, dimension, source type, and confidence.
    Returns results ranked by fused relevance score.
    """
    retriever = request.app.state.retriever

    # Build metadata filter
    filter_metadata = {}
    if company_id:
        filter_metadata["company_id"] = company_id.upper()
    if dimension:
        filter_metadata["dimension"] = dimension

    # Run hybrid retrieval
    results = await retriever.retrieve(
        query=q,
        k=top_k,
        filter_metadata=filter_metadata if filter_metadata else None,
    )

    # Apply source_types filter post-retrieval (ChromaDB $in has limitations)
    if source_types:
        allowed = set(s.strip() for s in source_types.split(","))
        results = [
            r for r in results
            if r.metadata.get("source_type", "") in allowed
        ]

    # Apply confidence filter post-retrieval
    if min_confidence > 0:
        results = [
            r for r in results
            if float(r.metadata.get("confidence", 0)) >= min_confidence
        ]

    return SearchResponse(
        query=q,
        total_results=len(results),
        results=[
            SearchResultResponse(
                doc_id=r.doc_id,
                content=r.content,
                score=r.score,
                metadata=r.metadata,
                retrieval_method=r.retrieval_method,
            )
            for r in results
        ],
    )


@router.post("/index", response_model=IndexResponse)
async def index_company_evidence(
    request: Request,
    body: IndexRequest,
):
    """
    Index evidence for a company from CS2.

    Fetches documents and signals from the CS2 API, maps them
    to dimensions via the dimension mapper, and indexes into
    both dense (ChromaDB) and sparse (BM25) stores.
    """
    retriever = request.app.state.retriever
    cs2 = request.app.state.cs2
    mapper = request.app.state.mapper

    ticker = body.company_id.upper()

    try:
        # Fetch evidence from CS2
        evidence_list = await cs2.get_evidence(
            company_id=ticker,
            min_confidence=body.min_confidence,
        )

        if not evidence_list:
            return IndexResponse(
                company_id=ticker,
                documents_indexed=0,
                message=f"No evidence found for {ticker} in CS2",
            )

        # Build documents with dimension mapping
        docs = []
        for e in evidence_list:
            primary_dim = mapper.get_primary_dimension(e.signal_category)
            docs.append({
                "doc_id": e.evidence_id,
                "content": e.content,
                "metadata": {
                    "company_id": e.company_id,
                    "source_type": e.source_type.value,
                    "signal_category": e.signal_category.value,
                    "dimension": primary_dim.value,
                    "confidence": e.confidence,
                    "fiscal_year": e.fiscal_year or 0,
                    "source_url": e.source_url or "",
                },
            })

        count = retriever.index_documents(docs)

        # Mark as indexed in CS2
        evidence_ids = [e.evidence_id for e in evidence_list]
        await cs2.mark_indexed(evidence_ids)

        return IndexResponse(
            company_id=ticker,
            documents_indexed=count,
            message=f"Indexed {count} evidence items for {ticker}",
        )

    except Exception as e:
        logger.error("indexing_failed", company=ticker, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Indexing failed for {ticker}: {str(e)}",
        )


@router.get("/index/stats", response_model=IndexStatsResponse)
async def get_index_stats(request: Request):
    """Get indexing statistics for the evidence store."""
    retriever = request.app.state.retriever
    stats = retriever.get_stats()
    return IndexStatsResponse(**stats)


@router.get("/llm/status", response_model=LLMStatusResponse)
async def get_llm_status(request: Request):
    """Get LLM router health, configured providers, and budget."""
    router_instance = request.app.state.router
    status = router_instance.get_status()
    return LLMStatusResponse(**status)
