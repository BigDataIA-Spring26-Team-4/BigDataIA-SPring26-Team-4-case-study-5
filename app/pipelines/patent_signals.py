"""
Patent signal collector for AI innovation.

Case Study 2: Collects and analyzes patent filings to measure
actual R&D commitment to AI (innovation activity signal).

Uses the USPTO PatentsView public API (free, no API key required,
rate-limited to 45 req/min which we respect with delays).
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Union
from uuid import UUID

import httpx

from app.models.signal import ExternalSignal, SignalCategory, SignalSource

logger = logging.getLogger(__name__)


@dataclass
class Patent:
    """A patent record."""

    patent_number: str
    title: str
    abstract: str
    filing_date: datetime
    grant_date: datetime | None
    inventors: list[str]
    assignee: str
    is_ai_related: bool
    ai_categories: list[str]


class PatentSignalCollector:
    """Collect patent signals for AI innovation."""

    AI_PATENT_KEYWORDS = [
        "machine learning",
        "neural network",
        "deep learning",
        "artificial intelligence",
        "natural language processing",
        "computer vision",
        "reinforcement learning",
        "predictive model",
        "classification algorithm",
    ]

    AI_PATENT_CLASSES = [
        "706",  # Data processing: AI
        "382",  # Image analysis
        "704",  # Speech processing
    ]

    # USPTO PatentsView API - free, public, no key required
    USPTO_API_BASE = "https://search.patentsview.org/api/v1/patent/"

    def search_patents(
        self,
        assignee_name: str,
        max_results: int = 50,
        years_back: int = 5,
        api_key: str | None = None,
    ) -> list[Patent]:
        """
        Search USPTO PatentSearch API for company patents.

        Uses GET with query params (the documented primary method).
        Requires a free API key from patentsview.org.
        Falls back to empty list if no key or API unavailable.
        """
        if not api_key:
            try:
                from app.config import settings
                api_key = settings.PATENTSVIEW_API_KEY
            except Exception:
                pass

        if not api_key:
            logger.warning(
                "No PATENTSVIEW_API_KEY set. Skipping patent search. "
                "Request a free key at https://patentsview-support.atlassian.net"
            )
            return []

        try:
            import json as _json

            cutoff_date = (
                datetime.now(timezone.utc) - timedelta(days=years_back * 365)
            ).strftime("%Y-%m-%d")

            # Build query using POST with JSON body
            # Uses _text_phrase for text-type fields per API docs
            body = {
                "q": {
                    "_and": [
                        {"_text_phrase": {"assignees.assignee_organization": assignee_name}},
                        {"_gte": {"patent_date": cutoff_date}},
                    ]
                },
                "f": ["patent_id", "patent_title", "patent_date"],
                "o": {"size": min(max_results, 100)},
                "s": [{"patent_date": "desc"}],
            }

            logger.info(
                f"Searching PatentSearch API for '{assignee_name}' patents since {cutoff_date}..."
            )
            logger.debug(f"Request body: {_json.dumps(body)}")

            client = httpx.Client(timeout=30.0)
            resp = client.post(
                self.USPTO_API_BASE,
                json=body,
                headers={
                    "X-Api-Key": api_key,
                    "Content-Type": "application/json",
                    "User-Agent": "PE-OrgAIR-Research/1.0 (academic research)",
                },
            )

            time.sleep(2)

            if resp.status_code != 200:
                logger.warning(
                    f"PatentSearch API returned {resp.status_code}: {resp.text[:500]}"
                )
                # If 400, log the full request body for debugging
                if resp.status_code == 400:
                    logger.warning(f"Request body was: {_json.dumps(body)}")
                return []

            data = resp.json()
            patents_data = data.get("patents", [])

            if not patents_data:
                logger.info(f"No patents found for {assignee_name}")
                return []

            patents = []
            for p in patents_data:
                try:
                    patent = Patent(
                        patent_number=p.get("patent_id", ""),
                        title=p.get("patent_title", ""),
                        abstract="",
                        filing_date=datetime.strptime(
                            p.get("patent_date", "2020-01-01"), "%Y-%m-%d"
                        ).replace(tzinfo=timezone.utc),
                        grant_date=None,
                        inventors=[],
                        assignee=assignee_name,
                        is_ai_related=False,
                        ai_categories=[],
                    )
                    patent = self.classify_patent(patent)
                    patents.append(patent)
                except Exception as e:
                    logger.debug(f"Skipping malformed patent record: {e}")

            ai_count = sum(1 for p in patents if p.is_ai_related)
            logger.info(
                f"Found {len(patents)} patents for {assignee_name}, "
                f"{ai_count} AI-related"
            )
            return patents

        except httpx.ConnectError:
            logger.warning("Cannot reach PatentSearch API (network issue). Returning empty.")
            return []
        except Exception as e:
            logger.error(f"Patent search failed for {assignee_name}: {e}")
            return []


    def analyze_patents(
        self, company_id: Union[UUID, str], patents: list[Patent], years: int = 5
    ) -> ExternalSignal:
        """Analyze patent portfolio for AI innovation."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=years * 365)
        recent_patents = [p for p in patents if p.filing_date > cutoff]
        ai_patents = [p for p in recent_patents if p.is_ai_related]

        # Scoring:
        # - AI patent count: 5 points each (max 50)
        # - Recency bonus: +2 per patent filed in last year (max 20)
        # - Category diversity: 10 points per category (max 30)

        last_year = datetime.now(timezone.utc) - timedelta(days=365)
        recent_ai = [p for p in ai_patents if p.filing_date > last_year]

        categories = set()
        for p in ai_patents:
            categories.update(p.ai_categories)

        score = (
            min(len(ai_patents) * 5, 50)
            + min(len(recent_ai) * 2, 20)
            + min(len(categories) * 10, 30)
        )

        return ExternalSignal(
            company_id=company_id,
            category=SignalCategory.INNOVATION_ACTIVITY,
            source=SignalSource.USPTO,
            signal_date=datetime.now(timezone.utc),
            raw_value=f"{len(ai_patents)} AI patents in {years} years",
            normalized_score=round(score, 1),
            confidence=0.90,
            metadata={
                "total_patents": len(patents),
                "ai_patents": len(ai_patents),
                "recent_ai_patents": len(recent_ai),
                "ai_categories": list(categories),
            },
        )

    def classify_patent(self, patent: Patent) -> Patent:
        """Classify a patent as AI-related."""
        text = f"{patent.title} {patent.abstract}".lower()

        is_ai = any(kw in text for kw in self.AI_PATENT_KEYWORDS)

        categories = []
        if "neural network" in text or "deep learning" in text:
            categories.append("deep_learning")
        if "natural language" in text:
            categories.append("nlp")
        if "computer vision" in text or "image" in text:
            categories.append("computer_vision")
        if "predictive" in text:
            categories.append("predictive_analytics")

        patent.is_ai_related = is_ai or len(categories) > 0
        patent.ai_categories = categories

        return patent
