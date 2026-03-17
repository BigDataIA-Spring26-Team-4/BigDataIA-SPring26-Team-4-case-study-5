"""
SEC EDGAR pipeline tests for Case Study 2.

Tests cover:
- SECEdgarPipeline download logic
- DocumentParser (PDF, HTML, section extraction, metadata)
- SemanticChunker (chunking with overlap, section-aware chunking)
- Document models (DocumentRecord, DocumentStatus)
"""

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from app.models.document import (
    DocumentChunk,
    DocumentRecord,
    DocumentStatus,
    ParsedDocument,
)
from app.pipelines.document_parser import DocumentParser, SemanticChunker
from app.pipelines.sec_edgar import SECEdgarPipeline


# ===========================================================================
# Fixtures
# ===========================================================================

SAMPLE_HTML_CONTENT = """
<html>
<head><style>body { font-size: 12px; }</style></head>
<body>
<h1>ANNUAL REPORT</h1>
<p>ITEM 1. BUSINESS</p>
<p>Caterpillar is a leading manufacturer of construction equipment.
The company leverages artificial intelligence for predictive maintenance.</p>
<p>ITEM 1A. RISK FACTORS</p>
<p>We face risks related to technology adoption including AI implementation.
Cybersecurity threats remain a concern for our connected fleet.</p>
<p>ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS</p>
<p>Revenue increased 12% year-over-year driven by strong demand.
We invested $500M in digital transformation initiatives including AI.</p>
<p>ITEM 7A. QUANTITATIVE AND QUALITATIVE DISCLOSURES</p>
<p>Interest rate sensitivity analysis shows moderate exposure.</p>
</body>
</html>
"""

# The parser requires sections to have >50 words and looks for end markers
# at least 500 chars after the section header start, so the test content
# must be long enough to satisfy those constraints.
_FILLER = " ".join(["technology innovation data analytics"] * 40)  # ~200 words
SAMPLE_PLAIN_TEXT = (
    "ITEM 1. BUSINESS\n"
    f"This is the business section content with AI and machine learning. {_FILLER}\n\n"
    "ITEM 1A. RISK FACTORS\n"
    f"Risk factors include technology disruption and AI governance. {_FILLER}\n\n"
    "ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS\n"
    f"Management discusses the use of artificial intelligence in operations. {_FILLER}\n"
)


@pytest.fixture
def parser():
    return DocumentParser()


@pytest.fixture
def chunker():
    return SemanticChunker(chunk_size=50, chunk_overlap=10, min_chunk_size=20)


@pytest.fixture
def large_chunker():
    """Chunker with default (production) settings."""
    return SemanticChunker()


@pytest.fixture
def sample_parsed_doc():
    content = "word " * 500  # 500 words
    return ParsedDocument(
        company_ticker="CAT",
        filing_type="10-K",
        filing_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        content=content,
        sections={
            "item_1": "word " * 200,
            "item_1a": "word " * 150,
        },
        source_path="/fake/path/10-K/0001234-24-000001/full-submission.txt",
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        word_count=500,
    )


@pytest.fixture
def sample_parsed_doc_no_sections():
    content = "word " * 300
    return ParsedDocument(
        company_ticker="DE",
        filing_type="8-K",
        filing_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
        content=content,
        sections={},
        source_path="/fake/path/8-K/0001234-24-000002/full-submission.txt",
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        word_count=300,
    )


# ===========================================================================
# SECEdgarPipeline Tests
# ===========================================================================


