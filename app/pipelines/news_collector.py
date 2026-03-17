"""
News & Press Release collector for AI leadership signals.

CS3 Extension: Scrapes company newsroom pages and uses free GNews API
to find AI-related announcements. These are strong signals for:
  - Leadership commitment (CEO/CTO announcing AI initiatives)
  - Use case portfolio (real AI deployments announced publicly)
  - Culture (innovation announcements reflect internal culture)

Unlike Glassdoor (employee opinions) or SEC filings (legal prose),
press releases represent deliberate public positioning on AI.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)


# Company newsroom URLs (investor relations / press release pages)
NEWSROOM_URLS = {
    "NVDA": [
        "https://nvidianews.nvidia.com/news",
    ],
    "JPM": [
        "https://www.jpmorganchase.com/newsroom",
    ],
    "WMT": [
        "https://corporate.walmart.com/newsroom",
    ],
    "GE": [
        "https://www.gevernova.com/news",
        "https://www.geaerospace.com/news",
    ],
    "DG": [
        "https://newscenter.dollargeneral.com/",
    ],
}

# Search queries for GNews API.
# Short queries work better on the free tier (returns more articles).
GNEWS_SEARCH_TEMPLATES = [
    "{company} AI",
    "{company} artificial intelligence",
    "{company} technology",
    "{company} machine learning",
    "{company} AI strategy",
]

COMPANY_NAMES = {
    "NVDA": "NVIDIA",
    "JPM": "JPMorgan Chase",
    "WMT": "Walmart",
    "GE": "GE Aerospace",  # Post-split name
    "DG": "Dollar General",
}


@dataclass
class NewsArticle:
    """A single news article or press release."""
    title: str
    source: str
    url: str
    published_date: Optional[datetime]
    snippet: str
    is_ai_related: bool
    ai_score: float  # 0-100 relevance score
    categories: List[str] = field(default_factory=list)


@dataclass
class NewsSignal:
    """Aggregated news signal for a company."""
    company_id: str
    ticker: str
    overall_score: Decimal
    leadership_score: Decimal      # CEO/CTO AI announcements
    deployment_score: Decimal       # Real AI use case announcements
    investment_score: Decimal       # Technology investment news
    article_count: int
    ai_article_count: int
    confidence: Decimal
    top_articles: List[dict] = field(default_factory=list)


# ── AI relevance keywords (scored by strength) ──────────────────

STRONG_AI_KEYWORDS = [
    "artificial intelligence", "machine learning", "deep learning",
    "generative ai", "large language model", "neural network",
    "ai strategy", "ai-powered", "ai-driven", "ai platform",
    "chatgpt", "copilot", "ai assistant", "ai investment",
    # Industry-specific AI terms that appear in headlines
    "ai chip", "ai gpu", "ai data center", "ai server",
    "ai infrastructure", "ai spending", "ai revenue",
]

MODERATE_AI_KEYWORDS = [
    "automation", "data science", "predictive analytics",
    "natural language processing", "computer vision",
    "fraud detection", "algorithmic", "digital transformation",
    "cloud ai", "mlops", "ai model", "ai research",
    # Broader tech terms that signal AI context in headlines
    "gpu", "data center", "cloud computing", "semiconductor",
    "technology investment", "tech spending", "digital",
]

LEADERSHIP_KEYWORDS = [
    "ceo", "cto", "cio", "chief", "announces", "strategy",
    "investment", "billion", "million", "commitment",
    "partnership", "acquisition", "launch", "unveil",
]

DEPLOYMENT_KEYWORDS = [
    "deploy", "production", "launch", "roll out", "implement",
    "customer", "revenue", "savings", "efficiency", "pilot",
    "use case", "solution", "platform", "product",
]


class NewsCollector:
    """
    Collect and analyze news/press releases for AI leadership signals.

    Scoring:
        - Each article scored 0-100 for AI relevance
        - Articles with CEO/CTO mentions get leadership bonus
        - Articles about real deployments get deployment bonus
        - Overall = 0.40*leadership + 0.35*deployment + 0.25*investment

    API budget: max 2 GNews queries per company (10 total for 5 companies).
    Free tier allows 100 requests/day — this uses at most 10.
    """

    def __init__(self, gnews_api_key: Optional[str] = None, data_dir: str = "data/news"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.gnews_api_key = gnews_api_key
        self.client = httpx.Client(
            timeout=15.0,
            headers={"User-Agent": "Mozilla/5.0 (compatible; research-bot)"},
            follow_redirects=True,
        )

        # Load API key from settings if not provided directly
        if not self.gnews_api_key:
            try:
                from app.config import settings
                self.gnews_api_key = getattr(settings, "GNEWS_API_KEY", None)
            except Exception:
                pass

        if not self.gnews_api_key:
            logger.warning("No GNEWS_API_KEY configured — GNews API will be skipped. "
                           "Set GNEWS_API_KEY in .env (free at https://gnews.io)")

    def collect_news(self, ticker: str, limit: int = 30) -> List[NewsArticle]:
        """Collect news from multiple sources, cache results."""
        articles = []

        # Source 1: GNews API (free, no key needed)
        articles.extend(self._fetch_gnews(ticker, limit))

        # Source 2: Scrape newsroom page for headlines
        articles.extend(self._scrape_newsroom(ticker))

        # Deduplicate by title similarity
        articles = self._deduplicate(articles)

        # Score each article
        for article in articles:
            self._score_article(article)

        # Cache
        self._cache_articles(ticker, articles)

        logger.info(f"Collected {len(articles)} articles for {ticker}, "
                     f"{sum(1 for a in articles if a.is_ai_related)} AI-related")
        return articles

    def _fetch_gnews(self, ticker: str, limit: int) -> List[NewsArticle]:
        """Fetch from GNews API (requires API key, free tier: 100 req/day).

        Uses max 2 queries per company to stay well under the daily limit.
        5 companies × 2 queries = 10 requests total.
        """
        if not self.gnews_api_key or self.gnews_api_key.strip() == "":
            logger.info(f"GNews: skipped for {ticker} (no API key)")
            return []

        company = COMPANY_NAMES.get(ticker, ticker)
        articles = []
        import time

        # 5 queries per company (25 total for 5 companies, within 100/day limit)
        for template in GNEWS_SEARCH_TEMPLATES[:5]:
            query = template.format(company=company)
            try:
                # GNews free tier: 1 request/second rate limit
                time.sleep(1.1)
                resp = self.client.get(
                    "https://gnews.io/api/v4/search",
                    params={
                        "q": query,
                        "lang": "en",
                        "max": 10,
                        "sortby": "relevance",
                        "apikey": self.gnews_api_key.strip(),
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for a in data.get("articles", []):
                        articles.append(NewsArticle(
                            title=a.get("title", ""),
                            source=a.get("source", {}).get("name", "unknown"),
                            url=a.get("url", ""),
                            published_date=self._parse_date(a.get("publishedAt")),
                            snippet=a.get("description", ""),
                            is_ai_related=False,
                            ai_score=0,
                        ))
                elif resp.status_code in (403, 429):
                    logger.warning(f"GNews rate limited ({resp.status_code}) — stopping queries for {ticker}.")
                    break
                elif resp.status_code == 401:
                    logger.error("GNews API key invalid. Check GNEWS_API_KEY in .env")
                    break
                else:
                    logger.warning(f"GNews returned {resp.status_code} for query: {query}")
            except Exception as e:
                logger.error(f"GNews error: {e}")

        logger.info(f"GNews: {len(articles)} articles for {ticker}")
        return articles

    def _scrape_newsroom(self, ticker: str) -> List[NewsArticle]:
        """Scrape company newsroom page for headlines."""
        articles = []
        urls = NEWSROOM_URLS.get(ticker, [])

        for url in urls:
            try:
                resp = self.client.get(url)
                if resp.status_code != 200:
                    logger.debug(f"Newsroom {url} returned {resp.status_code}")
                    continue

                html = resp.text
                # Extract titles from common patterns
                # Look for <h2>, <h3>, <a> tags with article-like content
                title_patterns = [
                    r'<h[23][^>]*>\s*<a[^>]*>([^<]+)</a>\s*</h[23]>',
                    r'<a[^>]*class="[^"]*title[^"]*"[^>]*>([^<]+)</a>',
                    r'<h[23][^>]*>([^<]{20,150})</h[23]>',
                    r'"headline":\s*"([^"]{20,200})"',
                ]

                found_titles = set()
                for pattern in title_patterns:
                    matches = re.findall(pattern, html, re.IGNORECASE)
                    for title in matches:
                        title = title.strip()
                        if len(title) > 15 and title not in found_titles:
                            found_titles.add(title)
                            articles.append(NewsArticle(
                                title=title,
                                source=f"newsroom:{ticker}",
                                url=url,
                                published_date=datetime.now(timezone.utc),
                                snippet="",
                                is_ai_related=False,
                                ai_score=0,
                            ))

                logger.info(f"Newsroom {url}: found {len(found_titles)} headlines")

            except Exception as e:
                logger.warning(f"Failed to scrape {url}: {e}")

        return articles

    def _score_article(self, article: NewsArticle):
        """Score an article for AI relevance."""
        text = f"{article.title} {article.snippet}".lower()

        # Check for standalone "ai" as a word boundary match.
        # Many headlines say "AI" without compound phrases like
        # "ai strategy" or "ai-powered", e.g. "India Fuels Its AI Mission",
        # "Cut AI Costs", "NVIDIA AI Day".  We detect these with a
        # simple word-boundary approach.
        import re
        standalone_ai = len(re.findall(r'\bai\b', text))

        # Count keyword matches
        strong_matches = sum(1 for kw in STRONG_AI_KEYWORDS if kw in text)
        moderate_matches = sum(1 for kw in MODERATE_AI_KEYWORDS if kw in text)
        leadership_matches = sum(1 for kw in LEADERSHIP_KEYWORDS if kw in text)
        deployment_matches = sum(1 for kw in DEPLOYMENT_KEYWORDS if kw in text)

        # Standalone "ai" counts as a strong match
        strong_matches += standalone_ai

        # AI relevance score
        ai_score = min(100, strong_matches * 20 + moderate_matches * 10)

        article.is_ai_related = ai_score > 0 or strong_matches > 0
        article.ai_score = ai_score

        # Categorize
        if leadership_matches >= 2:
            article.categories.append("leadership")
        if deployment_matches >= 2:
            article.categories.append("deployment")
        if strong_matches >= 1:
            article.categories.append("ai_strategy")

    def analyze_news(
        self, company_id: str, ticker: str, articles: List[NewsArticle]
    ) -> NewsSignal:
        """Analyze collected articles into a news signal."""
        if not articles:
            return self._empty_signal(company_id, ticker)

        ai_articles = [a for a in articles if a.is_ai_related]
        n_total = len(articles)
        n_ai = len(ai_articles)

        if n_ai == 0:
            return NewsSignal(
                company_id=company_id, ticker=ticker,
                overall_score=Decimal("15"),
                leadership_score=Decimal("15"),
                deployment_score=Decimal("15"),
                investment_score=Decimal("15"),
                article_count=n_total, ai_article_count=0,
                confidence=Decimal("0.4"),
            )

        # Score components
        avg_ai_score = sum(a.ai_score for a in ai_articles) / n_ai
        ai_ratio = n_ai / max(n_total, 1)

        # Leadership: articles mentioning C-suite + AI
        leadership_articles = [a for a in ai_articles if "leadership" in a.categories]
        leadership_score = min(100, (len(leadership_articles) / max(n_ai, 1)) * 100 + avg_ai_score * 0.3)

        # Deployment: articles about real AI use cases
        deployment_articles = [a for a in ai_articles if "deployment" in a.categories]
        deployment_score = min(100, (len(deployment_articles) / max(n_ai, 1)) * 100 + avg_ai_score * 0.2)

        # Investment: overall AI coverage intensity
        investment_score = min(100, ai_ratio * 150 + avg_ai_score * 0.5)

        # Overall weighted
        overall = (
            0.40 * leadership_score
            + 0.35 * deployment_score
            + 0.25 * investment_score
        )
        overall = max(10, min(100, overall))

        # Confidence based on article count
        confidence = min(0.5 + n_ai / 20, 0.90)

        # Top articles for display
        top = sorted(ai_articles, key=lambda a: a.ai_score, reverse=True)[:5]
        top_dicts = [
            {"title": a.title, "source": a.source, "score": a.ai_score,
             "categories": a.categories}
            for a in top
        ]

        return NewsSignal(
            company_id=company_id, ticker=ticker,
            overall_score=Decimal(str(round(overall, 2))),
            leadership_score=Decimal(str(round(leadership_score, 2))),
            deployment_score=Decimal(str(round(deployment_score, 2))),
            investment_score=Decimal(str(round(investment_score, 2))),
            article_count=n_total,
            ai_article_count=n_ai,
            confidence=Decimal(str(round(confidence, 2))),
            top_articles=top_dicts,
        )

    def _deduplicate(self, articles: List[NewsArticle]) -> List[NewsArticle]:
        """Remove duplicate articles by title similarity."""
        seen_titles = set()
        unique = []
        for a in articles:
            key = a.title.lower().strip()[:60]
            if key not in seen_titles:
                seen_titles.add(key)
                unique.append(a)
        return unique

    def _parse_date(self, raw: Optional[str]) -> Optional[datetime]:
        if not raw:
            return datetime.now(timezone.utc)
        for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S.%fZ"):
            try:
                return datetime.strptime(raw[:26], fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return datetime.now(timezone.utc)

    def _cache_articles(self, ticker: str, articles: List[NewsArticle]):
        path = self.data_dir / f"{ticker}.json"
        payload = [
            {
                "title": a.title,
                "source": a.source,
                "url": a.url,
                "published_date": a.published_date.strftime("%Y-%m-%d") if a.published_date else None,
                "snippet": a.snippet,
                "is_ai_related": a.is_ai_related,
                "ai_score": a.ai_score,
                "categories": a.categories,
            }
            for a in articles
        ]
        path.write_text(json.dumps(payload, indent=2))
        logger.info(f"Cached {len(articles)} articles to {path}")

    def load_cached(self, ticker: str) -> List[NewsArticle]:
        path = self.data_dir / f"{ticker}.json"
        if not path.exists():
            return []
        raw = json.loads(path.read_text())
        return [
            NewsArticle(
                title=a["title"], source=a["source"], url=a["url"],
                published_date=self._parse_date(a.get("published_date")),
                snippet=a.get("snippet", ""),
                is_ai_related=a.get("is_ai_related", False),
                ai_score=a.get("ai_score", 0),
                categories=a.get("categories", []),
            )
            for a in raw
        ]

    def _empty_signal(self, company_id: str, ticker: str) -> NewsSignal:
        return NewsSignal(
            company_id=company_id, ticker=ticker,
            overall_score=Decimal("15"), leadership_score=Decimal("15"),
            deployment_score=Decimal("15"), investment_score=Decimal("15"),
            article_count=0, ai_article_count=0,
            confidence=Decimal("0.3"),
        )
