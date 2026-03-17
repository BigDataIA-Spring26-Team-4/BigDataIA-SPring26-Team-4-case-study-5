"""
Snowflake database service for PE Org-AI-R Platform.

ORM models match EXACTLY the PDF schema (Section 5.1):
- Table names are PLURAL
- Field names match PDF exactly
- Data types match PDF specification
"""

import json
import uuid
from datetime import datetime, date, timezone
from typing import Optional
from urllib.parse import quote_plus

import structlog
from sqlalchemy import (
    create_engine,
    Column,
    String,
    Numeric,
    Date,
    DateTime,
    Integer,
    Text,
    ForeignKey,
    func,
    Boolean,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from fastapi import HTTPException

from app.config import settings
from app.models.company import CompanyCreate, CompanyUpdate, IndustryCreate
from app.models.assessment import (
    AssessmentCreate,
    AssessmentUpdate,
    AssessmentStatus,
    validate_status_transition,
)
from app.models.dimension import DimensionScoreCreate, DimensionScoreUpdate

log = structlog.get_logger(__name__)

# ============================================================================
# Engine & Session Setup
# ============================================================================

# Build connection string with URL-encoded credentials
connection_string = (
    f"snowflake://{quote_plus(settings.SNOWFLAKE_USER)}:"
    f"{quote_plus(settings.SNOWFLAKE_PASSWORD.get_secret_value())}@"
    f"{settings.SNOWFLAKE_ACCOUNT}/"
    f"{settings.SNOWFLAKE_DATABASE}/"
    f"{settings.SNOWFLAKE_SCHEMA}"
    f"?warehouse={settings.SNOWFLAKE_WAREHOUSE}"
)

if settings.SNOWFLAKE_ROLE:
    connection_string += f"&role={settings.SNOWFLAKE_ROLE}"

engine = create_engine(
    connection_string,
    echo=settings.DEBUG,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

Base = declarative_base()


def get_db():
    """Dependency to get database session."""
    db = SessionLocal()
    log.debug("db_session_opened")
    try:
        yield db
    finally:
        db.close()
        log.debug("db_session_closed")


# ============================================================================
# ORM Models (Match PDF Section 5.1 EXACTLY)
# ============================================================================

class IndustryRow(Base):
    """Industries table - PDF Section 5.1, Line 2-8"""
    __tablename__ = "industries"  # PLURAL per PDF

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, unique=True)
    sector = Column(String(100), nullable=False)
    h_r_base = Column(Numeric(5, 2), nullable=False)
    created_at = Column(DateTime, default=func.current_timestamp())


class CompanyRow(Base):
    """Companies table - PDF Section 5.1, Line 10-21"""
    __tablename__ = "companies"  # PLURAL per PDF

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    ticker = Column(String(10), nullable=True)
    industry_id = Column(String(36), ForeignKey("industries.id"), nullable=False)
    position_factor = Column(Numeric(4, 3), nullable=False, default=0.0)  # DECIMAL(4,3) per PDF
    is_deleted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.current_timestamp())
    updated_at = Column(DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp())


class AssessmentRow(Base):
    """Assessments table - PDF Section 5.1, Line 23-40"""
    __tablename__ = "assessments"  # PLURAL per PDF

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id = Column(String(36), ForeignKey("companies.id"), nullable=False)
    assessment_type = Column(String(20), nullable=False)  # Not "type"!
    assessment_date = Column(Date, nullable=False)  # DATE not DATETIME per PDF
    status = Column(String(20), nullable=False, default="draft")
    primary_assessor = Column(String(255), nullable=True)  # Not "assessor_name"!
    secondary_assessor = Column(String(255), nullable=True)  # Not "assessor_email"!
    v_r_score = Column(Numeric(5, 2), nullable=True)  # DECIMAL(5,2) per PDF
    confidence_lower = Column(Numeric(5, 2), nullable=True)  # Not "lower_bound"!
    confidence_upper = Column(Numeric(5, 2), nullable=True)  # Not "upper_bound"!
    created_at = Column(DateTime, default=func.current_timestamp())