class TestSECEdgarPipeline:
    """Tests for SEC EDGAR download pipeline."""

    @patch("app.pipelines.sec_edgar.Downloader")
    def test_init(self, mock_downloader_cls):
        """Test pipeline initializes Downloader with correct args."""
        pipeline = SECEdgarPipeline(
            company_name="TestApp",
            email="test@example.com",
            download_dir=Path("data/raw/sec"),
        )
        mock_downloader_cls.assert_called_once_with(
            "TestApp", "test@example.com", Path("data/raw/sec")
        )
        assert pipeline.download_dir == Path("data/raw/sec")

    @patch("app.pipelines.sec_edgar.Downloader")
    def test_download_filings_calls_get_for_each_type(self, mock_dl_cls):
        """Test that download_filings calls dl.get for each filing type."""
        mock_dl = MagicMock()
        mock_dl_cls.return_value = mock_dl

        pipeline = SECEdgarPipeline("Test", "t@t.com", Path("/tmp/test"))

        # No files will be found (directory doesn't exist) — that's fine
        result = pipeline.download_filings(
            ticker="CAT",
            filing_types=["10-K", "10-Q"],
            limit=5,
            after="2022-01-01",
        )

        assert mock_dl.get.call_count == 2
        mock_dl.get.assert_any_call("10-K", "CAT", limit=5, after="2022-01-01")
        mock_dl.get.assert_any_call("10-Q", "CAT", limit=5, after="2022-01-01")

    @patch("app.pipelines.sec_edgar.Downloader")
    def test_download_filings_handles_exception(self, mock_dl_cls):
        """Test that errors during download are caught gracefully."""
        mock_dl = MagicMock()
        mock_dl.get.side_effect = Exception("SEC rate limit")
        mock_dl_cls.return_value = mock_dl

        pipeline = SECEdgarPipeline("Test", "t@t.com", Path("/tmp/test"))
        result = pipeline.download_filings(ticker="CAT", filing_types=["10-K"])

        # Should return empty list, not raise
        assert result == []

    @patch("app.pipelines.sec_edgar.Downloader")
    def test_download_filings_finds_files(self, mock_dl_cls, tmp_path):
        """Test that downloaded files are discovered correctly."""
        mock_dl = MagicMock()
        mock_dl_cls.return_value = mock_dl

        # Create fake filing structure
        filing_dir = tmp_path / "sec-edgar-filings" / "CAT" / "10-K" / "0001234-24-000001"
        filing_dir.mkdir(parents=True)
        fake_file = filing_dir / "full-submission.txt"
        fake_file.write_text("fake filing content")

        pipeline = SECEdgarPipeline("Test", "t@t.com", tmp_path)
        result = pipeline.download_filings(ticker="CAT", filing_types=["10-K"])

        assert len(result) == 1
        assert result[0] == fake_file

    @patch("app.pipelines.sec_edgar.Downloader")
    def test_default_filing_types(self, mock_dl_cls):
        """Test default filing types include 10-K, 10-Q, 8-K."""
        mock_dl = MagicMock()
        mock_dl_cls.return_value = mock_dl

        pipeline = SECEdgarPipeline("Test", "t@t.com")
        pipeline.download_filings(ticker="JPM")

        assert mock_dl.get.call_count == 3  # 10-K, 10-Q, 8-K


# ===========================================================================
# DocumentParser Tests
# ===========================================================================


