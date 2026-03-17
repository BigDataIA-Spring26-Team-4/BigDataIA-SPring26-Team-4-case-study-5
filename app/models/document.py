"""
Document models for SEC filings and evidence collection.

Case Study 2: Defines data structures for SEC documents,
parsed content, and document chunks for LLM processing.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class DocumentStatus(str, Enum):
    """Document processing status."""

    PENDING = "pending"
    DOWNLOADED = "downloaded"
    PARSED = "parsed"
    CHUNKED = "chunked"
    INDEXED = "indexed"
    FAILED = "failed"


class DocumentRecord(BaseModel):
    """Metadata record for a document stored in the database."""

    id: UUID = Field(default_factory=uuid4)
    company_id: UUID
    ticker: str
    filing_type: str
    filing_date: datetime
    source_url: str | None = None
    local_path: str | None = None
    s3_key: str | None = None
    content_hash: str | None = None
    word_count: int | None = None
    chunk_count: int | None = None
    status: DocumentStatus = DocumentStatus.PENDING
    error_message: str | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    processed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


@dataclass
class ParsedDocument:
    """Represents a parsed SEC document."""

    company_ticker: str
    filing_type: str
    filing_date: datetime
    content: str
    sections: dict[str, str]
    source_path: str
    content_hash: str
    word_count: int


@dataclass
class DocumentChunk:
    """A chunk of a document for processing."""

    document_id: str
    chunk_index: int
    content: str
    section: str | None
    start_char: int
    end_char: int
    word_count: int
