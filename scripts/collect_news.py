#!/usr/bin/env python
"""
Collect news/press releases for CS3 companies and push to Snowflake.

Scrapes company newsroom pages and uses GNews API (free) to find
AI-related announcements, then scores and stores as signals.

Usage:
    poetry run python -m scripts.collect_news
    poetry run python -m scripts.collect_news --ticker JPM
"""

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.pipelines.news_collector import NewsCollector
from app.services.snowflake import (
    get_script_db, get_company_by_ticker, insert_signal,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

CS3_TICKERS = ["NVDA", "JPM", "WMT", "GE", "DG"]
RESULTS_DIR = Path("results")


def main(tickers: list):
    RESULTS_DIR.mkdir(exist_ok=True)
    db = get_script_db()
    collector = NewsCollector(data_dir="data/news")

    logger.info("=" * 60)
    logger.info("NEWS & PRESS RELEASE COLLECTION")
    logger.info("=" * 60)

    all_signals = {}

    for ticker in tickers:
        logger.info(f"\n{ticker}: Collecting news...")

        company = get_company_by_ticker(db, ticker)
        if not company:
            logger.error(f"{ticker} not found in Snowflake")
            continue

        # Collect articles
        articles = collector.collect_news(ticker, limit=30)

        # Analyze
        signal = collector.analyze_news(str(company.id), ticker, articles)
        all_signals[ticker] = signal

        # Push to Snowflake
        insert_signal(
            db, company_id=company.id,
            category="leadership_signals",
            source="news_press_releases",
            signal_date=datetime.now(timezone.utc),
            raw_value=f"News: {signal.ai_article_count}/{signal.article_count} AI articles, score={signal.overall_score}",
            normalized_score=float(signal.overall_score),
            confidence=float(signal.confidence),
            metadata={
                "leadership_score": float(signal.leadership_score),
                "deployment_score": float(signal.deployment_score),
                "investment_score": float(signal.investment_score),
                "article_count": signal.article_count,
                "ai_article_count": signal.ai_article_count,
                "top_articles": signal.top_articles,
            },
        )

        logger.info(f"  Articles: {signal.article_count} total, {signal.ai_article_count} AI-related")
        logger.info(f"  Overall: {signal.overall_score}")
        logger.info(f"  Leadership={signal.leadership_score} "
                     f"Deployment={signal.deployment_score} "
                     f"Investment={signal.investment_score}")
        if signal.top_articles:
            logger.info(f"  Top articles:")
            for a in signal.top_articles[:3]:
                logger.info(f"    - [{a['score']:.0f}] {a['title'][:80]}")

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("NEWS COLLECTION SUMMARY")
    logger.info(f"{'='*60}")
    logger.info(f"{'Ticker':<6} {'Total':>6} {'AI':>4} {'Score':>7} {'Lead':>6} {'Deploy':>7} {'Invest':>7}")
    logger.info("-" * 50)

    for ticker in tickers:
        s = all_signals.get(ticker)
        if s:
            logger.info(f"{ticker:<6} {s.article_count:>6} {s.ai_article_count:>4} "
                         f"{float(s.overall_score):>7.1f} {float(s.leadership_score):>6.1f} "
                         f"{float(s.deployment_score):>7.1f} {float(s.investment_score):>7.1f}")

    db.close()
    logger.info("\nDone. Re-run: poetry run python -m scripts.score_portfolio")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", help="Single ticker")
    args = parser.parse_args()

    if args.ticker:
        main([args.ticker.upper()])
    else:
        main(CS3_TICKERS)