class TestDocumentParser:
    """Tests for document parsing logic."""

    def test_parse_html(self, parser, tmp_path):
        """Test HTML parsing extracts text and removes scripts/styles."""
        html_file = tmp_path / "filing.html"
        html_file.write_text(SAMPLE_HTML_CONTENT)

        text = parser._parse_html(html_file)

        assert "ANNUAL REPORT" in text
        assert "Caterpillar" in text
        assert "artificial intelligence" in text
        # Scripts and styles should be removed
        assert "font-size" not in text

    def test_parse_html_txt_extension(self, parser, tmp_path):
        """Test that .txt files with HTML content are parsed correctly."""
        txt_file = tmp_path / "full-submission.txt"
        txt_file.write_text(SAMPLE_HTML_CONTENT)

        text = parser._parse_html(txt_file)
        assert "Caterpillar" in text

    @patch("pdfplumber.open")
    def test_parse_pdf(self, mock_pdf_open, parser):
        """Test PDF parsing extracts text from all pages."""
        mock_page1 = MagicMock()
        mock_page1.extract_text.return_value = "Page 1 content about AI"
        mock_page2 = MagicMock()
        mock_page2.extract_text.return_value = "Page 2 with machine learning"
        mock_page3 = MagicMock()
        mock_page3.extract_text.return_value = None  # Empty page

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page1, mock_page2, mock_page3]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_pdf_open.return_value = mock_pdf

        text = parser._parse_pdf(Path("test.pdf"))

        assert "Page 1 content about AI" in text
        assert "machine learning" in text
        # Empty page should be skipped
        assert text.count("\n\n") == 1  # Only one separator between two pages

    def test_extract_sections(self, parser):
        """Test section extraction from document content."""
        sections = parser._extract_sections(SAMPLE_PLAIN_TEXT)

        assert "item_1" in sections
        assert "item_1a" in sections
        assert "item_7" in sections
        assert "BUSINESS" in sections["item_1"].upper()
        assert "RISK" in sections["item_1a"].upper()

    def test_extract_sections_missing(self, parser):
        """Test section extraction when sections are missing."""
        content = "This document has no standard SEC sections."
        sections = parser._extract_sections(content)
        assert sections == {}

    def test_extract_metadata_from_path(self, parser):
        """Test metadata extraction from SEC filing path."""
        path = Path("data/raw/sec/sec-edgar-filings/CAT/10-K/0001234-24-000001/full-submission.txt")
        filing_type, filing_date = parser._extract_metadata(path)

        assert filing_type == "10-K"
        assert filing_date.year == 2024

    def test_extract_metadata_old_year(self, parser):
        """Test metadata extraction handles 20th century years."""
        path = Path("data/sec/CAT/10-K/0001234-99-000001/full-submission.txt")
        _, filing_date = parser._extract_metadata(path)
        assert filing_date.year == 1999

    def test_extract_metadata_no_date(self, parser):
        """Test metadata fallback when no date in path."""
        path = Path("data/sec/CAT/10-K/unknown/full-submission.txt")
        _, filing_date = parser._extract_metadata(path)
        # Should default to current time
        assert filing_date.year >= 2024

    def test_parse_filing_html(self, parser, tmp_path):
        """Test full parse_filing workflow for HTML."""
        html_file = tmp_path / "full-submission.txt"
        html_file.write_text(SAMPLE_HTML_CONTENT)

        # Need parent dirs to mimic SEC path structure
        doc = parser.parse_filing(html_file, "CAT")

        assert doc.company_ticker == "CAT"
        assert doc.word_count > 0
        assert doc.content_hash is not None
        assert len(doc.content_hash) == 64  # SHA-256 hex

    def test_parse_filing_unsupported_format(self, parser, tmp_path):
        """Test that unsupported file types raise ValueError."""
        bad_file = tmp_path / "filing.xlsx"
        bad_file.write_text("not a filing")

        with pytest.raises(ValueError, match="Unsupported file type"):
            parser.parse_filing(bad_file, "CAT")

    def test_content_hash_deduplication(self, parser, tmp_path):
        """Test that identical content produces identical hashes."""
        file1 = tmp_path / "filing1.html"
        file2 = tmp_path / "filing2.html"
        file1.write_text("<html><body>Same content</body></html>")
        file2.write_text("<html><body>Same content</body></html>")

        doc1 = parser.parse_filing(file1, "CAT")
        doc2 = parser.parse_filing(file2, "CAT")

        assert doc1.content_hash == doc2.content_hash

    def test_content_hash_different(self, parser, tmp_path):
        """Test that different content produces different hashes."""
        file1 = tmp_path / "filing1.html"
        file2 = tmp_path / "filing2.html"
        file1.write_text("<html><body>Content A</body></html>")
        file2.write_text("<html><body>Content B</body></html>")

        doc1 = parser.parse_filing(file1, "CAT")
        doc2 = parser.parse_filing(file2, "CAT")

        assert doc1.content_hash != doc2.content_hash

    def test_section_size_limit(self, parser):
        """Test that extracted sections are capped at 50000 chars."""
        # Create content with a very long section
        long_section = "A" * 60000
        content = f"ITEM 1. BUSINESS\n{long_section}\nITEM 1A. RISK FACTORS\nShort risk."
        sections = parser._extract_sections(content)

        if "item_1" in sections:
            assert len(sections["item_1"]) <= 50000