class DimensionScoreRow(Base):
    """Dimension_scores table - PDF Section 5.1, Line 42-58"""
    __tablename__ = "dimension_scores"  # PLURAL per PDF

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    assessment_id = Column(String(36), ForeignKey("assessments.id"), nullable=False)
    dimension = Column(String(30), nullable=False)
    score = Column(Numeric(5, 2), nullable=False)  # DECIMAL(5,2) per PDF
    weight = Column(Numeric(4, 3), nullable=False)  # DECIMAL(4,3) per PDF
    confidence = Column(Numeric(4, 3), nullable=False, default=0.8)  # DECIMAL(4,3) per PDF
    evidence_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=func.current_timestamp())


# ============================================================================
# Industry CRUD
# ============================================================================

def create_industry(db: Session, data: IndustryCreate) -> IndustryRow:
    """Create a new industry."""
    log.info("db_create_industry", name=data.name)
    row = IndustryRow(
        name=data.name,
        sector=data.sector,
        h_r_base=float(data.h_r_base),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ============================================================================
# CS2: Evidence Collection ORM Models (documents, chunks, signals)
# ============================================================================


class DocumentRow(Base):
    """documents table — SEC filings metadata."""
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id = Column(String(36), ForeignKey("companies.id"), nullable=False)
    ticker = Column(String(10), nullable=False)
    filing_type = Column(String(20), nullable=False)
    filing_date = Column(Date, nullable=False)
    source_url = Column(String(500), nullable=True)
    local_path = Column(String(500), nullable=True)
    s3_key = Column(String(500), nullable=True)
    content_hash = Column(String(64), nullable=True)
    word_count = Column(Integer, nullable=True)
    chunk_count = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    error_message = Column(String(1000), nullable=True)
    created_at = Column(DateTime, default=func.current_timestamp())
    processed_at = Column(DateTime, nullable=True)


class DocumentChunkRow(Base):
    """document_chunks table — chunked text for LLM processing."""
    __tablename__ = "document_chunks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    section = Column(String(50), nullable=True)
    start_char = Column(Integer, nullable=True)
    end_char = Column(Integer, nullable=True)
    word_count = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=func.current_timestamp())


class ExternalSignalRow(Base):
    """external_signals table — hiring, patent, tech stack signals."""
    __tablename__ = "external_signals"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id = Column(String(36), ForeignKey("companies.id"), nullable=False)
    category = Column(String(30), nullable=False)
    source = Column(String(30), nullable=False)
    signal_date = Column(Date, nullable=False)
    raw_value = Column(String(500), nullable=True)
    normalized_score = Column(Numeric(5, 2), nullable=True)
    confidence = Column(Numeric(4, 3), nullable=True)
    metadata_ = Column("metadata", String(4000), nullable=True)
    created_at = Column(DateTime, default=func.current_timestamp())


class CompanySignalSummaryRow(Base):
    """company_signal_summaries table — aggregated scores per company."""
    __tablename__ = "company_signal_summaries"

    company_id = Column(String(36), ForeignKey("companies.id"), primary_key=True)
    ticker = Column(String(10), nullable=False)
    technology_hiring_score = Column(Numeric(5, 2), nullable=True)
    innovation_activity_score = Column(Numeric(5, 2), nullable=True)
    digital_presence_score = Column(Numeric(5, 2), nullable=True)
    leadership_signals_score = Column(Numeric(5, 2), nullable=True)
    composite_score = Column(Numeric(5, 2), nullable=True)
    signal_count = Column(Integer, nullable=True)
    last_updated = Column(DateTime, nullable=True)


# ============================================================================
# CS2: Helper — standalone DB session for scripts
# ============================================================================


def get_script_db() -> Session:
    """Get a DB session for use in scripts (not a FastAPI dependency)."""
    return SessionLocal()


# ============================================================================
# CS2: Company lookup by ticker
# ============================================================================


def get_company_by_ticker(db: Session, ticker: str) -> Optional[CompanyRow]:
    """Find a company by ticker symbol."""
    return (
        db.query(CompanyRow)
        .filter(CompanyRow.ticker == ticker, CompanyRow.is_deleted == False)
        .first()
    )


