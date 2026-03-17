#!/usr/bin/env python
"""
Improve signal quality: more Glassdoor reviews + multi-site jobs + updated summaries.

1. Fetches 100+ Glassdoor reviews per company (vs 50 before)
2. Scrapes jobs from Indeed + ZipRecruiter + Glassdoor (no LinkedIn to avoid bans)
3. Recomputes leadership_signals_score incorporating SEC text scores
4. Updates company_signal_summaries in Snowflake

Usage:
    poetry run python -m scripts.improve_signals
    poetry run python -m scripts.improve_signals --ticker NVDA
    poetry run python -m scripts.improve_signals --skip-jobs
"""

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from app.pipelines.glassdoor_collector import GlassdoorCultureCollector
from app.pipelines.job_signals import JobSignalCollector, JobPosting
from app.services.snowflake import (
    get_script_db, get_company_by_ticker,
    insert_signal, upsert_signal_summary,
    get_signal_summary, list_signals_db,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

CS3_COMPANIES = {
    "NVDA": "NVIDIA",
    "JPM": "JPMorgan Chase",
    "WMT": "Walmart",
    "GE": "General Electric",
    "DG": "Dollar General",
}

# Safe job sites (no login required, lower ban risk)
SAFE_JOB_SITES = ["indeed", "zip_recruiter", "glassdoor"]
RESULTS_DIR = Path("results")


def scrape_jobs_multi(company_name: str, max_per_site: int = 20) -> list[JobPosting]:
    try:
        from jobspy import scrape_jobs
    except ImportError:
        logger.error("python-jobspy not installed")
        return []

    collector = JobSignalCollector()
    all_postings = []
    seen = set()

    for site in SAFE_JOB_SITES:
        try:
            logger.info(f"    Scraping {site}...")
            search = f'"{company_name}" AI OR "machine learning" OR "data scientist"'
            kwargs = {
                "site_name": [site],
                "search_term": search,
                "results_wanted": max_per_site,
            }
            if site == "indeed":
                kwargs["country_indeed"] = "USA"

            df = scrape_jobs(**kwargs)
            time.sleep(4)

            if df is None or len(df) == 0:
                logger.info(f"      No results from {site}")
                continue

            count = 0
            for _, row in df.iterrows():
                title = str(row.get("title", "")).lower().strip()
                if title in seen:
                    continue
                seen.add(title)

                posting = JobPosting(
                    title=str(row.get("title", "")),
                    company=str(row.get("company_name", company_name)),
                    location=str(row.get("location", "Unknown")),
                    description=str(row.get("description", "")),
                    posted_date=str(row.get("date_posted", "")),
                    source=site,
                    url=str(row.get("job_url", "")),
                    is_ai_related=False,
                    ai_skills=[],
                )
                posting = collector.classify_posting(posting)
                all_postings.append(posting)
                count += 1

            logger.info(f"      {count} unique postings from {site}")

        except Exception as e:
            logger.warning(f"      {site} failed: {e}")

    ai_count = sum(1 for p in all_postings if p.is_ai_related)
    logger.info(f"    Total: {len(all_postings)} postings, {ai_count} AI-related")
    return all_postings


def fetch_more_reviews(ticker: str, limit: int = 100) -> float:
    collector = GlassdoorCultureCollector()
    reviews = collector.fetch_reviews(ticker, limit=limit)
    if not reviews:
        return 0.0
    signal = collector.analyze_reviews("", ticker, reviews)
    logger.info(f"    Glassdoor: {signal.review_count} reviews, score={signal.overall_score}")
    return float(signal.overall_score)


def compute_leadership_from_all_signals(company_id: str, db) -> float:
    """Compute leadership score from board + glassdoor + SEC text signals."""
    signals = list_signals_db(db, company_id=company_id)

    board_score = 0.0
    glassdoor_score = 0.0
    sec_item_1a_score = 0.0
    sec_item_7_score = 0.0

    for sig in signals:
        score_val = float(sig.normalized_score) if sig.normalized_score else 0
        source = sig.source or ""

        if source == "company_website":
            board_score = max(board_score, score_val)
        elif source == "glassdoor":
            glassdoor_score = max(glassdoor_score, score_val)
        elif source == "sec_item_1a":
            sec_item_1a_score = max(sec_item_1a_score, score_val)
        elif source == "sec_item_7":
            sec_item_7_score = max(sec_item_7_score, score_val)

    # Weighted: board 35%, SEC item_1a 25%, SEC item_7 20%, glassdoor 20%
    leadership = (
        0.35 * board_score
        + 0.25 * sec_item_1a_score
        + 0.20 * sec_item_7_score
        + 0.20 * glassdoor_score
    )
    return round(max(0, min(100, leadership)), 2)


def main(tickers: list, skip_jobs: bool = False):
    RESULTS_DIR.mkdir(exist_ok=True)
    db = get_script_db()

    logger.info("=" * 60)
    logger.info("SIGNAL QUALITY IMPROVEMENT")
    logger.info("=" * 60)

    collector = JobSignalCollector()

    for ticker in tickers:
        company_name = CS3_COMPANIES.get(ticker)
        if not company_name:
            continue

        logger.info(f"\n{ticker} — {company_name}")

        company = get_company_by_ticker(db, ticker)
        if not company:
            logger.error(f"  Not found in Snowflake")
            continue

        # 1. More Glassdoor reviews
        logger.info(f"  [1/3] Fetching more Glassdoor reviews...")
        gd_score = fetch_more_reviews(ticker, limit=100)

        if gd_score > 0:
            insert_signal(
                db, company_id=company.id,
                category="leadership_signals", source="glassdoor",
                signal_date=datetime.now(timezone.utc),
                raw_value=f"100+ reviews, culture score={gd_score}",
                normalized_score=gd_score,
                confidence=0.85,
                metadata={"review_count": 100, "source": "wextractor"},
            )

        # 2. Multi-site job scraping
        new_hiring_score = None
        if not skip_jobs:
            logger.info(f"  [2/3] Multi-site job scraping...")
            postings = scrape_jobs_multi(company_name)

            if postings:
                signal = collector.analyze_job_postings(
                    company_id=company.id, company=company_name, postings=postings,
                )
                insert_signal(
                    db, company_id=company.id,
                    category=signal.category.value, source="multi_site",
                    signal_date=signal.signal_date,
                    raw_value=signal.raw_value,
                    normalized_score=signal.normalized_score,
                    confidence=signal.confidence,
                    metadata=signal.metadata,
                )
                new_hiring_score = signal.normalized_score
                logger.info(f"    NEW hiring score: {new_hiring_score}/100")
        else:
            logger.info(f"  [2/3] Skipping job scraping")

        time.sleep(3)

        # 3. Recompute leadership with all signals (board + glassdoor + SEC)
        logger.info(f"  [3/3] Recomputing leadership from all signals...")
        leadership = compute_leadership_from_all_signals(company.id, db)
        logger.info(f"    Leadership score: {leadership}/100")

        # Update summary table
        summary = get_signal_summary(db, company.id)
        if summary:
            hiring = new_hiring_score if new_hiring_score else float(summary.technology_hiring_score or 0)
            upsert_signal_summary(
                db, company_id=company.id, ticker=ticker,
                hiring_score=hiring,
                innovation_score=float(summary.innovation_activity_score or 0),
                digital_score=float(summary.digital_presence_score or 0),
                leadership_score=leadership,
                signal_count=(summary.signal_count or 0) + 2,
            )

        logger.info(f"  Summary updated for {ticker}")

    db.close()
    logger.info("\nDone. Run: poetry run python -m scripts.score_portfolio")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", help="Single ticker")
    parser.add_argument("--skip-jobs", action="store_true", help="Skip job scraping")
    args = parser.parse_args()

    tickers = [args.ticker.upper()] if args.ticker else list(CS3_COMPANIES.keys())
    main(tickers, skip_jobs=args.skip_jobs)