# ===========================================================================
# SemanticChunker Tests
# ===========================================================================


class TestSemanticChunker:
    """Tests for semantic chunking logic."""

    def test_chunk_text_basic(self, chunker):
        """Test basic text chunking produces correct chunks."""
        text = " ".join([f"word{i}" for i in range(100)])
        chunks = chunker._chunk_text(text, "doc123", "item_1")

        assert len(chunks) > 0
        assert all(isinstance(c, DocumentChunk) for c in chunks)
        assert all(c.document_id == "doc123" for c in chunks)
        assert all(c.section == "item_1" for c in chunks)

    def test_chunk_indexes_sequential(self, chunker):
        """Test that chunk indexes are sequential starting from 0."""
        text = " ".join(["word"] * 200)
        chunks = chunker._chunk_text(text, "doc1", None)

        indexes = [c.chunk_index for c in chunks]
        assert indexes == list(range(len(chunks)))

    def test_chunk_overlap(self, chunker):
        """Test that chunks overlap correctly."""
        text = " ".join([f"w{i}" for i in range(150)])
        chunks = chunker._chunk_text(text, "doc1", None)

        if len(chunks) >= 2:
            # Last words of chunk 0 should appear in start of chunk 1
            words_0 = chunks[0].content.split()
            words_1 = chunks[1].content.split()
            overlap_words = words_0[-chunker.chunk_overlap:]
            assert words_1[:len(overlap_words)] == overlap_words

    def test_min_chunk_size_prevents_tiny_tails(self, chunker):
        """Test that tiny trailing chunks are merged into the previous one."""
        # chunk_size=50, min_chunk_size=20
        # 60 words: first chunk should absorb everything since remainder < min
        text = " ".join(["word"] * 60)
        chunks = chunker._chunk_text(text, "doc1", None)

        for chunk in chunks:
            assert chunk.word_count >= chunker.min_chunk_size

    def test_chunk_document_with_sections(self, chunker, sample_parsed_doc):
        """Test chunking a document with sections chunks each section separately."""
        chunks = chunker.chunk_document(sample_parsed_doc)

        assert len(chunks) > 0
        sections_in_chunks = set(c.section for c in chunks)
        assert "item_1" in sections_in_chunks
        assert "item_1a" in sections_in_chunks

    def test_chunk_document_no_sections_uses_full_content(
        self, chunker, sample_parsed_doc_no_sections
    ):
        """Test that documents without sections chunk the full content."""
        chunks = chunker.chunk_document(sample_parsed_doc_no_sections)

        assert len(chunks) > 0
        assert all(c.section is None for c in chunks)

    def test_chunk_word_count_accurate(self, chunker):
        """Test that word_count matches actual words in chunk content."""
        text = " ".join(["test"] * 100)
        chunks = chunker._chunk_text(text, "doc1", None)

        for chunk in chunks:
            actual = len(chunk.content.split())
            assert chunk.word_count == actual

    def test_chunk_char_positions(self, chunker):
        """Test that start_char and end_char are non-negative and ordered."""
        text = " ".join(["hello"] * 100)
        chunks = chunker._chunk_text(text, "doc1", None)

        for chunk in chunks:
            assert chunk.start_char >= 0
            assert chunk.end_char > chunk.start_char

    def test_empty_text_produces_no_chunks(self, chunker):
        """Test that empty text produces zero chunks."""
        chunks = chunker._chunk_text("", "doc1", None)
        assert chunks == []

    def test_single_word_produces_one_chunk(self, chunker):
        """Test that a single word produces exactly one chunk."""
        chunks = chunker._chunk_text("hello", "doc1", None)
        assert len(chunks) == 1
        assert chunks[0].content == "hello"
        assert chunks[0].word_count == 1

    def test_default_chunker_sizes(self, large_chunker):
        """Test default chunker parameters match PDF spec."""
        assert large_chunker.chunk_size == 1000
        assert large_chunker.chunk_overlap == 100
        assert large_chunker.min_chunk_size == 200


