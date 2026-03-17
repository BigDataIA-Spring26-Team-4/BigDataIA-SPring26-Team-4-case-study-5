"""
External signals collection and retrieval endpoints.

Case Study 2: API endpoints for triggering signal collection,
listing signals, and retrieving company signal summaries.
All endpoints read/write to Snowflake via snowflake service.
"""

import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.signal import DEFAULT_SIGNAL_WEIGHTS, SignalWeights
from app.services.snowflake import get_db, get_script_db
from app.services import snowflake as snowflake_db

router = APIRouter(prefix="/api/v1/signals", tags=["signals"])
log = structlog.get_logger(__name__)


# ── Request / Response schemas ──────────────────────────────────────────


class SignalCollectionRequest(BaseModel):
    company_id: UUID
    signal_categories: list[str] = [
        "technology_hiring",
        "innovation_activity",
        "digital_presence",
        "leadership_signals",
    ]


class SignalCollectionResponse(BaseModel):
    task_id: str
    status: str
    message: str


class SignalOut(BaseModel):
    id: str
    company_id: str
    category: str
    source: str
    signal_date: str
    raw_value: str | None = None
    normalized_score: float | None = None
    confidence: float | None = None
    metadata: dict | None = None
    created_at: str | None = None

    class Config:
        from_attributes = True


class SignalSummaryOut(BaseModel):
    company_id: str
    ticker: str
    technology_hiring_score: float | None = None
    innovation_activity_score: float | None = None
    digital_presence_score: float | None = None
    leadership_signals_score: float | None = None
    composite_score: float | None = None
    signal_count: int | None = None
    last_updated: str | None = None
    weights: dict | None = None

    class Config:
        from_attributes = True


class EvidenceStatsOut(BaseModel):
    total_documents: int
    total_chunks: int
    total_signals: int
    companies_with_signals: int


# ── Helper ──────────────────────────────────────────────────────────────


def _row_to_signal_out(r) -> SignalOut:
    meta = {}
    if r.metadata_:
        try:
            meta = json.loads(r.metadata_) if isinstance(r.metadata_, str) else r.metadata_
        except Exception:
            meta = {}
    return SignalOut(
        id=str(r.id),
        company_id=str(r.company_id),
        category=r.category,
        source=r.source,
        signal_date=str(r.signal_date),
        raw_value=r.raw_value,
        normalized_score=float(r.normalized_score) if r.normalized_score else None,
        confidence=float(r.confidence) if r.confidence else None,
        metadata=meta,
        created_at=str(r.created_at) if r.created_at else None,
    )


# ── Endpoints ───────────────────────────────────────────────────────────


@router.post("/collect", response_model=SignalCollectionResponse)
async def collect_signals(
    request: SignalCollectionRequest,
    background_tasks: BackgroundTasks,
):
    """Trigger signal collection for a company (async background task).

    This endpoint runs the full CS2 evidence collection pipeline
    (jobs, tech stack, patents) for the given company and stores
    results to Snowflake.
    """
    task_id = str(uuid4())

    background_tasks.add_task(
        _run_signal_collection,
        task_id=task_id,
        company_id=request.company_id,
        signal_categories=request.signal_categories,
    )

    return SignalCollectionResponse(
        task_id=task_id,
        status="queued",
        message=f"Signal collection started for company {request.company_id}",
    )


