"""
CS2 Evidence Collection API client.

Task 7.0b: Connect to CS2 Evidence Collection.
CS2 produces evidence with rich metadata that CS4 must preserve:
  - source_type: SEC 10-K Item 1, Item 1A, Item 7, job posting, etc.
  - signal_category: technology_hiring, innovation_activity, etc.
  - confidence: Extraction confidence (0-1)
  - extracted_entities: Structured entities from the text

Wraps the existing FastAPI document/signal/evidence endpoints.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx
import structlog

logger = structlog.get_logger()


# ============================================================================
# Enums (per CS4 PDF Section 3)
# ============================================================================


class SourceType(str, Enum):
    """Evidence source types from CS2."""
    SEC_10K_ITEM_1 = "sec_10k_item_1"       # Business description
    SEC_10K_ITEM_1A = "sec_10k_item_1a"     # Risk factors
    SEC_10K_ITEM_7 = "sec_10k_item_7"       # MD&A
    JOB_POSTING_LINKEDIN = "job_posting_linkedin"
    JOB_POSTING_INDEED = "job_posting_indeed"
    PATENT_USPTO = "patent_uspto"
    PRESS_RELEASE = "press_release"
    GLASSDOOR_REVIEW = "glassdoor_review"
    BOARD_PROXY_DEF14A = "board_proxy_def14a"
    ANALYST_INTERVIEW = "analyst_interview"  # DD interviews
    DD_DATA_ROOM = "dd_data_room"           # Data room docs
    NEWS_ARTICLE = "news_article"           # News/press releases


class SignalCategory(str, Enum):
    """Signal categories from CS2 collectors."""
    TECHNOLOGY_HIRING = "technology_hiring"
    INNOVATION_ACTIVITY = "innovation_activity"
    DIGITAL_PRESENCE = "digital_presence"
    LEADERSHIP_SIGNALS = "leadership_signals"
    CULTURE_SIGNALS = "culture_signals"
    GOVERNANCE_SIGNALS = "governance_signals"


# ============================================================================
# Mapping from CS3 data to CS4 enums
# ============================================================================

# Map CS3 filing type / signal source → SourceType
_SOURCE_TYPE_MAP = {
    "10-K": SourceType.SEC_10K_ITEM_7,
    "10-Q": SourceType.SEC_10K_ITEM_7,
    "8-K": SourceType.PRESS_RELEASE,
    # Signal sources
    "indeed": SourceType.JOB_POSTING_INDEED,
    "linkedin": SourceType.JOB_POSTING_LINKEDIN,
    "glassdoor": SourceType.GLASSDOOR_REVIEW,
    "company_website": SourceType.BOARD_PROXY_DEF14A,
    "news_press_releases": SourceType.NEWS_ARTICLE,
    "patentsview": SourceType.PATENT_USPTO,
}

# Map CS3 chunk section → more specific SourceType
_SECTION_SOURCE_MAP = {
    "item_1": SourceType.SEC_10K_ITEM_1,
    "item_1a": SourceType.SEC_10K_ITEM_1A,
    "item_7": SourceType.SEC_10K_ITEM_7,
}

# Map CS3 signal category → SignalCategory
_CATEGORY_MAP = {
    "technology_hiring": SignalCategory.TECHNOLOGY_HIRING,
    "innovation_activity": SignalCategory.INNOVATION_ACTIVITY,
    "digital_presence": SignalCategory.DIGITAL_PRESENCE,
    "leadership_signals": SignalCategory.LEADERSHIP_SIGNALS,
}


# ============================================================================
# Dataclasses
# ============================================================================


@dataclass
class ExtractedEntity:
    """Entity extracted from evidence text."""
    entity_type: str    # "ai_investment", "technology", "person", etc.
    text: str
    confidence: float
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CS2Evidence:
    """Evidence item from CS2 Evidence Collection."""
    evidence_id: str
    company_id: str
    source_type: SourceType
    signal_category: SignalCategory
    content: str
    extracted_at: datetime
    confidence: float

    # Optional metadata
    fiscal_year: Optional[int] = None
    source_url: Optional[str] = None
    page_number: Optional[int] = None
    extracted_entities: List[ExtractedEntity] = field(default_factory=list)

    # Indexing status
    indexed_in_cs4: bool = False
    indexed_at: Optional[datetime] = None


# ============================================================================
# CS2 Client
# ============================================================================


class CS2Client:
    """
    Client for CS2 Evidence Collection API.

    Fetches evidence from:
      - GET /api/v1/documents (SEC filing metadata)
      - GET /api/v1/documents/{id}/chunks (document text chunks)
      - GET /api/v1/signals (external signals: jobs, patents, tech)
      - GET /api/v1/evidence/companies/{id} (combined evidence view)
    """

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=60.0)

    async def _resolve_company_id(self, ticker: str) -> Optional[str]:
        """
        Resolve ticker → Snowflake UUID company_id.

        The CS3 API stores company_id as UUID in Snowflake, but CS4
        passes tickers (NVDA, JPM, etc). This bridge resolves the
        ticker to the actual UUID via /api/v1/companies/by-ticker/.
        """
        try:
            response = await self.client.get(
                f"{self.base_url}/api/v1/companies/by-ticker/{ticker.upper()}"
            )
            response.raise_for_status()
            data = response.json()
            uuid = data.get("company_id") or data.get("id", "")
            logger.info("cs2_ticker_resolved", ticker=ticker, company_id=uuid[:12] + "...")
            return uuid
        except Exception as e:
            logger.warning("cs2_ticker_resolve_failed", ticker=ticker, error=str(e))
            return None

    async def get_evidence(
        self,
        company_id: str,
        source_types: Optional[List[SourceType]] = None,
        signal_categories: Optional[List[SignalCategory]] = None,
        min_confidence: float = 0.0,
    ) -> List[CS2Evidence]:
        """
        Fetch all evidence for a company — documents + signals.

        Combines document chunks (SEC filings) and external signals
        (jobs, patents, tech stack, glassdoor, board, news) into
        a unified CS2Evidence list.
        """
        # Resolve ticker → UUID (Snowflake uses UUID, not ticker)
        resolved_id = await self._resolve_company_id(company_id)
        if not resolved_id:
            logger.warning("cs2_no_company_found", ticker=company_id)
            return []

        evidence_list: List[CS2Evidence] = []

        # Fetch document chunks (using UUID)
        doc_evidence = await self._fetch_document_evidence(company_id, resolved_id)
        evidence_list.extend(doc_evidence)

        # Fetch signal-based evidence (using UUID)
        signal_evidence = await self._fetch_signal_evidence(company_id, resolved_id)
        evidence_list.extend(signal_evidence)

        # Apply filters
        if source_types:
            type_set = set(source_types)
            evidence_list = [e for e in evidence_list if e.source_type in type_set]

        if signal_categories:
            cat_set = set(signal_categories)
            evidence_list = [e for e in evidence_list if e.signal_category in cat_set]

        if min_confidence > 0:
            evidence_list = [e for e in evidence_list if e.confidence >= min_confidence]

        logger.info(
            "cs2_evidence_fetched",
            company_id=company_id,
            total=len(evidence_list),
        )
        return evidence_list

    async def mark_indexed(self, evidence_ids: List[str]) -> int:
        """
        Mark evidence as indexed in CS4.

        NOTE: This is tracked in-memory by the CS4 layer since CS3's
        Snowflake schema doesn't have an indexed_in_cs4 column.
        Returns the count of IDs marked.
        """
        logger.info("cs2_mark_indexed", count=len(evidence_ids))
        return len(evidence_ids)

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    # ── Internal: Document Evidence ─────────────────────────────

    async def _fetch_document_evidence(
        self, ticker: str, snowflake_id: str
    ) -> List[CS2Evidence]:
        """Fetch SEC filing chunks as evidence items."""
        evidence = []

        try:
            # Get documents using Snowflake UUID (not ticker)
            response = await self.client.get(
                f"{self.base_url}/api/v1/documents",
                params={"company_id": snowflake_id, "limit": 100},
            )
            response.raise_for_status()
            documents = response.json()

            for doc in documents:
                doc_id = doc["id"]
                filing_type = doc.get("filing_type", "10-K")
                filing_date = doc.get("filing_date", "")

                # Derive fiscal year from filing date
                fiscal_year = None
                if filing_date:
                    try:
                        fiscal_year = int(filing_date[:4])
                    except (ValueError, IndexError):
                        pass

                # Fetch chunks for this document
                try:
                    chunk_resp = await self.client.get(
                        f"{self.base_url}/api/v1/documents/{doc_id}/chunks"
                    )
                    chunk_resp.raise_for_status()
                    chunks = chunk_resp.json()
                except httpx.HTTPError:
                    chunks = []

                for chunk in chunks:
                    section = (chunk.get("section") or "").lower().strip()
                    content = chunk.get("content", "")

                    if not content or len(content.strip()) < 50:
                        continue

                    # Map section to specific source type
                    source_type = _SECTION_SOURCE_MAP.get(
                        section,
                        _SOURCE_TYPE_MAP.get(filing_type, SourceType.SEC_10K_ITEM_7),
                    )

                    # Map source type to signal category
                    signal_cat = self._source_to_signal(source_type)

                    evidence.append(CS2Evidence(
                        evidence_id=chunk.get("id", f"{doc_id}_chunk_{chunk.get('chunk_index', 0)}"),
                        company_id=ticker,
                        source_type=source_type,
                        signal_category=signal_cat,
                        content=content,
                        extracted_at=datetime.fromisoformat(
                            doc.get("created_at", datetime.now().isoformat())
                            .replace("Z", "+00:00")
                        ) if doc.get("created_at") else datetime.now(),
                        confidence=0.85,  # SEC filings are high-confidence
                        fiscal_year=fiscal_year,
                    ))

        except (httpx.HTTPError, httpx.ConnectError) as e:
            logger.warning("cs2_document_fetch_failed", ticker=ticker, error=str(e))

        return evidence

    async def _fetch_signal_evidence(
        self, ticker: str, snowflake_id: str
    ) -> List[CS2Evidence]:
        """
        Fetch external signals as evidence items.

        Uses TWO sources:
          1. Local JSON data files (rich text: reviews, bios, articles, job titles)
          2. Snowflake signals API (thin metadata summaries as fallback)

        The local files contain the real collected data from Glassdoor,
        Board, News, and Job APIs.  These provide the actual text content
        that rubric keywords can match against.
        """
        evidence: List[CS2Evidence] = []

        # ── 1. Rich evidence from local data files ───────────────
        for loader_name, loader_fn in [
            ("glassdoor", self._load_glassdoor_evidence),
            ("board", self._load_board_evidence),
            ("news", self._load_news_evidence),
            ("jobs", self._load_jobs_evidence),
        ]:
            try:
                items = loader_fn(ticker)
                evidence.extend(items)
                if items:
                    logger.info("cs2_local_evidence_loaded", source=loader_name, ticker=ticker, count=len(items))
            except Exception as e:
                logger.warning("cs2_local_evidence_failed", source=loader_name, ticker=ticker, error=str(e))

        # ── 2. Snowflake signal summaries (fallback / extra) ─────
        try:
            response = await self.client.get(
                f"{self.base_url}/api/v1/signals",
                params={"company_id": snowflake_id, "limit": 200},
            )
            response.raise_for_status()
            signals = response.json()

            # Only add signals that aren't already covered by local data
            existing_sources = {e.source_type for e in evidence}
            for sig in signals:
                source = sig.get("source", "")
                source_type = _SOURCE_TYPE_MAP.get(source, SourceType.PRESS_RELEASE)

                # Skip if we already have rich data for this source
                if source_type in existing_sources:
                    continue

                category = sig.get("category", "")
                raw_value = sig.get("raw_value", "")
                metadata = sig.get("metadata", {}) or {}

                content_parts = []
                if raw_value:
                    content_parts.append(raw_value)
                for key, val in metadata.items():
                    if isinstance(val, (str, int, float)) and val:
                        content_parts.append(f"{key}: {val}")

                content = " | ".join(content_parts)
                if not content or len(content.strip()) < 10:
                    continue

                signal_cat = _CATEGORY_MAP.get(category, SignalCategory.LEADERSHIP_SIGNALS)
                confidence = float(sig.get("confidence") or 0.7)

                evidence.append(CS2Evidence(
                    evidence_id=sig.get("id", ""),
                    company_id=ticker,
                    source_type=source_type,
                    signal_category=signal_cat,
                    content=content,
                    extracted_at=datetime.now(),
                    confidence=confidence,
                ))

        except (httpx.HTTPError, httpx.ConnectError) as e:
            logger.warning("cs2_signal_fetch_failed", ticker=ticker, error=str(e))

        logger.info(
            "cs2_signal_evidence_built",
            ticker=ticker,
            total=len(evidence),
        )
        return evidence

    # ── Rich Evidence Loaders (local JSON data files) ────────────

    @staticmethod
    def _load_glassdoor_evidence(ticker: str) -> List[CS2Evidence]:
        """
        Load Glassdoor reviews from data/glassdoor/{ticker}.json.

        Each review becomes an evidence item with real pros/cons text.
        Maps to: culture_signals → Culture dimension.
        """
        import json
        from pathlib import Path

        path = Path(f"data/glassdoor/{ticker}.json")
        if not path.exists():
            return []

        try:
            reviews = json.loads(path.read_text())
        except Exception:
            return []

        evidence = []
        for i, rev in enumerate(reviews[:15]):  # Top 15 reviews
            pros = rev.get("pros", "")
            cons = rev.get("cons", "")
            title = rev.get("title", "")
            job_title = rev.get("job_title", "")
            rating = rev.get("rating", "")
            advice = rev.get("advice_to_management", "") or ""

            content = (
                f"Glassdoor Review ({rating}/5) by {job_title}: {title}. "
                f"Pros: {pros} "
                f"Cons: {cons} "
                f"{('Advice: ' + advice) if advice else ''}"
            ).strip()

            if len(content) < 30:
                continue

            evidence.append(CS2Evidence(
                evidence_id=f"glassdoor_{ticker}_{rev.get('review_id', i)}",
                company_id=ticker,
                source_type=SourceType.GLASSDOOR_REVIEW,
                signal_category=SignalCategory.CULTURE_SIGNALS,
                content=content,
                extracted_at=datetime.now(),
                confidence=0.75,
            ))

        return evidence

    @staticmethod
    def _load_board_evidence(ticker: str) -> List[CS2Evidence]:
        """
        Load board composition from data/board/{ticker}.json.

        Board members with bios become evidence items.
        Maps to: governance_signals → AI Governance dimension.
        """
        import json
        from pathlib import Path

        path = Path(f"data/board/{ticker}.json")
        if not path.exists():
            return []

        try:
            data = json.loads(path.read_text())
        except Exception:
            return []

        evidence = []
        members = data.get("members", [])
        committees = data.get("committees", [])

        # Each board member as evidence
        for i, member in enumerate(members):
            name = member.get("name", "")
            title = member.get("title", "")
            bio = member.get("bio", "")
            comms = ", ".join(member.get("committees", []))
            independent = "Independent" if member.get("is_independent") else "Executive"

            content = (
                f"Board Member: {name}, {title} ({independent}). "
                f"{bio} "
                f"{'Committees: ' + comms if comms else ''}"
            ).strip()

            if len(content) < 30:
                continue

            evidence.append(CS2Evidence(
                evidence_id=f"board_{ticker}_{i}",
                company_id=ticker,
                source_type=SourceType.BOARD_PROXY_DEF14A,
                signal_category=SignalCategory.GOVERNANCE_SIGNALS,
                content=content,
                extracted_at=datetime.now(),
                confidence=0.90,
            ))

        # Committees as a single evidence item
        if committees:
            # Handle both list-of-strings and list-of-dicts formats
            if isinstance(committees[0], str):
                comm_text = "Board Committees: " + ", ".join(committees)
            else:
                comm_text = "Board Committees: " + "; ".join(
                    f"{c.get('name', '')} ({', '.join(c.get('members', []))})" for c in committees
                )
            evidence.append(CS2Evidence(
                evidence_id=f"board_committees_{ticker}",
                company_id=ticker,
                source_type=SourceType.BOARD_PROXY_DEF14A,
                signal_category=SignalCategory.GOVERNANCE_SIGNALS,
                content=comm_text,
                extracted_at=datetime.now(),
                confidence=0.90,
            ))

        # Executives as evidence (if present)
        executives = data.get("executives", [])
        if executives:
            exec_text = "Executive Leadership: " + ", ".join(
                f"{e.get('name', '')} ({e.get('title', '')})" for e in executives
            )
            evidence.append(CS2Evidence(
                evidence_id=f"board_executives_{ticker}",
                company_id=ticker,
                source_type=SourceType.BOARD_PROXY_DEF14A,
                signal_category=SignalCategory.LEADERSHIP_SIGNALS,
                content=exec_text,
                extracted_at=datetime.now(),
                confidence=0.90,
            ))

        # AI strategy as evidence (check both 'strategy' dict and 'strategy_text' string)
        strategy_text = data.get("strategy_text", "")
        strategy_dict = data.get("strategy", {})

        if strategy_text:
            evidence.append(CS2Evidence(
                evidence_id=f"board_strategy_{ticker}",
                company_id=ticker,
                source_type=SourceType.BOARD_PROXY_DEF14A,
                signal_category=SignalCategory.LEADERSHIP_SIGNALS,
                content=f"AI Strategy: {strategy_text}",
                extracted_at=datetime.now(),
                confidence=0.85,
            ))
        elif strategy_dict:
            strat_parts = []
            for key, val in strategy_dict.items():
                if isinstance(val, str) and val:
                    strat_parts.append(f"{key.replace('_', ' ').title()}: {val}")
                elif isinstance(val, list) and val:
                    strat_parts.append(f"{key.replace('_', ' ').title()}: {', '.join(str(v) for v in val)}")
            if strat_parts:
                evidence.append(CS2Evidence(
                    evidence_id=f"board_strategy_{ticker}",
                    company_id=ticker,
                    source_type=SourceType.BOARD_PROXY_DEF14A,
                    signal_category=SignalCategory.LEADERSHIP_SIGNALS,
                    content="AI Strategy: " + ". ".join(strat_parts),
                    extracted_at=datetime.now(),
                    confidence=0.85,
                ))

        return evidence

    @staticmethod
    def _load_news_evidence(ticker: str) -> List[CS2Evidence]:
        """
        Load news articles from data/news/{ticker}.json.

        AI-relevant articles become evidence items.
        Maps to: leadership_signals → Leadership dimension.
        """
        import json
        from pathlib import Path

        path = Path(f"data/news/{ticker}.json")
        if not path.exists():
            return []

        try:
            articles = json.loads(path.read_text())
        except Exception:
            return []

        evidence = []
        for i, article in enumerate(articles[:20]):
            title = article.get("title", "")
            snippet = article.get("snippet", article.get("description", ""))
            source = article.get("source", "")
            ai_related = article.get("is_ai_related", False)
            categories = article.get("categories", [])

            content = (
                f"{'[AI] ' if ai_related else ''}News ({source}): {title}. "
                f"{snippet} "
                f"{'Categories: ' + ', '.join(categories) if categories else ''}"
            ).strip()

            if len(content) < 30:
                continue

            evidence.append(CS2Evidence(
                evidence_id=f"news_{ticker}_{i}",
                company_id=ticker,
                source_type=SourceType.NEWS_ARTICLE,
                signal_category=SignalCategory.LEADERSHIP_SIGNALS,
                content=content,
                extracted_at=datetime.now(),
                confidence=0.80 if ai_related else 0.60,
            ))

        return evidence

    @staticmethod
    def _load_jobs_evidence(ticker: str) -> List[CS2Evidence]:
        """
        Load job postings from results/{ticker}_jobs.json.

        AI job titles become evidence items.
        Maps to: technology_hiring → Talent dimension.
        """
        import json
        from pathlib import Path

        path = Path(f"results/{ticker.lower()}_jobs.json")
        if not path.exists():
            return []

        try:
            jobs = json.loads(path.read_text())
        except Exception:
            return []

        # Build a single evidence item from all AI jobs
        ai_jobs = [j for j in jobs if j.get("is_ai")]
        all_titles = [j.get("title", "") for j in jobs if j.get("title")]
        ai_titles = [j.get("title", "") for j in ai_jobs if j.get("title")]

        evidence = []

        if ai_titles:
            # Combined AI hiring evidence
            content = (
                f"{ticker} AI Hiring: {len(ai_jobs)}/{len(jobs)} job postings are AI-related. "
                f"AI roles include: {', '.join(ai_titles[:10])}. "
                f"Skills sought: {', '.join(set(s for j in ai_jobs for s in j.get('skills', []) if s))}."
            )

            evidence.append(CS2Evidence(
                evidence_id=f"jobs_ai_{ticker}",
                company_id=ticker,
                source_type=SourceType.JOB_POSTING_INDEED,
                signal_category=SignalCategory.TECHNOLOGY_HIRING,
                content=content,
                extracted_at=datetime.now(),
                confidence=0.80,
            ))

        # Also add individual notable AI job postings (top 5)
        for i, job in enumerate(ai_jobs[:5]):
            title = job.get("title", "")
            skills = ", ".join(job.get("skills", []))
            content = (
                f"AI Job Posting at {ticker}: {title}. "
                f"{'Skills: ' + skills if skills else ''}"
            ).strip()

            evidence.append(CS2Evidence(
                evidence_id=f"job_{ticker}_{i}",
                company_id=ticker,
                source_type=SourceType.JOB_POSTING_INDEED,
                signal_category=SignalCategory.TECHNOLOGY_HIRING,
                content=content,
                extracted_at=datetime.now(),
                confidence=0.80,
            ))

        return evidence

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _source_to_signal(source_type: SourceType) -> SignalCategory:
        """Map SourceType to primary SignalCategory (per CS4 PDF Task 8.0a)."""
        mapping = {
            SourceType.SEC_10K_ITEM_1: SignalCategory.DIGITAL_PRESENCE,
            SourceType.SEC_10K_ITEM_1A: SignalCategory.GOVERNANCE_SIGNALS,
            SourceType.SEC_10K_ITEM_7: SignalCategory.LEADERSHIP_SIGNALS,
            SourceType.JOB_POSTING_LINKEDIN: SignalCategory.TECHNOLOGY_HIRING,
            SourceType.JOB_POSTING_INDEED: SignalCategory.TECHNOLOGY_HIRING,
            SourceType.PATENT_USPTO: SignalCategory.INNOVATION_ACTIVITY,
            SourceType.GLASSDOOR_REVIEW: SignalCategory.CULTURE_SIGNALS,
            SourceType.BOARD_PROXY_DEF14A: SignalCategory.GOVERNANCE_SIGNALS,
            SourceType.PRESS_RELEASE: SignalCategory.LEADERSHIP_SIGNALS,
            SourceType.NEWS_ARTICLE: SignalCategory.LEADERSHIP_SIGNALS,
            SourceType.ANALYST_INTERVIEW: SignalCategory.LEADERSHIP_SIGNALS,
            SourceType.DD_DATA_ROOM: SignalCategory.DIGITAL_PRESENCE,
        }
        return mapping.get(source_type, SignalCategory.LEADERSHIP_SIGNALS)
