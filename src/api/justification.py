"""
CS4 Justification, IC Prep, and Analyst Notes API.

Endpoints:
  GET  /api/v1/justification/{company_id}/{dimension}  — Score justification
  GET  /api/v1/ic-prep/{company_id}                    — IC meeting package
  POST /api/v1/analyst-notes/interview                 — Submit interview
  POST /api/v1/analyst-notes/dd-finding                — Submit DD finding
  POST /api/v1/analyst-notes/data-room                 — Submit data room summary
  POST /api/v1/analyst-notes/meeting                   — Submit meeting notes
  GET  /api/v1/analyst-notes/{company_id}              — List notes for company
"""

from typing import List, Optional

import structlog
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from src.services.integration.cs3_client import Dimension

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1", tags=["justification"])


# ============================================================================
# Response Models — Justification
# ============================================================================


class CitedEvidenceResponse(BaseModel):
    """Evidence citation in a justification."""
    evidence_id: str
    content: str
    source_type: str
    source_url: Optional[str] = None
    confidence: float
    matched_keywords: List[str]
    relevance_score: float


class JustificationResponse(BaseModel):
    """Score justification response."""
    company_id: str
    dimension: str
    score: float
    level: int
    level_name: str
    confidence_interval: list

    rubric_criteria: str
    rubric_keywords: List[str]

    supporting_evidence: List[CitedEvidenceResponse]
    gaps_identified: List[str]

    generated_summary: str
    evidence_strength: str


# ============================================================================
# Response Models — IC Prep
# ============================================================================


class ICPrepResponse(BaseModel):
    """IC meeting preparation package."""
    company_id: str
    company_name: str
    org_air_score: float
    vr_score: float
    hr_score: float

    executive_summary: str
    key_strengths: List[str]
    key_gaps: List[str]
    risk_factors: List[str]
    recommendation: str

    dimension_justifications: dict  # dimension → justification
    generated_at: str
    total_evidence_count: int
    avg_evidence_strength: str


# ============================================================================
# Request/Response Models — Analyst Notes
# ============================================================================


class InterviewRequest(BaseModel):
    """Submit interview transcript."""
    company_id: str = Field(..., description="Company ticker")
    interviewee: str = Field(..., description="Interviewee name")
    interviewee_title: str = Field(..., description="Interviewee title (CTO, CDO, etc.)")
    transcript: str = Field(..., min_length=10, description="Interview transcript text")
    assessor: str = Field(..., description="Analyst email or name")
    dimensions_discussed: List[str] = Field(
        default=[], description="Dimension names discussed",
    )


class DDFindingRequest(BaseModel):
    """Submit due diligence finding."""
    company_id: str
    title: str = Field(..., min_length=3)
    finding: str = Field(..., min_length=10)
    dimension: str
    severity: str = Field(..., description="critical, major, minor, informational")
    assessor: str


class DataRoomRequest(BaseModel):
    """Submit data room document summary."""
    company_id: str
    document_name: str
    summary: str = Field(..., min_length=10)
    dimension: str
    assessor: str


class MeetingRequest(BaseModel):
    """Submit management meeting notes."""
    company_id: str
    title: str
    notes: str = Field(..., min_length=10)
    attendees: List[str]
    dimensions_discussed: List[str]
    assessor: str


class NoteSubmitResponse(BaseModel):
    """Response after submitting a note."""
    note_id: str
    message: str


class AnalystNoteResponse(BaseModel):
    """Analyst note in list responses."""
    note_id: str
    company_id: str
    note_type: str
    title: str
    content: str
    assessor: str
    confidence: float
    created_at: str
    dimensions_discussed: List[str]
    risk_flags: List[str]


# ============================================================================
# Valid Dimensions
# ============================================================================

VALID_DIMENSIONS = {d.value for d in Dimension}


def _validate_dimension(dim_str: str) -> Dimension:
    """Validate and convert dimension string to enum."""
    if dim_str not in VALID_DIMENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid dimension '{dim_str}'. Valid: {sorted(VALID_DIMENSIONS)}",
        )
    return Dimension(dim_str)


# ============================================================================
# Justification Endpoints
# ============================================================================