async def _run_signal_collection(
    task_id: str,
    company_id: UUID,
    signal_categories: list[str],
):
    """Background task — runs CS2 signal collectors and stores to Snowflake.

    Collects: job postings (hiring), tech stack (digital presence),
    patents (innovation). Leadership signals come from CS3 (Glassdoor + Board).
    """
    db = get_script_db()
    try:
        log.info(
            "signal_collection_started",
            task_id=task_id,
            company_id=str(company_id),
            categories=signal_categories,
        )
        company_id_str = str(company_id)

        # Look up ticker for this company
        company = snowflake_db.get_company(db, company_id_str)
        ticker = company.ticker
        if not ticker:
            log.error("company_has_no_ticker", company_id=company_id_str)
            return

        CS3_NAMES = {
            "NVDA": "NVIDIA", "JPM": "JPMorgan", "WMT": "Walmart",
            "GE": "GE Aerospace", "DG": "Dollar General",
        }
        company_name = CS3_NAMES.get(ticker, ticker)

        hiring_score = 0.0
        innovation_score = 0.0
        digital_score = 0.0

        # ── Technology Hiring (Job Postings) ─────────────────────
        if "technology_hiring" in signal_categories:
            try:
                from app.pipelines.job_signals import JobSignalCollector

                collector = JobSignalCollector()
                postings = collector.scrape_jobs(company_name, max_results=15)
                postings = [collector.classify_posting(p) for p in postings]
                signal = collector.analyze_job_postings(
                    company_id=company_id_str,
                    company=company_name,
                    postings=postings,
                )
                snowflake_db.insert_signal(
                    db,
                    company_id=company_id_str,
                    category=signal.category.value,
                    source=signal.source.value,
                    signal_date=signal.signal_date,
                    raw_value=signal.raw_value,
                    normalized_score=signal.normalized_score,
                    confidence=signal.confidence,
                    metadata=signal.metadata,
                )
                hiring_score = signal.normalized_score
                log.info("hiring_signal_collected", ticker=ticker, score=hiring_score)
            except Exception as e:
                log.error("hiring_collection_failed", ticker=ticker, error=str(e))

        # ── Digital Presence (Tech Stack) ────────────────────────
        if "digital_presence" in signal_categories:
            try:
                from app.pipelines.tech_signals import TechStackCollector

                tech = TechStackCollector()
                techs = tech.get_known_technologies(ticker)
                tech_signal = tech.analyze_tech_stack(
                    company_id=company_id_str, technologies=techs,
                )
                snowflake_db.insert_signal(
                    db,
                    company_id=company_id_str,
                    category=tech_signal.category.value,
                    source=tech_signal.source.value,
                    signal_date=tech_signal.signal_date,
                    raw_value=tech_signal.raw_value,
                    normalized_score=tech_signal.normalized_score,
                    confidence=tech_signal.confidence,
                    metadata=tech_signal.metadata,
                )
                digital_score = tech_signal.normalized_score
                log.info("digital_signal_collected", ticker=ticker, score=digital_score)
            except Exception as e:
                log.error("digital_collection_failed", ticker=ticker, error=str(e))

        # ── Innovation Activity (Patents) ────────────────────────
        if "innovation_activity" in signal_categories:
            try:
                from app.pipelines.patent_signals import PatentSignalCollector

                ASSIGNEES = {
                    "NVDA": "NVIDIA", "JPM": "JPMorgan", "WMT": "Walmart",
                    "GE": "General Electric", "DG": "Dollar General",
                }
                patent_col = PatentSignalCollector()
                patents = patent_col.search_patents(
                    assignee_name=ASSIGNEES.get(ticker, ticker),
                )
                pat_signal = patent_col.analyze_patents(
                    company_id=company_id_str, patents=patents,
                )
                snowflake_db.insert_signal(
                    db,
                    company_id=company_id_str,
                    category=pat_signal.category.value,
                    source=pat_signal.source.value,
                    signal_date=pat_signal.signal_date,
                    raw_value=pat_signal.raw_value,
                    normalized_score=pat_signal.normalized_score,
                    confidence=pat_signal.confidence,
                    metadata=pat_signal.metadata,
                )
                innovation_score = pat_signal.normalized_score
                log.info("patent_signal_collected", ticker=ticker, score=innovation_score)
            except Exception as e:
                log.error("patent_collection_failed", ticker=ticker, error=str(e))

        # ── Update Summary ───────────────────────────────────────
        snowflake_db.upsert_signal_summary(
            db,
            company_id=company_id_str,
            ticker=ticker,
            hiring_score=hiring_score,
            innovation_score=innovation_score,
            digital_score=digital_score,
            leadership_score=0.0,
            signal_count=3,
        )

        log.info(
            "signal_collection_completed",
            task_id=task_id,
            ticker=ticker,
            hiring=hiring_score,
            innovation=innovation_score,
            digital=digital_score,
        )

    except Exception as e:
        log.error("signal_collection_failed", task_id=task_id, error=str(e))
    finally:
        db.close()


