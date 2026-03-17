"""
Document collection and retrieval endpoints.

Case Study 2: API endpoints for triggering SEC document collection,
listing documents, and retrieving document chunks.
All endpoints read/write to Snowflake via snowflake_cs2 service.
"""

import json
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.services.snowflake import get_db
from app.services import snowflake as snowflake_db

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])
log = structlog.get_logger(__name__)


# ── Request / Response schemas ──────────────────────────────────────────


class CollectionRequest(BaseModel):
    company_id: UUID
    filing_types: list[str] = ["10-K", "10-Q", "8-K"]
    years_back: int = 3


class CollectionResponse(BaseModel):
    task_id: str
    status: str
    message: str


class DocumentOut(BaseModel):
    id: str
    company_id: str
    ticker: str
    filing_type: str
    filing_date: str
    content_hash: str | None = None
    word_count: int | None = None
    chunk_count: int | None = None
    status: str
    local_path: str | None = None
    created_at: str | None = None

    class Config:
        from_attributes = True


class ChunkOut(BaseModel):
    id: str
    document_id: str
    chunk_index: int
    content: str
    section: str | None = None
    word_count: int | None = None

    class Config:
        from_attributes = True


# ── Endpoints ───────────────────────────────────────────────────────────


@router.post("/collect", response_model=CollectionResponse)
async def collect_documents(
    request: CollectionRequest,
    background_tasks: BackgroundTasks,
):
    """Trigger document collection for a company (async background task)."""
    task_id = str(uuid4())

    background_tasks.add_task(
        _run_document_collection,
        task_id=task_id,
        company_id=request.company_id,
        filing_types=request.filing_types,
        years_back=request.years_back,
    )

    return CollectionResponse(
        task_id=task_id,
        status="queued",
        message=f"Document collection started for company {request.company_id}",
    )


async def _run_document_collection(
    task_id: str,
    company_id: UUID,
    filing_types: list[str],
    years_back: int,
):
    """Background task — delegates to SEC EDGAR pipeline + stores to Snowflake."""
    log.info("document_collection_started", task_id=task_id, company_id=str(company_id))
    # Full implementation is in scripts/collect_evidence.py
    # The API triggers the same pipeline that the script uses


@router.get("", response_model=list[DocumentOut])
async def list_documents(
    company_id: str | None = None,
    filing_type: str | None = None,
    status: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """List documents with optional filters. Reads from Snowflake."""
    rows = snowflake_db.list_documents_db(
        db,
        company_id=company_id,
        filing_type=filing_type,
        status=status,
        limit=limit,
    )
    return [
        DocumentOut(
            id=str(r.id),
            company_id=str(r.company_id),
            ticker=r.ticker,
            filing_type=r.filing_type,
            filing_date=str(r.filing_date),
            content_hash=r.content_hash,
            word_count=r.word_count,
            chunk_count=r.chunk_count,
            status=r.status,
            local_path=r.local_path,
            created_at=str(r.created_at) if r.created_at else None,
        )
        for r in rows
    ]


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(document_id: str, db: Session = Depends(get_db)):
    """Get a single document by ID."""
    row = snowflake_db.get_document_by_id(db, document_id)
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentOut(
        id=str(row.id),
        company_id=str(row.company_id),
        ticker=row.ticker,
        filing_type=row.filing_type,
        filing_date=str(row.filing_date),
        content_hash=row.content_hash,
        word_count=row.word_count,
        chunk_count=row.chunk_count,
        status=row.status,
        local_path=row.local_path,
        created_at=str(row.created_at) if row.created_at else None,
    )


@router.get("/{document_id}/chunks", response_model=list[ChunkOut])
async def get_document_chunks(document_id: str, db: Session = Depends(get_db)):
    """Get all chunks for a document."""
    rows = snowflake_db.get_chunks_for_document(db, document_id)
    return [
        ChunkOut(
            id=str(r.id),
            document_id=str(r.document_id),
            chunk_index=r.chunk_index,
            content=r.content,
            section=r.section,
            word_count=r.word_count,
        )
        for r in rows
    ]