@router.get(
    "/justification/{company_id}/{dimension}",
    response_model=JustificationResponse,
)
async def get_justification(
    request: Request,
    company_id: str,
    dimension: str,
):
    """
    Generate score justification for a company dimension.

    Returns rubric-matched evidence, gaps, and an IC-ready summary.
    This is the core CS4 use case: "Why did TechCorp score 72 on Data Infrastructure?"
    """
    dim = _validate_dimension(dimension)
    generator = request.app.state.generator

    try:
        justification = await generator.generate_justification(
            company_id.upper(), dim,
        )

        return JustificationResponse(
            company_id=justification.company_id,
            dimension=justification.dimension.value,
            score=justification.score,
            level=justification.level,
            level_name=justification.level_name,
            confidence_interval=list(justification.confidence_interval),
            rubric_criteria=justification.rubric_criteria,
            rubric_keywords=justification.rubric_keywords,
            supporting_evidence=[
                CitedEvidenceResponse(
                    evidence_id=e.evidence_id,
                    content=e.content,
                    source_type=e.source_type,
                    source_url=e.source_url,
                    confidence=e.confidence,
                    matched_keywords=e.matched_keywords,
                    relevance_score=e.relevance_score,
                )
                for e in justification.supporting_evidence
            ],
            gaps_identified=justification.gaps_identified,
            generated_summary=justification.generated_summary,
            evidence_strength=justification.evidence_strength,
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(
            "justification_failed",
            company=company_id, dimension=dimension, error=str(e),
        )
        raise HTTPException(status_code=500, detail=f"Justification failed: {e}")


# ============================================================================
# IC Prep Endpoints
# ============================================================================


@router.get("/ic-prep/{company_id}", response_model=ICPrepResponse)
async def prepare_ic_meeting(
    request: Request,
    company_id: str,
    focus_dimensions: Optional[str] = Query(
        None,
        description="Comma-separated dimensions to focus on. Defaults to all 7.",
    ),
):
    """
    Generate complete IC meeting preparation package.

    Produces justifications for all dimensions (or a subset),
    executive summary, strengths, gaps, risks, and recommendation.
    """
    workflow = request.app.state.ic_workflow

    # Parse focus dimensions
    dims = None
    if focus_dimensions:
        dim_names = [d.strip() for d in focus_dimensions.split(",")]
        dims = [_validate_dimension(d) for d in dim_names]

    try:
        package = await workflow.prepare_meeting(
            company_id.upper(),
            focus_dimensions=dims,
        )

        # Serialize dimension justifications
        dim_justifications = {}
        for dim, j in package.dimension_justifications.items():
            dim_justifications[dim.value] = {
                "score": j.score,
                "level": j.level,
                "level_name": j.level_name,
                "evidence_count": len(j.supporting_evidence),
                "evidence_strength": j.evidence_strength,
                "gaps": j.gaps_identified,
                "summary": j.generated_summary,
            }

        return ICPrepResponse(
            company_id=package.company.ticker,
            company_name=package.company.name,
            org_air_score=package.assessment.org_air_score,
            vr_score=package.assessment.vr_score,
            hr_score=package.assessment.hr_score,
            executive_summary=package.executive_summary,
            key_strengths=package.key_strengths,
            key_gaps=package.key_gaps,
            risk_factors=package.risk_factors,
            recommendation=package.recommendation,
            dimension_justifications=dim_justifications,
            generated_at=package.generated_at,
            total_evidence_count=package.total_evidence_count,
            avg_evidence_strength=package.avg_evidence_strength,
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("ic_prep_failed", company=company_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"IC prep failed: {e}")


# ============================================================================
# Analyst Notes Endpoints
# ============================================================================


@router.post("/analyst-notes/interview", response_model=NoteSubmitResponse)
async def submit_interview(request: Request, body: InterviewRequest):
    """Submit an interview transcript for indexing."""
    collector = request.app.state.collector

    note_id = await collector.submit_interview(
        company_id=body.company_id,
        interviewee=body.interviewee,
        interviewee_title=body.interviewee_title,
        transcript=body.transcript,
        assessor=body.assessor,
        dimensions_discussed=body.dimensions_discussed,
    )

    return NoteSubmitResponse(
        note_id=note_id,
        message=f"Interview transcript indexed for {body.company_id.upper()}",
    )


@router.post("/analyst-notes/dd-finding", response_model=NoteSubmitResponse)
async def submit_dd_finding(request: Request, body: DDFindingRequest):
    """Submit a due diligence finding."""
    collector = request.app.state.collector

    note_id = await collector.submit_dd_finding(
        company_id=body.company_id,
        title=body.title,
        finding=body.finding,
        dimension=body.dimension,
        severity=body.severity,
        assessor=body.assessor,
    )

    return NoteSubmitResponse(
        note_id=note_id,
        message=f"DD finding indexed for {body.company_id.upper()}",
    )


@router.post("/analyst-notes/data-room", response_model=NoteSubmitResponse)
async def submit_data_room(request: Request, body: DataRoomRequest):
    """Submit a data room document summary."""
    collector = request.app.state.collector

    note_id = await collector.submit_data_room_summary(
        company_id=body.company_id,
        document_name=body.document_name,
        summary=body.summary,
        dimension=body.dimension,
        assessor=body.assessor,
    )

    return NoteSubmitResponse(
        note_id=note_id,
        message=f"Data room summary indexed for {body.company_id.upper()}",
    )


@router.post("/analyst-notes/meeting", response_model=NoteSubmitResponse)
async def submit_meeting(request: Request, body: MeetingRequest):
    """Submit management meeting notes."""
    collector = request.app.state.collector

    note_id = await collector.submit_management_meeting(
        company_id=body.company_id,
        title=body.title,
        notes=body.notes,
        attendees=body.attendees,
        dimensions_discussed=body.dimensions_discussed,
        assessor=body.assessor,
    )

    return NoteSubmitResponse(
        note_id=note_id,
        message=f"Meeting notes indexed for {body.company_id.upper()}",
    )


@router.get("/analyst-notes/{company_id}", response_model=List[AnalystNoteResponse])
async def list_analyst_notes(request: Request, company_id: str):
    """List all analyst notes for a company."""
    collector = request.app.state.collector

    notes = collector.get_notes_for_company(company_id.upper())

    return [
        AnalystNoteResponse(
            note_id=n.note_id,
            company_id=n.company_id,
            note_type=n.note_type.value,
            title=n.title,
            content=n.content[:500],
            assessor=n.assessor,
            confidence=n.confidence,
            created_at=n.created_at.isoformat(),
            dimensions_discussed=n.dimensions_discussed,
            risk_flags=n.risk_flags,
        )
        for n in notes
    ]