@router.get("", response_model=list[SignalOut])
async def list_signals(
    company_id: str | None = None,
    category: str | None = None,
    source: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """List signals with optional filters. Reads from Snowflake."""
    rows = snowflake_db.list_signals_db(
        db,
        company_id=company_id,
        category=category,
        source=source,
        limit=limit,
    )
    return [_row_to_signal_out(r) for r in rows]


@router.get("/companies/{company_id}/summary", response_model=SignalSummaryOut)
async def get_company_signal_summary(company_id: str, db: Session = Depends(get_db)):
    """Get aggregated signal summary for a company, including current weights."""
    row = snowflake_db.get_signal_summary(db, company_id)
    if not row:
        raise HTTPException(status_code=404, detail="Company signal summary not found")
    return SignalSummaryOut(
        company_id=str(row.company_id),
        ticker=row.ticker,
        technology_hiring_score=float(row.technology_hiring_score) if row.technology_hiring_score else None,
        innovation_activity_score=float(row.innovation_activity_score) if row.innovation_activity_score else None,
        digital_presence_score=float(row.digital_presence_score) if row.digital_presence_score else None,
        leadership_signals_score=float(row.leadership_signals_score) if row.leadership_signals_score else None,
        composite_score=float(row.composite_score) if row.composite_score else None,
        signal_count=row.signal_count,
        last_updated=str(row.last_updated) if row.last_updated else None,
        weights=DEFAULT_SIGNAL_WEIGHTS,
    )


@router.get("/companies/{company_id}/{category}", response_model=list[SignalOut])
async def get_signals_by_category(
    company_id: str, category: str, db: Session = Depends(get_db)
):
    """Get signals for a company by category."""
    rows = snowflake_db.get_signals_by_company_category(db, company_id, category)
    return [_row_to_signal_out(r) for r in rows]


# ── Signal Weights endpoint ─────────────────────────────────────────


@router.get("/weights")
async def get_signal_weights():
    """Get the default CS2 signal weights for composite scoring.

    These are the weights used to combine the 4 signal categories
    into a single composite score:
      composite = 0.30 * hiring + 0.25 * innovation
                + 0.25 * digital + 0.20 * leadership
    Users can override these via the /pipeline/recalculate-composite endpoint.
    """
    return {
        "weights": DEFAULT_SIGNAL_WEIGHTS,
        "sum": 1.0,
        "description": (
            "Default weights for composite score: "
            "technology_hiring=0.30, innovation_activity=0.25, "
            "digital_presence=0.25, leadership_signals=0.20"
        ),
        "configurable": True,
        "recalculate_endpoint": "/api/v1/pipeline/recalculate-composite",
    }


# ── Evidence endpoints (combined docs + signals) ────────────────────────


evidence_router = APIRouter(prefix="/api/v1/evidence", tags=["evidence"])


@evidence_router.get("/stats", response_model=EvidenceStatsOut)
async def get_evidence_stats(db: Session = Depends(get_db)):
    """Get overall evidence collection statistics."""
    stats = snowflake_db.get_evidence_stats(db)
    return EvidenceStatsOut(**stats)


@evidence_router.get("/companies/{company_id}")
async def get_company_evidence(company_id: str, db: Session = Depends(get_db)):
    """Get all evidence (documents + signals + summary) for a company."""
    data = snowflake_db.get_all_evidence_for_company(db, company_id)
    docs = [
        {
            "id": str(d.id),
            "ticker": d.ticker,
            "filing_type": d.filing_type,
            "filing_date": str(d.filing_date),
            "word_count": d.word_count,
            "chunk_count": d.chunk_count,
            "status": d.status,
        }
        for d in data["documents"]
    ]
    signals = [_row_to_signal_out(s).model_dump() for s in data["signals"]]
    summary = None
    if data["summary"]:
        s = data["summary"]
        summary = {
            "technology_hiring_score": float(s.technology_hiring_score) if s.technology_hiring_score else 0,
            "innovation_activity_score": float(s.innovation_activity_score) if s.innovation_activity_score else 0,
            "digital_presence_score": float(s.digital_presence_score) if s.digital_presence_score else 0,
            "leadership_signals_score": float(s.leadership_signals_score) if s.leadership_signals_score else 0,
            "composite_score": float(s.composite_score) if s.composite_score else 0,
            "signal_count": s.signal_count,
        }
    return {"documents": docs, "signals": signals, "summary": summary}
