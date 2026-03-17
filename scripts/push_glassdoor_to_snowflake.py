#!/usr/bin/env python
"""
Push fresh Glassdoor culture scores to Snowflake as signals.

The rescrape_glassdoor script only cached reviews locally. This script
analyzes the cached reviews and inserts the culture scores into Snowflake
so that score_portfolio picks them up.

Usage:
    poetry run python -m scripts.push_glassdoor_to_snowflake
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal

from app.pipelines.glassdoor_collector import GlassdoorCultureCollector
from app.services.snowflake import (
    get_script_db, get_company_by_ticker, insert_signal,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

CS3_TICKERS = ["NVDA", "JPM", "WMT", "GE", "DG"]


def main():
    db = get_script_db()
    collector = GlassdoorCultureCollector(data_dir="data/glassdoor")

    logger.info("=" * 60)
    logger.info("PUSH GLASSDOOR CULTURE SCORES TO SNOWFLAKE")
    logger.info("=" * 60)

    for ticker in CS3_TICKERS:
        company = get_company_by_ticker(db, ticker)
        if not company:
            logger.error(f"{ticker} not found in Snowflake")
            continue

        reviews = collector._load_cached(ticker)
        if not reviews:
            logger.warning(f"{ticker}: no cached reviews")
            continue

        signal = collector.analyze_reviews(str(company.id), ticker, reviews)

        # Insert as a glassdoor signal (same source/category as score_portfolio reads)
        insert_signal(
            db,
            company_id=company.id,
            category="leadership_signals",
            source="glassdoor",
            signal_date=datetime.now(timezone.utc),
            raw_value=f"Glassdoor culture: {signal.overall_score}/100 from {signal.review_count} reviews",
            normalized_score=float(signal.overall_score),
            confidence=float(signal.confidence),
            metadata={
                "innovation_score": float(signal.innovation_score),
                "data_driven_score": float(signal.data_driven_score),
                "ai_awareness_score": float(signal.ai_awareness_score),
                "change_readiness_score": float(signal.change_readiness_score),
                "review_count": signal.review_count,
                "avg_rating": float(signal.avg_rating),
                "positive_keywords": signal.positive_keywords_found,
                "negative_keywords": signal.negative_keywords_found,
            },
        )

        logger.info(f"{ticker}: pushed glassdoor score={signal.overall_score} "
                     f"({signal.review_count} reviews)")

    db.close()
    logger.info("\nDone. Run: poetry run python -m scripts.score_portfolio")


if __name__ == "__main__":
    main()
