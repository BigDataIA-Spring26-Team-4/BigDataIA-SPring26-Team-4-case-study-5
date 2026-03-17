"""
Board composition analyzer for AI governance signals.

CS3 Task 5.0d: Fetches directors & board members from sec-api.io,
or parses DEF-14A proxy filings from CS2, and scores governance
indicators related to AI oversight.

Falls back to locally cached JSON when APIs are unavailable.
"""

import json
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Tuple

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# CIK identifiers for the 5 CS3 target companies
COMPANY_TICKERS_CIK = {
    "NVDA": "1045810",
    "JPM": "19617",
    "WMT": "104169",
    "GE": "40554",
    "DG": "34408",
}


@dataclass
class BoardMember:
    name: str
    title: str
    committees: List[str]
    bio: str
    is_independent: bool
    tenure_years: int


@dataclass
class GovernanceSignal:
    company_id: str
    ticker: str
    has_tech_committee: bool
    has_ai_expertise: bool
    has_data_officer: bool
    has_risk_tech_oversight: bool
    has_ai_in_strategy: bool
    tech_expertise_count: int
    independent_ratio: Decimal
    governance_score: Decimal
    confidence: Decimal
    ai_experts: List[str] = field(default_factory=list)
    relevant_committees: List[str] = field(default_factory=list)


