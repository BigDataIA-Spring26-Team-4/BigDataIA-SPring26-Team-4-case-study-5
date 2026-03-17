#!/usr/bin/env python
"""
Comprehensive job scraping with proper delays, multiple queries, and all sites.

Strategy:
  - 4 search queries per company to catch different job titles
  - 5 sites: indeed, linkedin, google, glassdoor, zip_recruiter
  - Scrape ONE site at a time with 8-10s delays between requests
  - 20s delays between companies to avoid cross-site rate limits
  - Deduplication by normalized title + company
  - Google Jobs uses google_search_term (required for that site)

Usage:
    poetry run python -m scripts.scrape_jobs_v2
    poetry run python -m scripts.scrape_jobs_v2 --ticker NVDA
"""

import argparse
import json
import logging
import time
import random
from datetime import datetime, timezone
from pathlib import Path

from app.pipelines.job_signals import JobSignalCollector, JobPosting
from app.services.snowflake import (
    get_script_db, get_company_by_ticker,
    insert_signal, upsert_signal_summary,
    get_signal_summary,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

CS3_COMPANIES = {
    "NVDA": {"name": "NVIDIA", "full": "NVIDIA Corporation"},
    "JPM": {"name": "JPMorgan", "full": "JPMorgan Chase"},
    "WMT": {"name": "Walmart", "full": "Walmart"},
    "GE": {"name": "GE Aerospace", "full": "General Electric"},
    "DG": {"name": "Dollar General", "full": "Dollar General"},
}

SEARCH_TEMPLATES = [
    '"{name}" machine learning',
    '"{name}" data scientist',
    '"{name}" AI engineer',
    '"{name}" software engineer data',
]

GOOGLE_TEMPLATES = [
    '{name} machine learning engineer jobs in USA',
    '{name} data scientist jobs in USA',
    '{name} AI engineer jobs in USA',
]

RESULTS_DIR = Path("results")


def delay(min_sec=6, max_sec=12):
    t = random.uniform(min_sec, max_sec)
    logger.info(f"      Waiting {t:.1f}s...")
    time.sleep(t)


def scrape_site(site: str, search_term: str, google_term: str = "",
                max_results: int = 15) -> list[dict]:
    try:
        from jobspy import scrape_jobs

        kwargs = {
            "site_name": [site],
            "search_term": search_term,
            "results_wanted": max_results,
        }
        if site == "indeed":
            kwargs["country_indeed"] = "USA"
        if site == "google" and google_term:
            kwargs["google_search_term"] = google_term

        df = scrape_jobs(**kwargs)

        if df is None or len(df) == 0:
            return []

        results = []
        for _, row in df.iterrows():
            results.append({
                "title": str(row.get("title", "")),
                "company": str(row.get("company_name", "")),
                "location": str(row.get("location", "")),
                "description": str(row.get("description", "")),
                "posted_date": str(row.get("date_posted", "")),
                "source": site,
                "url": str(row.get("job_url", "")),
            })
        return results

    except Exception as e:
        logger.warning(f"      {site} error: {e}")
        return []


def scrape_company(ticker: str, company_info: dict) -> list[JobPosting]:
    collector = JobSignalCollector()
    name = company_info["name"]
    all_raw = []
    seen_keys = set()

    # Scrape each site with each query
    sites_to_try = ["indeed", "google", "linkedin", "glassdoor"]

    for query_template in SEARCH_TEMPLATES:
        search_term = query_template.format(name=name)

        for site in sites_to_try:
            google_term = ""
            if site == "google":
                google_term = f"{name} machine learning data scientist jobs in USA"

            logger.info(f"    [{site}] query='{search_term[:50]}...'")

            raw_results = scrape_site(site, search_term, google_term, max_results=10)

            # Deduplicate
            new_count = 0
            for r in raw_results:
                key = (r["title"].lower().strip(), r["company"].lower().strip())
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_raw.append(r)
                    new_count += 1

            if raw_results:
                logger.info(f"      Got {len(raw_results)} results, {new_count} new unique")
            else:
                logger.info(f"      No results")

            delay(6, 10)

        # Longer pause between query batches
        delay(3, 5)

    # Convert to JobPosting and classify
    postings = []
    for r in all_raw:
        posting = JobPosting(
            title=r["title"],
            company=r["company"],
            location=r["location"],
            description=r["description"],
            posted_date=r["posted_date"],
            source=r["source"],
            url=r["url"],
            is_ai_related=False,
            ai_skills=[],
        )
        posting = collector.classify_posting(posting)
        postings.append(posting)

    ai_count = sum(1 for p in postings if p.is_ai_related)
    tech_count = sum(1 for p in postings if collector._is_tech_job(p))
    logger.info(f"  TOTAL: {len(postings)} unique postings, {tech_count} tech, {ai_count} AI-related")

    return postings


def main(tickers: list):
    RESULTS_DIR.mkdir(exist_ok=True)
    db = get_script_db()
    collector = JobSignalCollector()

    logger.info("=" * 60)
    logger.info("COMPREHENSIVE JOB SCRAPING v2")
    logger.info("=" * 60)

    for ticker in tickers:
        info = CS3_COMPANIES.get(ticker)
        if not info:
            continue

        logger.info(f"\n{'='*50}")
        logger.info(f"  {ticker} — {info['full']}")
        logger.info(f"{'='*50}")

        company = get_company_by_ticker(db, ticker)
        if not company:
            logger.error(f"  Not found in Snowflake")
            continue

        postings = scrape_company(ticker, info)

        if not postings:
            logger.warning(f"  No postings found, keeping existing score")
            continue

        # Analyze and score
        signal = collector.analyze_job_postings(
            company_id=company.id, company=info["full"], postings=postings,
        )

        # Store signal
        insert_signal(
            db, company_id=company.id,
            category=signal.category.value,
            source="multi_site_v2",
            signal_date=signal.signal_date,
            raw_value=signal.raw_value,
            normalized_score=signal.normalized_score,
            confidence=signal.confidence,
            metadata=signal.metadata,
        )

        # Update summary
        summary = get_signal_summary(db, company.id)
        if summary:
            upsert_signal_summary(
                db, company_id=company.id, ticker=ticker,
                hiring_score=signal.normalized_score,
                innovation_score=float(summary.innovation_activity_score or 0),
                digital_score=float(summary.digital_presence_score or 0),
                leadership_score=float(summary.leadership_signals_score or 0),
                signal_count=(summary.signal_count or 0) + 1,
            )

        logger.info(f"  Hiring score: {signal.normalized_score}/100")
        logger.info(f"  Skills found: {signal.metadata.get('skills_found', [])}")

        # Save raw postings for reference
        postings_file = RESULTS_DIR / f"{ticker.lower()}_jobs.json"
        with open(postings_file, "w") as f:
            json.dump([{
                "title": p.title, "company": p.company,
                "source": p.source, "is_ai": p.is_ai_related,
                "skills": p.ai_skills,
            } for p in postings], f, indent=2)

        # Long delay between companies
        logger.info(f"  Waiting 20s before next company...")
        time.sleep(20)

    db.close()
    logger.info("\nDone. Run: poetry run python -m scripts.score_portfolio")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", help="Single ticker")
    args = parser.parse_args()

    tickers = [args.ticker.upper()] if args.ticker else list(CS3_COMPANIES.keys())
    main(tickers)