def get_company_by_ticker_with_industry(db: Session, ticker: str) -> Optional[dict]:
    """
    Find a company by ticker with industry sector data joined.

    CS4 Integration: Returns company metadata in the format CS4's
    CS1 client expects, including sector from the industries table.
    """
    result = (
        db.query(CompanyRow, IndustryRow)
        .join(IndustryRow, CompanyRow.industry_id == IndustryRow.id)
        .filter(CompanyRow.ticker == ticker, CompanyRow.is_deleted == False)
        .first()
    )
    if not result:
        return None

    company, industry = result
    return {
        "company_id": company.id,
        "ticker": company.ticker,
        "name": company.name,
        "sector": industry.sector,
        "sub_sector": industry.name,
        "market_cap_percentile": max(0.0, min(1.0, (float(company.position_factor) + 1) / 2)),
        "position_factor": float(company.position_factor),
        "industry_id": company.industry_id,
        "created_at": str(company.created_at) if company.created_at else None,
        "updated_at": str(company.updated_at) if company.updated_at else None,
    }


# ============================================================================
# CS2: Document CRUD
# ============================================================================


def insert_document(
    db: Session,
    company_id: str,
    ticker: str,
    filing_type: str,
    filing_date,
    content_hash: str,
    word_count: int,
    chunk_count: int,
    source_path: str,
    status: str = "chunked",
) -> DocumentRow:
    """Insert a document record. Deduplicates by content_hash."""
    existing = (
        db.query(DocumentRow)
        .filter(DocumentRow.content_hash == content_hash)
        .first()
    )
    if existing:
        log.info("document_already_exists", content_hash=content_hash[:12])
        return existing

    fd = filing_date
    if isinstance(fd, datetime):
        fd = fd.date()

    row = DocumentRow(
        company_id=company_id,
        ticker=ticker,
        filing_type=filing_type,
        filing_date=fd,
        local_path=source_path,
        content_hash=content_hash,
        word_count=word_count,
        chunk_count=chunk_count,
        status=status,
        processed_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log.info("document_inserted", id=row.id, ticker=ticker, filing_type=filing_type)
    return row


def insert_chunks(db: Session, document_id: str, chunks: list) -> int:
    """Insert document chunks. Returns count inserted."""
    count = 0
    for chunk in chunks:
        row = DocumentChunkRow(
            document_id=document_id,
            chunk_index=chunk.chunk_index,
            content=chunk.content[:60000],
            section=chunk.section,
            start_char=chunk.start_char,
            end_char=chunk.end_char,
            word_count=chunk.word_count,
        )
        db.add(row)
        count += 1
    db.commit()
    log.info("chunks_inserted", document_id=document_id, count=count)
    return count


def list_documents_db(
    db: Session,
    company_id: Optional[str] = None,
    filing_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
) -> list[DocumentRow]:
    """List documents with optional filters."""
    q = db.query(DocumentRow)
    if company_id:
        q = q.filter(DocumentRow.company_id == company_id)
    if filing_type:
        q = q.filter(DocumentRow.filing_type == filing_type)
    if status:
        q = q.filter(DocumentRow.status == status)
    return q.order_by(DocumentRow.created_at.desc()).limit(limit).all()


def get_document_by_id(db: Session, document_id: str) -> Optional[DocumentRow]:
    """Get a single document by ID."""
    return db.query(DocumentRow).filter(DocumentRow.id == document_id).first()


def get_chunks_for_document(db: Session, document_id: str) -> list[DocumentChunkRow]:
    """Get all chunks for a document, ordered by chunk_index."""
    return (
        db.query(DocumentChunkRow)
        .filter(DocumentChunkRow.document_id == document_id)
        .order_by(DocumentChunkRow.chunk_index)
        .all()
    )


# ============================================================================
# CS2: Signal CRUD
# ============================================================================


def insert_signal(
    db: Session,
    company_id: str,
    category: str,
    source: str,
    signal_date,
    raw_value: str,
    normalized_score: float,
    confidence: float,
    metadata: dict,
) -> ExternalSignalRow:
    """Insert an external signal."""
    sd = signal_date
    if isinstance(sd, datetime):
        sd = sd.date()

    row = ExternalSignalRow(
        company_id=company_id,
        category=category,
        source=source,
        signal_date=sd,
        raw_value=raw_value,
        normalized_score=float(normalized_score),
        confidence=float(confidence),
        metadata_=json.dumps(metadata, default=str),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log.info("signal_inserted", id=row.id, category=category, score=normalized_score)
    return row


def list_signals_db(
    db: Session,
    company_id: Optional[str] = None,
    category: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 100,
) -> list[ExternalSignalRow]:
    """List signals with optional filters."""
    q = db.query(ExternalSignalRow)
    if company_id:
        q = q.filter(ExternalSignalRow.company_id == company_id)
    if category:
        q = q.filter(ExternalSignalRow.category == category)
    if source:
        q = q.filter(ExternalSignalRow.source == source)
    return q.order_by(ExternalSignalRow.created_at.desc()).limit(limit).all()


def get_signals_by_company_category(
    db: Session, company_id: str, category: str,
) -> list[ExternalSignalRow]:
    """Get signals for a company by category."""
    return (
        db.query(ExternalSignalRow)
        .filter(
            ExternalSignalRow.company_id == company_id,
            ExternalSignalRow.category == category,
        )
        .order_by(ExternalSignalRow.created_at.desc())
        .all()
    )


def upsert_signal_summary(
    db: Session,
    company_id: str,
    ticker: str,
    hiring_score: float,
    innovation_score: float,
    digital_score: float,
    leadership_score: float,
    signal_count: int,
    weights: Optional[dict] = None,
) -> CompanySignalSummaryRow:
    """Insert or update the company signal summary.

    Args:
        weights: Optional dict with keys 'technology_hiring',
                 'innovation_activity', 'digital_presence',
                 'leadership_signals'. Defaults to 0.30/0.25/0.25/0.20.
    """
    w = weights or {}
    w_hiring = w.get("technology_hiring", 0.30)
    w_innovation = w.get("innovation_activity", 0.25)
    w_digital = w.get("digital_presence", 0.25)
    w_leadership = w.get("leadership_signals", 0.20)
    composite = (
        w_hiring * hiring_score
        + w_innovation * innovation_score
        + w_digital * digital_score
        + w_leadership * leadership_score
    )

    row = (
        db.query(CompanySignalSummaryRow)
        .filter(CompanySignalSummaryRow.company_id == company_id)
        .first()
    )

    if row:
        row.technology_hiring_score = hiring_score
        row.innovation_activity_score = innovation_score
        row.digital_presence_score = digital_score
        row.leadership_signals_score = leadership_score
        row.composite_score = round(composite, 2)
        row.signal_count = signal_count
        row.last_updated = datetime.now(timezone.utc)
    else:
        row = CompanySignalSummaryRow(
            company_id=company_id,
            ticker=ticker,
            technology_hiring_score=hiring_score,
            innovation_activity_score=innovation_score,
            digital_presence_score=digital_score,
            leadership_signals_score=leadership_score,
            composite_score=round(composite, 2),
            signal_count=signal_count,
            last_updated=datetime.now(timezone.utc),
        )
        db.add(row)

    db.commit()
    db.refresh(row)
    log.info("signal_summary_upserted", company_id=company_id, ticker=ticker, composite=round(composite, 2))
    return row


def get_signal_summary(db: Session, company_id: str) -> Optional[CompanySignalSummaryRow]:
    """Get the signal summary for a company."""
    return (
        db.query(CompanySignalSummaryRow)
        .filter(CompanySignalSummaryRow.company_id == company_id)
        .first()
    )


def get_all_evidence_for_company(db: Session, company_id: str) -> dict:
    """Get all evidence (documents + signals + summary) for one company."""
    docs = list_documents_db(db, company_id=company_id)
    signals = list_signals_db(db, company_id=company_id)
    summary = get_signal_summary(db, company_id)
    return {"documents": docs, "signals": signals, "summary": summary}


def get_evidence_stats(db: Session) -> dict:
    """Get overall evidence collection statistics."""
    return {
        "total_documents": db.query(DocumentRow).count(),
        "total_chunks": db.query(DocumentChunkRow).count(),
        "total_signals": db.query(ExternalSignalRow).count(),
        "companies_with_signals": db.query(CompanySignalSummaryRow).count(),
    }


def list_industries(db: Session) -> list[IndustryRow]:
    """List all industries."""
    log.debug("db_list_industries")
    return db.query(IndustryRow).all()


def get_industry(db: Session, industry_id: str) -> IndustryRow:
    """Get industry by ID."""
    row = db.query(IndustryRow).filter(IndustryRow.id == industry_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Industry not found")
    return row


# ============================================================================
# Company CRUD
# ============================================================================

def create_company(db: Session, data: CompanyCreate) -> CompanyRow:
    """Create a new company."""
    log.info("db_create_company", name=data.name)
    row = CompanyRow(
        name=data.name,
        ticker=data.ticker,
        industry_id=str(data.industry_id),
        position_factor=float(data.position_factor),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log.info("db_company_created", company_id=row.id)
    return row


def list_companies(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    industry_id: Optional[str] = None
) -> list[CompanyRow]:
    """List companies with pagination and optional filtering."""
    log.debug("db_list_companies", skip=skip, limit=limit, industry_id=industry_id)
    
    query = db.query(CompanyRow).filter(CompanyRow.is_deleted == False)
    
    if industry_id:
        query = query.filter(CompanyRow.industry_id == industry_id)
    
    return query.offset(skip).limit(limit).all()


def count_companies(db: Session, industry_id: Optional[str] = None) -> int:
    """Count total companies (for pagination)."""
    query = db.query(CompanyRow).filter(CompanyRow.is_deleted == False)
    
    if industry_id:
        query = query.filter(CompanyRow.industry_id == industry_id)
    
    return query.count()


def get_company(db: Session, company_id: str) -> CompanyRow:
    """Get a company by ID."""
    log.debug("db_get_company", company_id=company_id)
    row = (
        db.query(CompanyRow)
        .filter(CompanyRow.id == company_id, CompanyRow.is_deleted == False)
        .first()
    )
    if not row:
        log.warning("company_not_found", company_id=company_id)
        raise HTTPException(status_code=404, detail="Company not found")
    return row


def update_company(db: Session, company_id: str, data: CompanyUpdate) -> CompanyRow:
    """Update a company."""
    log.info("db_update_company", company_id=company_id)
    row = get_company(db, company_id)
    
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        if field == "industry_id" and value is not None:
            value = str(value)
        elif field == "position_factor" and value is not None:
            value = float(value)
        setattr(row, field, value)
    
    row.updated_at = datetime.now()
    db.commit()
    db.refresh(row)
    return row


def delete_company(db: Session, company_id: str) -> None:
    """Soft delete a company."""
    log.info("db_delete_company", company_id=company_id)
    row = get_company(db, company_id)
    row.is_deleted = True
    db.commit()


# ============================================================================
# Assessment CRUD
# ============================================================================

def create_assessment(db: Session, data: AssessmentCreate) -> AssessmentRow:
    """Create a new assessment."""
    log.info(
        "db_create_assessment",
        company_id=str(data.company_id),
        type=data.assessment_type.value
    )
    
    # Convert datetime to date if needed
    assessment_date = data.assessment_date
    if isinstance(assessment_date, datetime):
        assessment_date = assessment_date.date()
    
    row = AssessmentRow(
        company_id=str(data.company_id),
        assessment_type=data.assessment_type.value,
        assessment_date=assessment_date,
        status=AssessmentStatus.DRAFT.value,
        primary_assessor=data.primary_assessor,
        secondary_assessor=data.secondary_assessor,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log.info("db_assessment_created", assessment_id=row.id)
    return row


def list_assessments(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    company_id: Optional[str] = None
) -> list[AssessmentRow]:
    """List assessments with optional filtering."""
    log.debug("db_list_assessments", skip=skip, limit=limit, company_id=company_id)
    
    query = db.query(AssessmentRow)
    if company_id:
        query = query.filter(AssessmentRow.company_id == company_id)
    
    return query.offset(skip).limit(limit).all()


def count_assessments(db: Session, company_id: Optional[str] = None) -> int:
    """Count total assessments (for pagination)."""
    query = db.query(AssessmentRow)
    if company_id:
        query = query.filter(AssessmentRow.company_id == company_id)
    return query.count()


def get_assessment(db: Session, assessment_id: str) -> AssessmentRow:
    """Get an assessment by ID."""
    log.debug("db_get_assessment", assessment_id=assessment_id)
    row = db.query(AssessmentRow).filter(AssessmentRow.id == assessment_id).first()
    if not row:
        log.warning("assessment_not_found", assessment_id=assessment_id)
        raise HTTPException(status_code=404, detail="Assessment not found")
    return row


def update_assessment(
    db: Session,
    assessment_id: str,
    data: AssessmentUpdate
) -> AssessmentRow:
    """Update an assessment."""
    log.info("db_update_assessment", assessment_id=assessment_id)
    row = get_assessment(db, assessment_id)
    
    updates = data.model_dump(exclude_unset=True)
    
    # Validate status transition if status is being updated
    if "status" in updates and updates["status"] is not None:
        current_status = AssessmentStatus(row.status)
        new_status = updates["status"]
        
        if not validate_status_transition(current_status, new_status):
            log.warning(
                "invalid_status_transition",
                assessment_id=assessment_id,
                current=current_status.value,
                requested=new_status.value,
            )
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status transition from '{current_status.value}' to '{new_status.value}'"
            )
        updates["status"] = new_status.value
    
    # Convert enums to values
    if "assessment_type" in updates and updates["assessment_type"] is not None:
        updates["assessment_type"] = updates["assessment_type"].value
    
    if "company_id" in updates and updates["company_id"] is not None:
        updates["company_id"] = str(updates["company_id"])
    
    # Convert datetime to date if needed
    if "assessment_date" in updates and updates["assessment_date"] is not None:
        if isinstance(updates["assessment_date"], datetime):
            updates["assessment_date"] = updates["assessment_date"].date()
    
    # Convert numeric fields
    for field in ["v_r_score", "confidence_lower", "confidence_upper"]:
        if field in updates and updates[field] is not None:
            updates[field] = float(updates[field])
    
    for field, value in updates.items():
        setattr(row, field, value)
    
    db.commit()
    db.refresh(row)
    return row


# ============================================================================
# Dimension Score CRUD
# ============================================================================

def add_scores(
    db: Session,
    assessment_id: str,
    scores: list[DimensionScoreCreate]
) -> list[DimensionScoreRow]:
    """Add dimension scores to an assessment."""
    log.info("db_add_scores", assessment_id=assessment_id, count=len(scores))
    
    # Verify assessment exists
    get_assessment(db, assessment_id)
    
    rows = []
    for score in scores:
        row = DimensionScoreRow(
            assessment_id=assessment_id,
            dimension=score.dimension.value,
            score=float(score.score),
            weight=float(score.weight),
            confidence=float(score.confidence),
            evidence_count=score.evidence_count,
        )
        db.add(row)
        rows.append(row)
    
    db.commit()
    for r in rows:
        db.refresh(r)
    
    return rows


def get_scores(db: Session, assessment_id: str) -> list[DimensionScoreRow]:
    """Get all dimension scores for an assessment."""
    log.debug("db_get_scores", assessment_id=assessment_id)
    
    # Verify assessment exists
    get_assessment(db, assessment_id)
    
    return (
        db.query(DimensionScoreRow)
        .filter(DimensionScoreRow.assessment_id == assessment_id)
        .all()
    )


def update_score(
    db: Session,
    score_id: str,
    data: DimensionScoreUpdate
) -> DimensionScoreRow:
    """Update a single dimension score."""
    log.info("db_update_score", score_id=score_id)
    
    row = db.query(DimensionScoreRow).filter(DimensionScoreRow.id == score_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Dimension score not found")
    
    updates = data.model_dump(exclude_unset=True)
    
    # Convert numeric fields
    for field in ["score", "weight", "confidence"]:
        if field in updates and updates[field] is not None:
            updates[field] = float(updates[field])
    
    for field, value in updates.items():
        setattr(row, field, value)
    
    db.commit()
    db.refresh(row)
    return row
