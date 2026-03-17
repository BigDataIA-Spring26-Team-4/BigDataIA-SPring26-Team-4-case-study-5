"""
Document parsing and semantic chunking for SEC filings.

Case Study 2: Parses PDF and HTML SEC filings, extracts key sections
(Item 1, 1A, 7), and implements semantic chunking with overlap for
later LLM processing and vector search.
"""

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber
from bs4 import BeautifulSoup

from app.models.document import DocumentChunk, ParsedDocument


class DocumentParser:
    """Parse SEC filings from various formats."""

    # Regex patterns for section extraction
    SECTION_PATTERNS = {
        "item_1": r"(?:ITEM\s*1[.\s]*BUSINESS)",
        "item_1a": r"(?:ITEM\s*1A[.\s]*RISK\s*FACTORS)",
        "item_7": r"(?:ITEM\s*7[.\s]*MANAGEMENT)",
        "item_7a": r"(?:ITEM\s*7A[.\s]*QUANTITATIVE)",
    }

    def parse_filing(self, file_path: Path, ticker: str) -> ParsedDocument:
        """Parse a filing and extract structured content."""
        suffix = file_path.suffix.lower()

        if suffix == ".pdf":
            content = self._parse_pdf(file_path)
        elif suffix in [".htm", ".html", ".txt"]:
            content = self._parse_html(file_path)
        else:
            raise ValueError(f"Unsupported file type: {suffix}")

        # Extract sections
        sections = self._extract_sections(content)

        # Generate content hash for deduplication
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        # Extract filing metadata from path
        filing_type, filing_date = self._extract_metadata(file_path)

        return ParsedDocument(
            company_ticker=ticker,
            filing_type=filing_type,
            filing_date=filing_date,
            content=content,
            sections=sections,
            source_path=str(file_path),
            content_hash=content_hash,
            word_count=len(content.split()),
        )

    def _parse_pdf(self, file_path: Path) -> str:
        """Extract text from PDF using pdfplumber."""
        text_parts = []

        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)

        return "\n\n".join(text_parts)

    def _parse_html(self, file_path: Path) -> str:
        """Extract text from HTML filing."""
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            soup = BeautifulSoup(f.read(), "html.parser")

        # Remove script and style elements
        for element in soup(["script", "style"]):
            element.decompose()

        # Get text
        text = soup.get_text(separator="\n")

        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        text = "\n".join(line for line in lines if line)

        return text

    # Ordered end-markers so we know which ITEM follows which
    SECTION_END_PATTERNS = {
        "item_1": r"ITEM\s*1\s*A|ITEM\s*1\s*B",
        "item_1a": r"ITEM\s*1\s*B|ITEM\s*1\s*C|ITEM\s*2[.\s]",
        "item_7": r"ITEM\s*7\s*A|ITEM\s*8[.\s]",
        "item_7a": r"ITEM\s*8[.\s]",
    }

    def _extract_sections(self, content: str) -> dict[str, str]:
        """Extract key sections from 10-K content.

        Finds ALL occurrences of each section header and keeps the
        longest match — this skips TOC entries (which are short) and
        captures the real section body.
        """
        sections = {}
        content_upper = content.upper()

        for section_name, pattern in self.SECTION_PATTERNS.items():
            best_text = ""
            end_pattern = self.SECTION_END_PATTERNS.get(
                section_name, r"ITEM\s*\d"
            )

            for match in re.finditer(pattern, content_upper):
                start = match.start()

                # Search for the end marker at least 500 chars after start
                # to skip past the header itself
                search_start = start + 500
                end_match = re.search(end_pattern, content_upper[search_start:])
                if end_match:
                    end = search_start + end_match.start()
                else:
                    end = len(content)

                candidate = content[start:end]

                # Keep the longest candidate (real body, not TOC)
                if len(candidate) > len(best_text):
                    best_text = candidate

            if best_text and len(best_text.split()) > 50:
                sections[section_name] = best_text[:50000]

        return sections

    def _extract_metadata(self, file_path: Path) -> tuple[str, datetime]:
        """Extract filing type and date from file path."""
        # Path structure: .../ticker/filing_type/accession/file
        parts = file_path.parts
        filing_type = parts[-3] if len(parts) > 2 else "UNKNOWN"

        # Try to extract date from accession number (format: 0000000000-YY-NNNNNN)
        accession = parts[-2] if len(parts) > 1 else ""
        date_match = re.search(r"-(\d{2})-", accession)
        if date_match:
            year = int(date_match.group(1))
            year = 2000 + year if year < 50 else 1900 + year
            filing_date = datetime(year, 1, 1, tzinfo=timezone.utc)
        else:
            filing_date = datetime.now(timezone.utc)

        return filing_type, filing_date


class SemanticChunker:
    """Chunk documents with section awareness."""

    def __init__(
        self,
        chunk_size: int = 1000,   # Target words per chunk
        chunk_overlap: int = 100,  # Overlap in words
        min_chunk_size: int = 200,  # Minimum chunk size
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size

    def chunk_document(self, doc: ParsedDocument) -> list[DocumentChunk]:
        """Split document into overlapping chunks."""
        chunks = []

        # Chunk each section separately to preserve context
        for section_name, section_content in doc.sections.items():
            section_chunks = self._chunk_text(
                section_content, doc.content_hash, section_name
            )
            chunks.extend(section_chunks)

        # Also chunk any remaining content if no sections found
        if not doc.sections:
            chunks = self._chunk_text(doc.content, doc.content_hash, None)

        return chunks

    def _chunk_text(
        self, text: str, doc_id: str, section: str | None
    ) -> list[DocumentChunk]:
        """Split text into overlapping chunks."""
        words = text.split()
        chunks = []

        start_idx = 0
        chunk_index = 0

        while start_idx < len(words):
            end_idx = min(start_idx + self.chunk_size, len(words))

            # Don't create tiny final chunks
            if len(words) - end_idx < self.min_chunk_size:
                end_idx = len(words)

            chunk_words = words[start_idx:end_idx]
            chunk_content = " ".join(chunk_words)

            # Calculate character positions (approximate)
            start_char = len(" ".join(words[:start_idx]))
            end_char = start_char + len(chunk_content)

            chunks.append(
                DocumentChunk(
                    document_id=doc_id,
                    chunk_index=chunk_index,
                    content=chunk_content,
                    section=section,
                    start_char=start_char,
                    end_char=end_char,
                    word_count=len(chunk_words),
                )
            )

            # Move forward with overlap
            start_idx = end_idx - self.chunk_overlap
            chunk_index += 1

            if end_idx >= len(words):
                break

        return chunks
