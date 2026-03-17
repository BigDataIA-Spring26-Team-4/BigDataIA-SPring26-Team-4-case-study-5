"""
Pipeline execution API router.

Provides endpoints for running CS2 evidence collection pipelines,
CS3 signal collection, scoring, and composite weight recalculation.
All pipelines read/write to Snowflake and return results via the API.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.signal import DEFAULT_SIGNAL_WEIGHTS, SignalWeights
from app.services.snowflake import (
    get_db,
    get_company_by_ticker,
    get_signal_summary,
    get_script_db,
    insert_signal,
    list_documents_db,
    list_signals_db,
    upsert_signal_summary,
)

router = APIRouter(prefix="/api/v1/pipeline", tags=["pipeline"])
log = structlog.get_logger(__name__)

# In-memory task tracking (simple; for production use Redis/DB)
_task_status: dict[str, dict] = {}


# ── Schemas ─────────────────────────────────────────────────────────────


class PipelineRunRequest(BaseModel):
    ticker: str
    skip_sec: bool = False


class PipelineRunResponse(BaseModel):
    task_id: str
    ticker: str
    status: str
    message: str


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str  # queued | running | completed | failed
    ticker: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[dict] = None
    error: Optional[str] = None


class ScoringRequest(BaseModel):
    ticker: str


class ScoringResponse(BaseModel):
    ticker: str
    final_score: float
    vr_score: float
    hr_score: float
    synergy_score: float
    ci_lower: float
    ci_upper: float
    position_factor: float
    talent_concentration: float
    dimension_scores: dict
    evidence_count: int


class RecalcWeightsRequest(BaseModel):
    """Request to recalculate composite scores with custom weights."""
    technology_hiring: float = Field(default=0.30, ge=0, le=1)
    innovation_activity: float = Field(default=0.25, ge=0, le=1)
    digital_presence: float = Field(default=0.25, ge=0, le=1)
    leadership_signals: float = Field(default=0.20, ge=0, le=1)


class RecalcWeightsResponse(BaseModel):
    ticker: str
    old_composite: float
    new_composite: float
    weights_used: dict
    scores: dict


class WeightsInfoResponse(BaseModel):
    """Current default signal weights."""
    weights: dict
    description: str


CS3_TICKERS = ["NVDA", "JPM", "WMT", "GE", "DG"]


def _load_company_evidence(ticker: str, db: Session) -> dict:
    """Load all evidence for a company from Snowflake (mirrors scripts/score_portfolio.py)."""
    company = get_company_by_ticker(db, ticker)
    if not company:
        return {}

    summary = get_signal_summary(db, company.id)
    docs = list_documents_db(db, company_id=company.id)
    signals = list_signals_db(db, company_id=company.id)

    cs2_signals = {}
    glassdoor_score = 0.0
    board_score = 0.0
    sec_scores = {}
    news_score = 0.0

    if summary:
        cs2_signals = {
            "technology_hiring_score": float(summary.technology_hiring_score or 0),
            "innovation_activity_score": float(summary.innovation_activity_score or 0),
            "digital_presence_score": float(summary.digital_presence_score or 0),
            "leadership_signals_score": float(summary.leadership_signals_score or 0),
        }

    for sig in signals:
        score_val = float(sig.normalized_score) if sig.normalized_score else 0
        source = sig.source or ""
        category = sig.category or ""
        if source == "glassdoor" and category == "leadership_signals":
            glassdoor_score = max(glassdoor_score, score_val)
        elif source == "company_website" and category == "leadership_signals":
            board_score = max(board_score, score_val)
        elif source == "news_press_releases" and category == "leadership_signals":
            news_score = max(news_score, score_val)
        elif source.startswith("sec_item"):
            key = source.replace("sec_", "")
            sec_scores[key] = max(sec_scores.get(key, 0), score_val)

    return {
        "company_id": company.id,
        "cs2_signals": cs2_signals,
        "glassdoor_score": glassdoor_score,
        "board_score": board_score,
        "news_score": news_score,
        "sec_scores": sec_scores,
        "evidence_count": len(docs) + len(signals),
        "document_count": len(docs),
        "signal_count": len(signals),
    }


# ── Weight Endpoints ────────────────────────────────────────────────────


@router.get("/signal-weights", response_model=WeightsInfoResponse)
def get_signal_weights():
    """Get the default CS2 signal weights for composite scoring."""
    return WeightsInfoResponse(
        weights=DEFAULT_SIGNAL_WEIGHTS,
        description=(
            "Default weights for composite score calculation. "
            "technology_hiring (0.30) + innovation_activity (0.25) + "
            "digital_presence (0.25) + leadership_signals (0.20) = 1.00"
        ),
    )


@router.post("/recalculate-composite", response_model=list[RecalcWeightsResponse])
def recalculate_composite_scores(
    request: RecalcWeightsRequest,
    tickers: Optional[str] = Query(None, description="Comma-separated tickers, or all"),
    db: Session = Depends(get_db),
):
    """
    Recalculate composite scores for companies using custom weights.

    The weights must sum to 1.0. Updates are persisted to Snowflake.
    """
    # Validate weights sum
    total = (
        request.technology_hiring
        + request.innovation_activity
        + request.digital_presence
        + request.leadership_signals
    )
    if abs(total - 1.0) > 0.01:
        raise HTTPException(
            status_code=400,
            detail=f"Weights must sum to 1.0, got {total:.4f}",
        )

    weights_dict = {
        "technology_hiring": request.technology_hiring,
        "innovation_activity": request.innovation_activity,
        "digital_presence": request.digital_presence,
        "leadership_signals": request.leadership_signals,
    }

    target_tickers = (
        [t.strip().upper() for t in tickers.split(",")]
        if tickers
        else CS3_TICKERS
    )

    results = []
    for ticker in target_tickers:
        company = get_company_by_ticker(db, ticker)
        if not company:
            continue

        summary = get_signal_summary(db, company.id)
        if not summary:
            continue

        old_composite = float(summary.composite_score or 0)
        scores = {
            "technology_hiring_score": float(summary.technology_hiring_score or 0),
            "innovation_activity_score": float(summary.innovation_activity_score or 0),
            "digital_presence_score": float(summary.digital_presence_score or 0),
            "leadership_signals_score": float(summary.leadership_signals_score or 0),
        }

        # Recalculate with custom weights
        upsert_signal_summary(
            db,
            company_id=company.id,
            ticker=ticker,
            hiring_score=scores["technology_hiring_score"],
            innovation_score=scores["innovation_activity_score"],
            digital_score=scores["digital_presence_score"],
            leadership_score=scores["leadership_signals_score"],
            signal_count=summary.signal_count or 0,
            weights=weights_dict,
        )

        # Refresh to get new composite
        updated = get_signal_summary(db, company.id)
        new_composite = float(updated.composite_score or 0)

        results.append(
            RecalcWeightsResponse(
                ticker=ticker,
                old_composite=old_composite,
                new_composite=new_composite,
                weights_used=weights_dict,
                scores=scores,
            )
        )

    log.info(
        "composite_recalculated",
        tickers=[r.ticker for r in results],
        weights=weights_dict,
    )
    return results


# ── Pipeline Execution Endpoints ────────────────────────────────────────


@router.post("/collect-evidence", response_model=PipelineRunResponse)
async def collect_cs2_evidence(
    request: PipelineRunRequest,
    background_tasks: BackgroundTasks,
):
    """
    Trigger CS2 evidence collection pipeline for a company.

    Collects: SEC filings, job postings, tech stack, patents.
    Stores all data in Snowflake.
    """
    ticker = request.ticker.upper()
    if ticker not in CS3_TICKERS:
        raise HTTPException(status_code=400, detail=f"Unknown ticker: {ticker}")

    task_id = str(uuid4())
    _task_status[task_id] = {
        "task_id": task_id,
        "ticker": ticker,
        "status": "queued",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "pipeline": "cs2_evidence",
    }

    background_tasks.add_task(
        _run_cs2_collection, task_id=task_id, ticker=ticker, skip_sec=request.skip_sec,
    )

    return PipelineRunResponse(
        task_id=task_id,
        ticker=ticker,
        status="queued",
        message=f"CS2 evidence collection started for {ticker}",
    )


@router.post("/collect-cs3", response_model=PipelineRunResponse)
async def collect_cs3_signals(
    request: PipelineRunRequest,
    background_tasks: BackgroundTasks,
):
    """
    Trigger CS3 signal collection (Glassdoor + Board) for a company.
    """
    ticker = request.ticker.upper()
    if ticker not in CS3_TICKERS:
        raise HTTPException(status_code=400, detail=f"Unknown ticker: {ticker}")

    task_id = str(uuid4())
    _task_status[task_id] = {
        "task_id": task_id,
        "ticker": ticker,
        "status": "queued",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "pipeline": "cs3_signals",
    }

    background_tasks.add_task(_run_cs3_collection, task_id=task_id, ticker=ticker)

    return PipelineRunResponse(
        task_id=task_id,
        ticker=ticker,
        status="queued",
        message=f"CS3 signal collection started for {ticker}",
    )


@router.post("/score", response_model=ScoringResponse)
def score_company_endpoint(request: ScoringRequest, db: Session = Depends(get_db)):
    """
    Run the full Org-AI-R scoring pipeline for a company.

    Reads evidence from Snowflake, computes VR/HR/Synergy/Org-AI-R,
    saves results to results/{ticker}.json, and returns the scores.
    """
    ticker = request.ticker.upper()

    company = get_company_by_ticker(db, ticker)
    if not company:
        raise HTTPException(status_code=404, detail=f"Company {ticker} not found")

    try:
        from app.scoring.integration_service import ScoringIntegrationService

        evidence = _load_company_evidence(ticker, db)
        if not evidence:
            raise HTTPException(
                status_code=404, detail=f"No evidence found for {ticker}"
            )

        service = ScoringIntegrationService()
        result = service.score_company(
            ticker=ticker,
            cs2_signals=evidence["cs2_signals"],
            glassdoor_score=evidence["glassdoor_score"],
            board_score=evidence["board_score"],
            evidence_count=evidence["evidence_count"],
            sec_scores=evidence.get("sec_scores"),
            news_score=evidence.get("news_score", 0.0),
        )

        # Add extra metadata
        result["document_count"] = evidence["document_count"]
        result["signal_count"] = evidence["signal_count"]
        result["cs2_signals"] = evidence["cs2_signals"]
        result["glassdoor_score"] = evidence["glassdoor_score"]
        result["board_score"] = evidence["board_score"]
        result["news_score"] = evidence.get("news_score", 0.0)
        result["sec_scores"] = evidence.get("sec_scores", {})

        # Persist to JSON
        results_dir = Path("results")
        results_dir.mkdir(exist_ok=True)
        with open(results_dir / f"{ticker.lower()}.json", "w") as f:
            json.dump(result, f, indent=2, default=str)

        return ScoringResponse(
            ticker=ticker,
            final_score=result["final_score"],
            vr_score=result["vr_score"],
            hr_score=result["hr_score"],
            synergy_score=result["synergy_score"],
            ci_lower=result["ci_lower"],
            ci_upper=result["ci_upper"],
            position_factor=result["position_factor"],
            talent_concentration=result["talent_concentration"],
            dimension_scores=result.get("dimension_scores", {}),
            evidence_count=result.get("evidence_count", 0),
        )
    except HTTPException:
        raise
    except Exception as e:
        log.error("scoring_failed", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=f"Scoring failed: {e}")


@router.post("/score-portfolio")
def score_full_portfolio(db: Session = Depends(get_db)):
    """Score all 5 CS3 companies and return portfolio results."""
    from app.scoring.integration_service import ScoringIntegrationService

    scored = {}
    errors = {}
    service = ScoringIntegrationService()

    for ticker in CS3_TICKERS:
        try:
            evidence = _load_company_evidence(ticker, db)
            if not evidence:
                errors[ticker] = "No evidence"
                continue

            result = service.score_company(
                ticker=ticker,
                cs2_signals=evidence["cs2_signals"],
                glassdoor_score=evidence["glassdoor_score"],
                board_score=evidence["board_score"],
                evidence_count=evidence["evidence_count"],
                sec_scores=evidence.get("sec_scores"),
                news_score=evidence.get("news_score", 0.0),
            )

            # Add extra metadata
            result["document_count"] = evidence["document_count"]
            result["signal_count"] = evidence["signal_count"]
            result["cs2_signals"] = evidence["cs2_signals"]
            result["glassdoor_score"] = evidence["glassdoor_score"]
            result["board_score"] = evidence["board_score"]
            result["news_score"] = evidence.get("news_score", 0.0)
            result["sec_scores"] = evidence.get("sec_scores", {})

            results_dir = Path("results")
            results_dir.mkdir(exist_ok=True)
            with open(results_dir / f"{ticker.lower()}.json", "w") as f:
                json.dump(result, f, indent=2, default=str)

            scored[ticker] = {
                "final_score": result["final_score"],
                "vr_score": result["vr_score"],
                "hr_score": result["hr_score"],
                "synergy_score": result["synergy_score"],
            }
        except Exception as e:
            errors[ticker] = str(e)

    return {
        "scored": scored,
        "errors": errors,
        "total_scored": len(scored),
        "total_errors": len(errors),
    }


# ── Task Status ─────────────────────────────────────────────────────────


@router.get("/status/{task_id}", response_model=TaskStatusResponse)
def get_task_status(task_id: str):
    """Check the status of a background pipeline task."""
    task = _task_status.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskStatusResponse(**task)


@router.get("/tasks")
def list_tasks(limit: int = 20):
    """List recent pipeline tasks."""
    tasks = sorted(
        _task_status.values(),
        key=lambda t: t.get("started_at", ""),
        reverse=True,
    )[:limit]
    return tasks


# ── Evidence Summary Endpoint ───────────────────────────────────────────


@router.get("/evidence-summary/{ticker}")
def get_evidence_summary(ticker: str, db: Session = Depends(get_db)):
    """Get a complete evidence summary for a ticker (from Snowflake)."""
    ticker = ticker.upper()
    company = get_company_by_ticker(db, ticker)
    if not company:
        raise HTTPException(status_code=404, detail=f"Company {ticker} not found")

    summary = get_signal_summary(db, company.id)
    docs = list_documents_db(db, company_id=company.id)
    signals = list_signals_db(db, company_id=company.id)

    return {
        "ticker": ticker,
        "company_id": str(company.id),
        "document_count": len(docs),
        "signal_count": len(signals),
        "summary": {
            "technology_hiring_score": float(summary.technology_hiring_score or 0) if summary else 0,
            "innovation_activity_score": float(summary.innovation_activity_score or 0) if summary else 0,
            "digital_presence_score": float(summary.digital_presence_score or 0) if summary else 0,
            "leadership_signals_score": float(summary.leadership_signals_score or 0) if summary else 0,
            "composite_score": float(summary.composite_score or 0) if summary else 0,
        } if summary else None,
        "documents": [
            {
                "id": str(d.id),
                "filing_type": d.filing_type,
                "filing_date": str(d.filing_date),
                "word_count": d.word_count,
                "chunk_count": d.chunk_count,
            }
            for d in docs[:20]
        ],
        "signals": [
            {
                "id": str(s.id),
                "category": s.category,
                "source": s.source,
                "normalized_score": float(s.normalized_score) if s.normalized_score else None,
            }
            for s in signals[:30]
        ],
    }


# ── Background Task Implementations ────────────────────────────────────


def _run_cs2_collection(task_id: str, ticker: str, skip_sec: bool = False):
    """Background: Run CS2 evidence collection pipeline."""
    _task_status[task_id]["status"] = "running"
    db = get_script_db()

    try:
        company = get_company_by_ticker(db, ticker)
        if not company:
            raise ValueError(f"{ticker} not found in Snowflake")

        company_id = company.id
        result = {}

        # SEC documents
        if not skip_sec:
            from app.pipelines.document_parser import DocumentParser, SemanticChunker
            from app.pipelines.sec_edgar import SECEdgarPipeline
            from app.services.snowflake import insert_document, insert_chunks

            pipeline = SECEdgarPipeline(
                company_name="PE-OrgAIR-Platform",
                email="prajapati.dee@northeastern.edu",
            )
            parser = DocumentParser()
            chunker = SemanticChunker()

            filings = pipeline.download_filings(
                ticker=ticker, filing_types=["10-K"], limit=3, after="2022-01-01",
            )
            doc_count = 0
            for filing_path in filings:
                try:
                    doc = parser.parse_filing(filing_path, ticker)
                    chunks = chunker.chunk_document(doc)
                    doc_row = insert_document(
                        db, company_id=company_id, ticker=ticker,
                        filing_type=doc.filing_type, filing_date=doc.filing_date,
                        content_hash=doc.content_hash, word_count=doc.word_count,
                        chunk_count=len(chunks), source_path=doc.source_path,
                    )
                    insert_chunks(db, document_id=str(doc_row.id), chunks=chunks)
                    doc_count += 1
                except Exception:
                    pass
            result["documents"] = doc_count

        # Job signals
        from app.pipelines.job_signals import JobSignalCollector

        CS3_INFO = {
            "NVDA": "NVIDIA", "JPM": "JPMorgan", "WMT": "Walmart",
            "GE": "GE Aerospace", "DG": "Dollar General",
        }
        name = CS3_INFO.get(ticker, ticker)
        collector = JobSignalCollector()
        postings = collector.scrape_jobs(name, max_results=15)
        postings = [collector.classify_posting(p) for p in postings]
        signal = collector.analyze_job_postings(
            company_id=company_id, company=name, postings=postings,
        )
        insert_signal(
            db, company_id=company_id, category=signal.category.value,
            source=signal.source.value, signal_date=signal.signal_date,
            raw_value=signal.raw_value, normalized_score=signal.normalized_score,
            confidence=signal.confidence, metadata=signal.metadata,
        )
        result["hiring_score"] = signal.normalized_score

        # Tech stack
        from app.pipelines.tech_signals import TechStackCollector

        tech = TechStackCollector()
        techs = tech.get_known_technologies(ticker)
        tech_signal = tech.analyze_tech_stack(company_id=company_id, technologies=techs)
        insert_signal(
            db, company_id=company_id, category=tech_signal.category.value,
            source=tech_signal.source.value, signal_date=tech_signal.signal_date,
            raw_value=tech_signal.raw_value, normalized_score=tech_signal.normalized_score,
            confidence=tech_signal.confidence, metadata=tech_signal.metadata,
        )
        result["tech_score"] = tech_signal.normalized_score

        # Patents
        from app.pipelines.patent_signals import PatentSignalCollector

        ASSIGNEES = {
            "NVDA": "NVIDIA", "JPM": "JPMorgan", "WMT": "Walmart",
            "GE": "General Electric", "DG": "Dollar General",
        }
        patent_col = PatentSignalCollector()
        patents = patent_col.search_patents(assignee_name=ASSIGNEES.get(ticker, ticker))
        pat_signal = patent_col.analyze_patents(company_id=company_id, patents=patents)
        insert_signal(
            db, company_id=company_id, category=pat_signal.category.value,
            source=pat_signal.source.value, signal_date=pat_signal.signal_date,
            raw_value=pat_signal.raw_value, normalized_score=pat_signal.normalized_score,
            confidence=pat_signal.confidence, metadata=pat_signal.metadata,
        )
        result["patent_score"] = pat_signal.normalized_score

        # Update summary — preserve existing leadership score from CS3
        existing_summary = get_signal_summary(db, company_id)
        existing_leadership = (
            float(existing_summary.leadership_signals_score or 0)
            if existing_summary else 0.0
        )
        existing_count = (
            (existing_summary.signal_count or 0)
            if existing_summary else 0
        )
        upsert_signal_summary(
            db, company_id=company_id, ticker=ticker,
            hiring_score=signal.normalized_score,
            innovation_score=pat_signal.normalized_score,
            digital_score=tech_signal.normalized_score,
            leadership_score=existing_leadership,
            signal_count=max(3, existing_count),
        )

        _task_status[task_id].update({
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "result": result,
        })

    except Exception as e:
        _task_status[task_id].update({
            "status": "failed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "error": str(e),
        })
    finally:
        db.close()


def _run_cs3_collection(task_id: str, ticker: str):
    """Background: Run CS3 signal collection (Glassdoor + Board + News)."""
    _task_status[task_id]["status"] = "running"
    db = get_script_db()

    try:
        company = get_company_by_ticker(db, ticker)
        if not company:
            raise ValueError(f"{ticker} not found in Snowflake")

        result = {}

        # Glassdoor
        try:
            from app.pipelines.glassdoor_collector import GlassdoorCultureCollector

            gd = GlassdoorCultureCollector()
            reviews = gd.fetch_reviews(ticker, limit=50)
            culture = gd.analyze_reviews(str(company.id), ticker, reviews)
            insert_signal(
                db, company_id=company.id, category="leadership_signals",
                source="glassdoor", signal_date=datetime.now(timezone.utc),
                raw_value=f"{culture.review_count} reviews, overall={culture.overall_score}",
                normalized_score=float(culture.overall_score),
                confidence=float(culture.confidence),
                metadata={
                    "review_count": culture.review_count,
                    "overall_score": float(culture.overall_score),
                    "innovation": float(culture.innovation_score),
                    "data_driven": float(culture.data_driven_score),
                    "ai_awareness": float(culture.ai_awareness_score),
                    "change_readiness": float(culture.change_readiness_score),
                },
            )
            result["glassdoor_score"] = float(culture.overall_score)
            result["glassdoor_reviews"] = culture.review_count
            log.info("glassdoor_collected", ticker=ticker, score=float(culture.overall_score))
        except Exception as e:
            log.error("glassdoor_collection_failed", ticker=ticker, error=str(e))
            result["glassdoor_error"] = str(e)

        # Board
        try:
            from app.pipelines.board_analyzer import BoardCompositionAnalyzer

            ba = BoardCompositionAnalyzer()
            members, committees, strategy = ba.fetch_board_data(ticker)
            governance = ba.analyze_board(str(company.id), ticker, members, committees, strategy)
            insert_signal(
                db, company_id=company.id, category="leadership_signals",
                source="company_website", signal_date=datetime.now(timezone.utc),
                raw_value=f"Governance={governance.governance_score}",
                normalized_score=float(governance.governance_score),
                confidence=float(governance.confidence),
                metadata={
                    "governance_score": float(governance.governance_score),
                    "has_tech_committee": governance.has_tech_committee,
                    "has_ai_expertise": governance.has_ai_expertise,
                    "ai_experts": governance.ai_experts,
                },
            )
            result["board_score"] = float(governance.governance_score)
            result["ai_experts"] = governance.ai_experts
            log.info("board_collected", ticker=ticker, score=float(governance.governance_score))
        except Exception as e:
            log.error("board_collection_failed", ticker=ticker, error=str(e))
            result["board_error"] = str(e)

        # News / Press Releases
        try:
            from app.pipelines.news_collector import NewsCollector

            nc = NewsCollector()
            articles = nc.collect_news(ticker)
            if articles:
                news_signal = nc.analyze_news(str(company.id), ticker, articles)
                insert_signal(
                    db, company_id=company.id, category="leadership_signals",
                    source="news_press_releases", signal_date=datetime.now(timezone.utc),
                    raw_value=f"{len(articles)} articles, score={news_signal.overall_score}",
                    normalized_score=float(news_signal.overall_score),
                    confidence=float(news_signal.confidence),
                    metadata={
                        "article_count": news_signal.article_count,
                        "ai_article_count": news_signal.ai_article_count,
                        "leadership_score": float(news_signal.leadership_score),
                        "deployment_score": float(news_signal.deployment_score),
                        "investment_score": float(news_signal.investment_score),
                    },
                )
                result["news_score"] = float(news_signal.overall_score)
                result["news_articles"] = news_signal.article_count
                result["news_ai_articles"] = news_signal.ai_article_count
                log.info("news_collected", ticker=ticker, score=float(news_signal.overall_score))
            else:
                result["news_score"] = 0.0
                result["news_articles"] = 0
        except Exception as e:
            log.error("news_collection_failed", ticker=ticker, error=str(e))
            result["news_error"] = str(e)

        # NOTE: CS3 signals (Glassdoor, Board, News) are NOT written into
        # the CS2 composite's leadership_signals_score.  They flow into
        # scoring directly via the Evidence Mapper (Table 1) as separate
        # SignalSources.  Writing them into the composite would double-count
        # their contribution to Leadership/Governance/Culture dimensions.
        # The composite remains a CS2-only dashboard metric.
        log.info(
            "cs3_collection_done", ticker=ticker,
            glassdoor=result.get("glassdoor_score", 0),
            board=result.get("board_score", 0),
            news=result.get("news_score", 0),
        )

        _task_status[task_id].update({
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "result": result,
        })

    except Exception as e:
        _task_status[task_id].update({
            "status": "failed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "error": str(e),
        })
    finally:
        db.close()