class BoardCompositionAnalyzer:
    """
    Analyze board composition for AI governance indicators.

    Scoring (additive, capped at 100):
      Base:                          20 pts
      Tech/digital committee exists: +15 pts
      AI expertise on board:         +20 pts
      CAIO/CDO/CTO role:            +15 pts
      Independent ratio > 0.5:       +10 pts
      Risk committee tech oversight: +10 pts
      AI in strategic priorities:    +10 pts
    """

    SEC_API_URL = "https://api.sec-api.io/directors-and-board-members"

    AI_EXPERTISE_KEYWORDS = [
        "artificial intelligence", "machine learning",
        "chief data officer", "chief ai officer",
        "chief technology officer", "chief digital officer",
        "data science", "data analytics", "digital transformation",
        "deep learning", "neural network",
        "gpu computing", "ai acceleration", "ai computing",
        "ai strategy", "ai research", "ai infrastructure",
        "generative ai", "large language model",
    ]

    # Short abbreviations that must be matched as whole words
    # to avoid false positives (e.g. "cdo" inside "mcdonald's").
    AI_ABBREV_KEYWORDS = ["cdo", "cto", "caio", "cao"]

    # Titles that inherently indicate AI expertise (for companies
    # whose core business is AI/tech).  Founders/CEOs of GPU/AI
    # companies like NVIDIA should be recognized as AI experts
    # even when sec-api.io bio data is sparse.
    AI_LEADERSHIP_TITLES = [
        "chief ai officer",
        "chief data officer",
        "chief technology officer",
        "chief digital officer",
        "chief analytics officer",
        "vp ai", "vp artificial intelligence",
        "vp machine learning", "vp data science",
        "head of ai", "head of machine learning",
        "svp technology", "evp technology",
    ]
    TECH_COMMITTEE_NAMES = [
        "technology committee", "digital committee",
        "innovation committee", "it committee",
        "technology and cybersecurity", "technology and ecommerce",
    ]
    DATA_OFFICER_TITLES = [
        "chief data officer",
        "chief ai officer",
        "chief analytics officer",
        "chief digital officer",
        "chief technology officer",
    ]

    def __init__(self, sec_api_key: Optional[str] = None, data_dir: str = "data/board"):
        self.sec_api_key = sec_api_key
        self.data_dir = Path(data_dir)
        if not self.sec_api_key:
            try:
                from app.config import settings
                self.sec_api_key = settings.SEC_API_KEY
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------

    def fetch_board_data(
        self, ticker: str
    ) -> Tuple[List[BoardMember], List[str], str]:
        """
        Returns (members, committees, strategy_text).
        Tries sec-api.io first, then enriches with cached data
        (which has hand-curated bios and strategy text).
        Falls back to cached JSON if sec-api.io is unavailable.
        """
        members, committees = self._fetch_from_sec_api(ticker)
        if members:
            # sec-api.io often has sparse bios (just qualifications).
            # Merge in richer bios and strategy text from our cached
            # data which has been curated with AI-relevant details.
            cached_members, cached_committees, strategy = self._load_cached(ticker)
            if cached_members:
                cached_bios = {m.name: m.bio for m in cached_members if m.bio}
                api_names = {m.name for m in members}
                for m in members:
                    if m.name in cached_bios and len(cached_bios[m.name]) > len(m.bio):
                        m.bio = cached_bios[m.name]
                # Add cached members (e.g. executives) not in sec-api.io
                for cm in cached_members:
                    if cm.name not in api_names:
                        members.append(cm)
                        api_names.add(cm.name)
                # Merge any cached committees not in sec-api.io response
                comm_set = set(c.lower() for c in committees)
                for cc in cached_committees:
                    if cc.lower() not in comm_set:
                        committees.append(cc)
            else:
                strategy = ""
            return members, committees, strategy

        return self._load_cached(ticker)

    def _fetch_from_sec_api(
        self, ticker: str
    ) -> Tuple[List[BoardMember], List[str]]:
        if not self.sec_api_key or self.sec_api_key.startswith("your_"):
            logger.warning("No valid SEC_API_KEY configured, skipping API fetch")
            return [], []

        try:
            resp = httpx.post(
                self.SEC_API_URL,
                json={
                    "query": f"ticker:{ticker}",
                    "from": 0,
                    "size": 50,
                    "sort": [{"filedAt": {"order": "desc"}}],
                },
                headers={
                    "Authorization": self.sec_api_key,
                    "Content-Type": "application/json",
                },
                timeout=15.0,
            )
            if resp.status_code != 200:
                logger.warning(f"sec-api.io returned {resp.status_code} for {ticker}")
                return [], []

            data = resp.json()
            records = data.get("data", [])
            if not records:
                return [], []

            latest = records[0]
            directors_raw = latest.get("directors", [])
            all_committees: set = set()
            members: List[BoardMember] = []

            for d in directors_raw:
                comms = d.get("committeeMemberships", [])
                all_committees.update(comms)
                quals = d.get("qualificationsAndExperience", [])
                bio_text = ". ".join(quals) if quals else ""

                members.append(
                    BoardMember(
                        name=d.get("name", ""),
                        title=d.get("position", ""),
                        committees=comms,
                        bio=bio_text,
                        is_independent=d.get("isIndependent", False) or False,
                        tenure_years=0,
                    )
                )

            logger.info(f"Fetched {len(members)} board members from sec-api.io for {ticker}")
            return members, sorted(all_committees)

        except Exception as e:
            logger.error(f"sec-api.io error for {ticker}: {e}")
            return [], []

    def _load_cached(
        self, ticker: str
    ) -> Tuple[List[BoardMember], List[str], str]:
        path = self.data_dir / f"{ticker}.json"
        if not path.exists():
            logger.warning(f"No cached board data for {ticker}")
            return [], [], ""

        raw = json.loads(path.read_text())
        members = []
        for m in raw.get("members", []):
            members.append(
                BoardMember(
                    name=m["name"],
                    title=m["title"],
                    committees=m.get("committees", []),
                    bio=m.get("bio", ""),
                    is_independent=m.get("is_independent", False),
                    tenure_years=m.get("tenure_years", 0),
                )
            )

        committees = raw.get("committees", [])
        strategy = raw.get("strategy_text", "")
        # also fold in executive titles
        for ex in raw.get("executives", []):
            members.append(
                BoardMember(
                    name=ex["name"],
                    title=ex["title"],
                    committees=[],
                    bio="",
                    is_independent=False,
                    tenure_years=0,
                )
            )

        logger.info(f"Loaded cached board data for {ticker}: {len(members)} members")
        return members, committees, strategy

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def analyze_board(
        self,
        company_id: str,
        ticker: str,
        members: List[BoardMember],
        committees: List[str],
        strategy_text: str = "",
    ) -> GovernanceSignal:
        if not members:
            return self._empty_signal(company_id, ticker)

        score = Decimal("20")  # base

        # Tech committee
        has_tech = any(
            any(tc in c.lower() for tc in self.TECH_COMMITTEE_NAMES)
            for c in committees
        )
        if has_tech:
            score += Decimal("15")

        # AI expertise on board — check bios, titles, AND leadership roles
        import re
        ai_experts = []
        for m in members:
            bio_lower = m.bio.lower()
            title_lower = m.title.lower()
            combined = f"{bio_lower} {title_lower}"
            # Check bio + title against expertise keywords
            # Use word-boundary matching for short abbreviations
            # to avoid false positives (e.g. "cdo" in "McDonald's")
            has_expertise = any(kw in combined for kw in self.AI_EXPERTISE_KEYWORDS)
            if not has_expertise:
                has_expertise = any(
                    re.search(rf'\b{kw}\b', combined)
                    for kw in self.AI_ABBREV_KEYWORDS
                )
            if has_expertise:
                if m.name not in ai_experts:
                    ai_experts.append(m.name)
            # Check if title itself indicates AI leadership
            elif any(t in title_lower for t in self.AI_LEADERSHIP_TITLES):
                if m.name not in ai_experts:
                    ai_experts.append(m.name)
            # CEO/Founder of AI-focused companies should count —
            # check if strategy text mentions AI and person is CEO/Founder
            elif strategy_text and ("ceo" in title_lower or "founder" in title_lower):
                st_lower = strategy_text.lower()
                if any(kw in st_lower for kw in ["artificial intelligence", "ai", "machine learning"]):
                    if m.name not in ai_experts:
                        ai_experts.append(m.name)
        if ai_experts:
            score += Decimal("20")

        # Data / AI officer
        has_data_officer = False
        for m in members:
            title_lower = m.title.lower()
            if any(t in title_lower for t in self.DATA_OFFICER_TITLES):
                has_data_officer = True
                break
        if has_data_officer:
            score += Decimal("15")

        # Independent ratio
        total = len(members)
        ind_count = sum(1 for m in members if m.is_independent)
        ind_ratio = ind_count / total if total > 0 else 0
        if ind_ratio > 0.5:
            score += Decimal("10")

        # Risk committee with tech oversight
        has_risk_tech = any(
            "risk" in c.lower() and ("tech" in c.lower() or "cyber" in c.lower())
            for c in committees
        )
        # Also check if any risk committee member has tech background
        if not has_risk_tech:
            for m in members:
                if any("risk" in c.lower() for c in m.committees):
                    if any(kw in m.bio.lower() for kw in ["technology", "cyber", "digital"]):
                        has_risk_tech = True
                        break
        if has_risk_tech:
            score += Decimal("10")

        # AI in strategic priorities
        has_ai_strategy = False
        if strategy_text:
            st_lower = strategy_text.lower()
            has_ai_strategy = any(
                kw in st_lower
                for kw in ["artificial intelligence", "ai", "machine learning", "ai strategy"]
            )
        if has_ai_strategy:
            score += Decimal("10")

        score = min(score, Decimal("100"))

        relevant_comms = [
            c for c in committees
            if any(kw in c.lower() for kw in ["tech", "digital", "innovation", "risk", "cyber"])
        ]

        confidence = min(Decimal("0.5") + Decimal(str(len(members))) / Decimal("20"), Decimal("0.95"))

        return GovernanceSignal(
            company_id=company_id,
            ticker=ticker,
            has_tech_committee=has_tech,
            has_ai_expertise=bool(ai_experts),
            has_data_officer=has_data_officer,
            has_risk_tech_oversight=has_risk_tech,
            has_ai_in_strategy=has_ai_strategy,
            tech_expertise_count=len(ai_experts),
            independent_ratio=Decimal(str(round(ind_ratio, 2))),
            governance_score=score,
            confidence=confidence,
            ai_experts=ai_experts,
            relevant_committees=relevant_comms,
        )

    def extract_from_proxy(self, proxy_html: str) -> Tuple[List[BoardMember], List[str]]:
        """
        Parse DEF-14A proxy statement HTML for board members and committees.
        This is a best-effort extraction — proxy formats vary widely.
        """
        soup = BeautifulSoup(proxy_html, "html.parser")
        text = soup.get_text(separator="\n")
        members = []
        committees = set()

        # Look for common committee names
        for kw in ["audit committee", "compensation committee", "governance committee",
                    "technology committee", "risk committee", "nominating committee"]:
            if kw in text.lower():
                committees.add(kw.title())

        logger.info(f"Extracted {len(committees)} committees from proxy HTML")
        return members, sorted(committees)

    def _empty_signal(self, company_id: str, ticker: str) -> GovernanceSignal:
        return GovernanceSignal(
            company_id=company_id,
            ticker=ticker,
            has_tech_committee=False,
            has_ai_expertise=False,
            has_data_officer=False,
            has_risk_tech_oversight=False,
            has_ai_in_strategy=False,
            tech_expertise_count=0,
            independent_ratio=Decimal("0"),
            governance_score=Decimal("20"),
            confidence=Decimal("0.3"),
        )
