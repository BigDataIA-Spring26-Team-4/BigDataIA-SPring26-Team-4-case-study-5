"""
Glassdoor culture signal collector.

CS3 Task 5.0c: Fetches employee reviews using multiple providers
in priority order:
  1. Wextractor API (cleanest, free credits on signup)
  2. RapidAPI Real-Time Glassdoor Data (free tier ~500 req/month)
  3. Cached JSON fallback (data/glassdoor/{ticker}.json)

Analyzes reviews for culture signals: innovation, data-driven
mindset, AI awareness, and change readiness.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)

# Glassdoor employer IDs used by both APIs
GLASSDOOR_EMPLOYER_IDS = {
    "NVDA": "7633",
    "JPM": "145",
    "WMT": "715",
    "GE": "277",
    "DG": "34408",
    # CS2 companies kept for compatibility
    "CAT": "99",
    "DE": "670",
    "UNH": "1831",
    "HCA": "3071",
    "ADP": "6168",
    "PAYX": "4078",
    "TGT": "194",
    "GS": "2800",
}


@dataclass
class GlassdoorReview:
    review_id: str
    rating: float
    title: str
    pros: str
    cons: str
    advice_to_management: Optional[str]
    is_current_employee: bool
    job_title: str
    review_date: datetime


@dataclass
class CultureSignal:
    company_id: str
    ticker: str
    innovation_score: Decimal
    data_driven_score: Decimal
    change_readiness_score: Decimal
    ai_awareness_score: Decimal
    overall_score: Decimal
    review_count: int
    avg_rating: Decimal
    current_employee_ratio: Decimal
    confidence: Decimal
    positive_keywords_found: List[str] = field(default_factory=list)
    negative_keywords_found: List[str] = field(default_factory=list)


class GlassdoorCultureCollector:
    """
    Collect and analyze Glassdoor reviews for culture signals.

    Overall = 0.30 * innovation + 0.25 * data_driven
             + 0.25 * ai_awareness + 0.20 * change_readiness
    """

    INNOVATION_POSITIVE = [
        "innovative", "cutting-edge", "forward-thinking",
        "encourages new ideas", "experimental", "creative freedom",
        "startup mentality", "move fast", "disruptive",
    ]
    INNOVATION_NEGATIVE = [
        "bureaucratic", "slow to change", "resistant",
        "outdated", "stuck in old ways", "red tape",
        "politics", "siloed", "hierarchical",
    ]
    DATA_DRIVEN_KEYWORDS = [
        "data-driven", "metrics", "evidence-based",
        "analytical", "kpis", "dashboards", "data culture",
        "measurement", "quantitative",
    ]
    AI_AWARENESS_KEYWORDS = [
        "ai", "artificial intelligence", "machine learning",
        "automation", "data science", "ml", "algorithms",
        "predictive", "neural network",
    ]
    CHANGE_POSITIVE = [
        "agile", "adaptive", "fast-paced", "embraces change",
        "continuous improvement", "growth mindset",
    ]
    CHANGE_NEGATIVE = [
        "rigid", "traditional", "slow", "risk-averse",
        "change resistant", "old school",
    ]

    def __init__(
        self,
        wextractor_token: Optional[str] = None,
        rapidapi_key: Optional[str] = None,
        data_dir: str = "data/glassdoor",
    ):
        self.wextractor_token = wextractor_token
        self.rapidapi_key = rapidapi_key
        self.data_dir = Path(data_dir)

        if not self.wextractor_token or not self.rapidapi_key:
            try:
                from app.config import settings
                self.wextractor_token = self.wextractor_token or getattr(settings, "WEXTRACTOR_TOKEN", None)
                self.rapidapi_key = self.rapidapi_key or getattr(settings, "RAPIDAPI_KEY", None)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Fetching — priority: Wextractor → RapidAPI → cached JSON
    # ------------------------------------------------------------------

    def fetch_reviews(self, ticker: str, limit: int = 50) -> List[GlassdoorReview]:
        reviews = self._fetch_wextractor(ticker, limit)
        if reviews:
            self._cache_reviews(ticker, reviews)
            return reviews

        reviews = self._fetch_rapidapi(ticker, limit)
        if reviews:
            self._cache_reviews(ticker, reviews)
            return reviews

        logger.info(f"Using cached data for {ticker}")
        return self._load_cached(ticker)

    # --- Wextractor (preferred) -------------------------------------------

    def _fetch_wextractor(self, ticker: str, limit: int) -> List[GlassdoorReview]:
        if not self.wextractor_token or self.wextractor_token.startswith("your_"):
            return []

        employer_id = GLASSDOOR_EMPLOYER_IDS.get(ticker)
        if not employer_id:
            logger.warning(f"No Glassdoor employer ID for {ticker}")
            return []

        try:
            client = httpx.Client(timeout=15.0)
            all_reviews: List[GlassdoorReview] = []
            offset = 0

            while len(all_reviews) < limit:
                resp = client.get(
                    "https://wextractor.com/api/v1/reviews/glassdoor",
                    params={
                        "id": employer_id,
                        "auth_token": self.wextractor_token,
                        "language": "en",
                        "offset": str(offset),
                    },
                )
                if resp.status_code != 200:
                    logger.warning(f"Wextractor returned {resp.status_code} for {ticker}")
                    break

                data = resp.json()
                reviews_list = data.get("reviews", [])
                if not reviews_list:
                    break

                for r in reviews_list:
                    try:
                        all_reviews.append(GlassdoorReview(
                            review_id=str(r.get("id", "")),
                            rating=float(r.get("rating", 3.0)),
                            title=r.get("title", ""),
                            pros=r.get("pros", ""),
                            cons=r.get("cons", ""),
                            advice_to_management=r.get("advice"),
                            is_current_employee=bool(r.get("is_current_job", False)),
                            job_title=r.get("reviewer", ""),
                            review_date=self._parse_date(r.get("datetime", "")),
                        ))
                    except Exception as e:
                        logger.debug(f"Skipping review: {e}")

                offset += 10  # Wextractor returns 10 per page
                if len(reviews_list) < 10:
                    break

            logger.info(f"Wextractor: fetched {len(all_reviews)} reviews for {ticker}")
            return all_reviews

        except Exception as e:
            logger.error(f"Wextractor error for {ticker}: {e}")
            return []

    # --- RapidAPI (secondary) ---------------------------------------------

    RAPIDAPI_HOST = "real-time-glassdoor-data.p.rapidapi.com"

    def _fetch_rapidapi(self, ticker: str, limit: int) -> List[GlassdoorReview]:
        if not self.rapidapi_key or self.rapidapi_key.startswith("your_"):
            return []

        employer_id = GLASSDOOR_EMPLOYER_IDS.get(ticker)
        if not employer_id:
            return []

        try:
            client = httpx.Client(timeout=15.0)
            all_reviews: List[GlassdoorReview] = []
            page = 1
            max_pages = max(1, limit // 10)

            while len(all_reviews) < limit and page <= max_pages:
                resp = client.get(
                    f"https://{self.RAPIDAPI_HOST}/company-reviews",
                    params={"employer_id": employer_id, "page": str(page)},
                    headers={
                        "x-rapidapi-host": self.RAPIDAPI_HOST,
                        "x-rapidapi-key": self.rapidapi_key,
                    },
                )
                if resp.status_code != 200:
                    break

                data = resp.json()
                reviews_data = data.get("reviews", data.get("data", []))
                if not reviews_data:
                    break

                for r in reviews_data:
                    try:
                        all_reviews.append(GlassdoorReview(
                            review_id=str(r.get("review_id", r.get("id", ""))),
                            rating=float(r.get("rating", r.get("overall_rating", 3.0))),
                            title=r.get("review_title", r.get("title", "")),
                            pros=r.get("pros", ""),
                            cons=r.get("cons", ""),
                            advice_to_management=r.get("advice_to_management"),
                            is_current_employee="current" in str(
                                r.get("employee_status", r.get("is_current", ""))
                            ).lower(),
                            job_title=r.get("job_title", r.get("author_job_title", "")),
                            review_date=self._parse_date(
                                r.get("review_date", r.get("date", ""))
                            ),
                        ))
                    except Exception as e:
                        logger.debug(f"Skipping review: {e}")

                page += 1

            logger.info(f"RapidAPI: fetched {len(all_reviews)} reviews for {ticker}")
            return all_reviews

        except Exception as e:
            logger.error(f"RapidAPI error for {ticker}: {e}")
            return []

    # --- Helpers -----------------------------------------------------------

    def _parse_date(self, raw: str) -> datetime:
        if not raw:
            return datetime.now(timezone.utc)
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%b %d, %Y"):
            try:
                return datetime.strptime(raw[:26], fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return datetime.now(timezone.utc)

    def _cache_reviews(self, ticker: str, reviews: List[GlassdoorReview]):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        path = self.data_dir / f"{ticker}.json"
        payload = [
            {
                "review_id": r.review_id,
                "rating": r.rating,
                "title": r.title,
                "pros": r.pros,
                "cons": r.cons,
                "advice_to_management": r.advice_to_management,
                "is_current_employee": r.is_current_employee,
                "job_title": r.job_title,
                "review_date": r.review_date.strftime("%Y-%m-%d"),
            }
            for r in reviews
        ]
        path.write_text(json.dumps(payload, indent=2))
        logger.info(f"Cached {len(reviews)} reviews to {path}")

    def _load_cached(self, ticker: str) -> List[GlassdoorReview]:
        path = self.data_dir / f"{ticker}.json"
        if not path.exists():
            logger.warning(f"No cached reviews for {ticker}")
            return []

        raw = json.loads(path.read_text())
        reviews = []
        for r in raw:
            reviews.append(GlassdoorReview(
                review_id=r["review_id"],
                rating=float(r["rating"]),
                title=r["title"],
                pros=r["pros"],
                cons=r["cons"],
                advice_to_management=r.get("advice_to_management"),
                is_current_employee=r.get("is_current_employee", False),
                job_title=r.get("job_title", ""),
                review_date=self._parse_date(r["review_date"]),
            ))
        logger.info(f"Loaded {len(reviews)} cached reviews for {ticker}")
        return reviews

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def analyze_reviews(
        self, company_id: str, ticker: str, reviews: List[GlassdoorReview]
    ) -> CultureSignal:
        if not reviews:
            return self._empty_signal(company_id, ticker)

        innov_pos = 0.0
        innov_neg = 0.0
        data_mentions = 0.0
        ai_mentions = 0.0
        change_pos = 0.0
        change_neg = 0.0
        total_weight = 0.0
        rating_sum = 0.0
        current_count = 0
        pos_kw_found: set = set()
        neg_kw_found: set = set()

        now = datetime.now(timezone.utc)
        for review in reviews:
            text = f"{review.pros} {review.cons}".lower()
            if review.advice_to_management:
                text += f" {review.advice_to_management.lower()}"

            days_old = (now - review.review_date).days
            recency_weight = 1.0 if days_old < 730 else 0.5
            employee_weight = 1.2 if review.is_current_employee else 1.0
            w = recency_weight * employee_weight
            total_weight += w
            rating_sum += review.rating

            if review.is_current_employee:
                current_count += 1

            for kw in self.INNOVATION_POSITIVE:
                if kw in text:
                    innov_pos += w
                    pos_kw_found.add(kw)
            for kw in self.INNOVATION_NEGATIVE:
                if kw in text:
                    innov_neg += w
                    neg_kw_found.add(kw)
            for kw in self.DATA_DRIVEN_KEYWORDS:
                if kw in text:
                    data_mentions += w
                    pos_kw_found.add(kw)
            for kw in self.AI_AWARENESS_KEYWORDS:
                if kw in text:
                    ai_mentions += w
                    pos_kw_found.add(kw)
            for kw in self.CHANGE_POSITIVE:
                if kw in text:
                    change_pos += w
                    pos_kw_found.add(kw)
            for kw in self.CHANGE_NEGATIVE:
                if kw in text:
                    change_neg += w
                    neg_kw_found.add(kw)

        n = len(reviews)
        tw = max(total_weight, 1.0)

        innovation = max(0, min(100, (innov_pos - innov_neg) / tw * 50 + 50))
        data_driven = max(0, min(100, data_mentions / tw * 100))
        ai_awareness = max(0, min(100, ai_mentions / tw * 100))
        change_readiness = max(0, min(100, (change_pos - change_neg) / tw * 50 + 50))

        overall = (
            0.30 * innovation
            + 0.25 * data_driven
            + 0.25 * ai_awareness
            + 0.20 * change_readiness
        )

        confidence = min(0.5 + n / 50, 0.95)

        return CultureSignal(
            company_id=company_id,
            ticker=ticker,
            innovation_score=Decimal(str(round(innovation, 2))),
            data_driven_score=Decimal(str(round(data_driven, 2))),
            change_readiness_score=Decimal(str(round(change_readiness, 2))),
            ai_awareness_score=Decimal(str(round(ai_awareness, 2))),
            overall_score=Decimal(str(round(overall, 2))),
            review_count=n,
            avg_rating=Decimal(str(round(rating_sum / n, 2))),
            current_employee_ratio=Decimal(str(round(current_count / n, 2))),
            confidence=Decimal(str(round(confidence, 2))),
            positive_keywords_found=sorted(pos_kw_found),
            negative_keywords_found=sorted(neg_kw_found),
        )

    def _empty_signal(self, company_id: str, ticker: str) -> CultureSignal:
        return CultureSignal(
            company_id=company_id,
            ticker=ticker,
            innovation_score=Decimal("50"),
            data_driven_score=Decimal("50"),
            change_readiness_score=Decimal("50"),
            ai_awareness_score=Decimal("50"),
            overall_score=Decimal("50"),
            review_count=0,
            avg_rating=Decimal("0"),
            current_employee_ratio=Decimal("0"),
            confidence=Decimal("0.3"),
        )