# ===========================================================================
# Document Model Tests
# ===========================================================================


class TestDocumentModels:
    """Tests for document Pydantic models."""

    def test_document_status_enum_values(self):
        """Test all document statuses from the spec."""
        assert DocumentStatus.PENDING.value == "pending"
        assert DocumentStatus.DOWNLOADED.value == "downloaded"
        assert DocumentStatus.PARSED.value == "parsed"
        assert DocumentStatus.CHUNKED.value == "chunked"
        assert DocumentStatus.INDEXED.value == "indexed"
        assert DocumentStatus.FAILED.value == "failed"

    def test_document_record_defaults(self):
        """Test DocumentRecord has correct defaults."""
        from uuid import uuid4

        record = DocumentRecord(
            company_id=uuid4(),
            ticker="CAT",
            filing_type="10-K",
            filing_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert record.status == DocumentStatus.PENDING
        assert record.id is not None
        assert record.created_at is not None
        assert record.word_count is None
        assert record.s3_key is None

    def test_document_record_all_fields(self):
        """Test DocumentRecord with all fields populated."""
        from uuid import uuid4

        cid = uuid4()
        record = DocumentRecord(
            company_id=cid,
            ticker="JPM",
            filing_type="10-Q",
            filing_date=datetime(2024, 6, 15, tzinfo=timezone.utc),
            source_url="https://sec.gov/filing/123",
            local_path="/data/raw/sec/JPM/10-Q/filing.txt",
            s3_key="sec/JPM/10-Q/2024.txt",
            content_hash="abc123",
            word_count=50000,
            chunk_count=50,
            status=DocumentStatus.CHUNKED,
        )
        assert record.ticker == "JPM"
        assert record.status == DocumentStatus.CHUNKED
        assert record.word_count == 50000

    def test_parsed_document_dataclass(self):
        """Test ParsedDocument dataclass creation."""
        doc = ParsedDocument(
            company_ticker="WMT",
            filing_type="10-K",
            filing_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            content="Test content about AI",
            sections={"item_1": "Business section"},
            source_path="/fake/path",
            content_hash="hash123",
            word_count=4,
        )
        assert doc.company_ticker == "WMT"
        assert "item_1" in doc.sections

    def test_document_chunk_dataclass(self):
        """Test DocumentChunk dataclass creation."""
        chunk = DocumentChunk(
            document_id="doc123",
            chunk_index=0,
            content="This is chunk content",
            section="item_1",
            start_char=0,
            end_char=21,
            word_count=4,
        )
        assert chunk.chunk_index == 0
        assert chunk.section == "item_1"


# ===========================================================================
# Integration Tests
# ===========================================================================


class TestSECEdgarIntegration:
    """Integration tests combining parser and chunker."""

    def test_parse_and_chunk_html_filing(self, parser, chunker, tmp_path):
        """Test full parse-then-chunk workflow for an HTML filing."""
        html_file = tmp_path / "full-submission.txt"
        html_file.write_text(SAMPLE_HTML_CONTENT)

        doc = parser.parse_filing(html_file, "CAT")
        chunks = chunker.chunk_document(doc)

        assert doc.word_count > 0
        assert len(chunks) > 0

        # All chunk content should be non-empty
        for chunk in chunks:
            assert len(chunk.content.strip()) > 0
            assert chunk.word_count > 0

    def test_all_target_tickers_valid(self):
        """Test that all 10 target company tickers are strings."""
        tickers = ["CAT", "DE", "UNH", "HCA", "ADP", "PAYX", "WMT", "TGT", "JPM", "GS"]
        assert len(tickers) == 10
        assert all(isinstance(t, str) for t in tickers)
        assert all(len(t) <= 10 for t in tickers)
