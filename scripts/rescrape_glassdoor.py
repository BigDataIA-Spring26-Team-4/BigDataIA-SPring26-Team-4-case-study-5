#!/usr/bin/env python
"""
Re-scrape Glassdoor reviews with higher limit for all CS3 companies.

Problem: NVDA only has 10 cached reviews (3.7KB) vs 35-41KB for others.
This script forces a fresh fetch with limit=100 per company.

Usage:
    poetry run python -m scripts.rescrape_glassdoor
    poetry run python -m scripts.rescrape_glassdoor --ticker NVDA
"""

import argparse
import logging
from app.pipelines.glassdoor_collector import GlassdoorCultureCollector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

CS3_TICKERS = ["NVDA", "JPM", "WMT", "GE", "DG"]


def main(tickers: list):
    collector = GlassdoorCultureCollector(data_dir="data/glassdoor")
    logger.info("=" * 60)
    logger.info("GLASSDOOR RE-SCRAPE — Targeting 100 reviews per company")
    logger.info("=" * 60)

    for ticker in tickers:
        logger.info(f"\n{ticker}: Fetching reviews (limit=100)...")

        # Check how many we had before
        old_reviews = collector._load_cached(ticker)
        logger.info(f"  Before: {len(old_reviews)} cached reviews")

        # Force fresh fetch (APIs first, then cache fallback)
        reviews = collector.fetch_reviews(ticker, limit=100)
        logger.info(f"  After:  {len(reviews)} reviews")

        if reviews:
            signal = collector.analyze_reviews("check", ticker, reviews)
            logger.info(f"  Culture score: {signal.overall_score}")
            logger.info(f"  Innovation={signal.innovation_score} "
                         f"DataDriven={signal.data_driven_score} "
                         f"AI={signal.ai_awareness_score} "
                         f"Change={signal.change_readiness_score}")
            logger.info(f"  Pos keywords: {signal.positive_keywords_found[:10]}")
            logger.info(f"  Neg keywords: {signal.negative_keywords_found[:10]}")
        else:
            logger.warning(f"  No reviews retrieved for {ticker}")

    logger.info("\nDone. Re-run: poetry run python -m scripts.score_portfolio")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", help="Single ticker")
    args = parser.parse_args()

    if args.ticker:
        main([args.ticker.upper()])
    else:
        main(CS3_TICKERS)
