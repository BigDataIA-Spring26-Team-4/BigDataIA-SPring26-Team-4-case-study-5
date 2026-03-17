"""
Collect and index analyst notes and interview transcripts.

Task 8.0d: Analyst Notes Collector — primary source evidence.

Post-LOI due diligence produces high-confidence evidence:
  - Interview transcripts (CTO, CDO, CFO)
  - Management meeting notes
  - Site visit observations
  - Due diligence findings
  - Data room document summaries

This collector indexes analyst-generated evidence into the hybrid
retriever at confidence=1.0 (primary source = highest confidence),
making it searchable alongside CS2 evidence.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

import structlog

from src.services.retrieval.hybrid import HybridRetriever

logger = structlog.get_logger()


# ============================================================================
# Note Types
# ============================================================================


class NoteType(str, Enum):
    """Types of analyst-generated evidence."""
    INTERVIEW_TRANSCRIPT = "interview_transcript"
    MANAGEMENT_MEETING = "management_meeting"
    SITE_VISIT = "site_visit"
    DD_FINDING = "dd_finding"
    DATA_ROOM_SUMMARY = "data_room_summary"


# ============================================================================
# Analyst Note Dataclass
# ============================================================================


@dataclass
class AnalystNote:
    """Analyst-generated evidence item."""
    note_id: str
    company_id: str
    note_type: NoteType
    title: str
    content: str

    # Interview metadata
    interviewee: Optional[str] = None
    interviewee_title: Optional[str] = None

    # Assessment context
    dimensions_discussed: List[str] = field(default_factory=list)
    key_findings: List[str] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)

    # Provenance
    assessor: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    confidence: float = 1.0   # Primary source = highest confidence


# ============================================================================
# Analyst Notes Collector
# ============================================================================


class AnalystNotesCollector:
    """
    API for analysts to submit and index notes into the evidence store.

    All submitted notes are indexed in the hybrid retriever (both dense
    and sparse) with confidence=1.0, making them rank highly in search
    results alongside CS2 evidence.

    Usage:
        collector = AnalystNotesCollector(retriever)
        note_id = await collector.submit_interview(
            company_id="NVDA",
            interviewee="Jane Smith",
            interviewee_title="CTO",
            transcript="...",
            assessor="analyst@pe-firm.com",
            dimensions_discussed=["technology_stack", "data_infrastructure"],
        )
    """

    def __init__(self, retriever: HybridRetriever):
        self._retriever = retriever
        self._notes: Dict[str, AnalystNote] = {}  # In-memory note store

    @property
    def notes(self) -> Dict[str, AnalystNote]:
        """Access stored notes."""
        return self._notes

    # ── Submit Methods ──────────────────────────────────────────

    async def submit_interview(
        self,
        company_id: str,
        interviewee: str,
        interviewee_title: str,
        transcript: str,
        assessor: str,
        dimensions_discussed: Optional[List[str]] = None,
    ) -> str:
        """
        Submit interview transcript for indexing.

        Returns the generated note_id.
        """
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        note_id = f"interview_{company_id.upper()}_{timestamp}"

        # Determine primary dimension from discussed dimensions
        primary_dim = (
            dimensions_discussed[0] if dimensions_discussed else "leadership"
        )

        note = AnalystNote(
            note_id=note_id,
            company_id=company_id.upper(),
            note_type=NoteType.INTERVIEW_TRANSCRIPT,
            title=f"Interview: {interviewee_title} — {interviewee}",
            content=transcript,
            interviewee=interviewee,
            interviewee_title=interviewee_title,
            dimensions_discussed=dimensions_discussed or [],
            assessor=assessor,
        )
        self._notes[note_id] = note

        # Index into hybrid retriever
        doc = {
            "doc_id": note_id,
            "content": f"Interview with {interviewee_title}: {transcript}",
            "metadata": {
                "company_id": company_id.upper(),
                "source_type": NoteType.INTERVIEW_TRANSCRIPT.value,
                "dimension": primary_dim,
                "confidence": 1.0,
                "assessor": assessor,
                "interviewee_title": interviewee_title,
            },
        }
        self._retriever.index_documents([doc])

        logger.info(
            "interview_indexed",
            note_id=note_id,
            company=company_id,
            interviewee_title=interviewee_title,
        )
        return note_id

    async def submit_dd_finding(
        self,
        company_id: str,
        title: str,
        finding: str,
        dimension: str,
        severity: str,
        assessor: str,
    ) -> str:
        """
        Submit due diligence finding.

        severity: "critical", "major", "minor", "informational"
        Returns the generated note_id.
        """
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        note_id = f"dd_{company_id.upper()}_{timestamp}"

        note = AnalystNote(
            note_id=note_id,
            company_id=company_id.upper(),
            note_type=NoteType.DD_FINDING,
            title=title,
            content=finding,
            dimensions_discussed=[dimension],
            risk_flags=[severity] if severity in ("critical", "major") else [],
            assessor=assessor,
        )
        self._notes[note_id] = note

        doc = {
            "doc_id": note_id,
            "content": f"DD Finding [{severity}]: {title}\n\n{finding}",
            "metadata": {
                "company_id": company_id.upper(),
                "source_type": NoteType.DD_FINDING.value,
                "dimension": dimension,
                "confidence": 1.0,
                "assessor": assessor,
                "severity": severity,
            },
        }
        self._retriever.index_documents([doc])

        logger.info(
            "dd_finding_indexed",
            note_id=note_id,
            company=company_id,
            dimension=dimension,
            severity=severity,
        )
        return note_id

    async def submit_data_room_summary(
        self,
        company_id: str,
        document_name: str,
        summary: str,
        dimension: str,
        assessor: str,
    ) -> str:
        """
        Submit data room document summary.

        Returns the generated note_id.
        """
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        note_id = f"dataroom_{company_id.upper()}_{timestamp}"

        note = AnalystNote(
            note_id=note_id,
            company_id=company_id.upper(),
            note_type=NoteType.DATA_ROOM_SUMMARY,
            title=f"Data Room: {document_name}",
            content=summary,
            dimensions_discussed=[dimension],
            assessor=assessor,
        )
        self._notes[note_id] = note

        doc = {
            "doc_id": note_id,
            "content": f"Data Room Document: {document_name}\n\n{summary}",
            "metadata": {
                "company_id": company_id.upper(),
                "source_type": NoteType.DATA_ROOM_SUMMARY.value,
                "dimension": dimension,
                "confidence": 1.0,
                "assessor": assessor,
                "document_name": document_name,
            },
        }
        self._retriever.index_documents([doc])

        logger.info(
            "data_room_indexed",
            note_id=note_id,
            company=company_id,
            document=document_name,
        )
        return note_id

    async def submit_management_meeting(
        self,
        company_id: str,
        title: str,
        notes: str,
        attendees: List[str],
        dimensions_discussed: List[str],
        assessor: str,
    ) -> str:
        """
        Submit management meeting notes.

        Returns the generated note_id.
        """
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        note_id = f"meeting_{company_id.upper()}_{timestamp}"

        primary_dim = (
            dimensions_discussed[0] if dimensions_discussed else "leadership"
        )

        note = AnalystNote(
            note_id=note_id,
            company_id=company_id.upper(),
            note_type=NoteType.MANAGEMENT_MEETING,
            title=title,
            content=notes,
            dimensions_discussed=dimensions_discussed,
            assessor=assessor,
        )
        self._notes[note_id] = note

        doc = {
            "doc_id": note_id,
            "content": (
                f"Management Meeting: {title}\n"
                f"Attendees: {', '.join(attendees)}\n\n{notes}"
            ),
            "metadata": {
                "company_id": company_id.upper(),
                "source_type": NoteType.MANAGEMENT_MEETING.value,
                "dimension": primary_dim,
                "confidence": 1.0,
                "assessor": assessor,
            },
        }
        self._retriever.index_documents([doc])

        logger.info(
            "meeting_notes_indexed",
            note_id=note_id,
            company=company_id,
            attendees=len(attendees),
        )
        return note_id

    # ── Query Methods ───────────────────────────────────────────

    def get_notes_for_company(self, company_id: str) -> List[AnalystNote]:
        """Get all analyst notes for a company."""
        ticker = company_id.upper()
        return [
            note for note in self._notes.values()
            if note.company_id == ticker
        ]

    def get_note(self, note_id: str) -> Optional[AnalystNote]:
        """Get a single note by ID."""
        return self._notes.get(note_id)

    def get_notes_by_type(
        self, company_id: str, note_type: NoteType
    ) -> List[AnalystNote]:
        """Get notes filtered by type."""
        ticker = company_id.upper()
        return [
            note for note in self._notes.values()
            if note.company_id == ticker and note.note_type == note_type
        ]

    def get_risk_flags(self, company_id: str) -> List[str]:
        """Get all risk flags from analyst notes for a company."""
        flags = []
        for note in self.get_notes_for_company(company_id):
            flags.extend(note.risk_flags)
        return flags

    def get_stats(self) -> Dict:
        """Get collector statistics."""
        by_type = {}
        by_company = {}
        for note in self._notes.values():
            by_type[note.note_type.value] = by_type.get(note.note_type.value, 0) + 1
            by_company[note.company_id] = by_company.get(note.company_id, 0) + 1

        return {
            "total_notes": len(self._notes),
            "by_type": by_type,
            "by_company": by_company,
        }
