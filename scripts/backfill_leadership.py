#!/usr/bin/env python
"""
Backfill leadership_signals_score from CS3 collected data.

Computes leadership score from:
  - Board governance score (60% weight)
  - Glassdoor change_readiness (25% weight) — proxy for leadership culture
  - Glassdoor ai_awareness (15% weight) — proxy for tech leadership

Updates the company_signal_summaries table in Snowflake.

Usage:
    poetry run python -m scripts.backfill_leadership
"""

import json
import logging
from pathlib import Path

from app.services.snowflake import (
    get_script_db, get_company_by_ticker,
    get_signal_summary, upsert_signal_summary,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

CS3_TICKERS = ["NVDA", "JPM", "WMT", "GE", "DG"]
RESULTS_DIR = Path("results")


def compute_leadership_score(evidence: dict) -> float:
    cs3 = evidence.get("cs3_signals", {})
    glassdoor = cs3.get("glassdoor", {})
    board = cs3.get("board", {})

    board_gov = board.get("governance_score", 20.0)
    gd_change = glassdoor.get("change_readiness", 50.0)
    gd_ai = glassdoor.get("ai_awareness", 0.0)

    score = 0.60 * board_gov + 0.25 * gd_change + 0.15 * gd_ai
    return round(max(0, min(100, score)), 2)


def main():
    db = get_script_db()
    logger.info("Backfilling leadership_signals_score from CS3 evidence...")

    for ticker in CS3_TICKERS:
        evidence_file = RESULTS_DIR / f"{ticker.lower()}_evidence.json"
        if not evidence_file.exists():
            logger.warning(f"No evidence file for {ticker}, skipping")
            continue

        evidence = json.loads(evidence_file.read_text())
        leadership = compute_leadership_score(evidence)

        company = get_company_by_ticker(db, ticker)
        if not company:
            logger.error(f"{ticker} not found in Snowflake")
            continue

        summary = get_signal_summary(db, company.id)
        if not summary:
            logger.warning(f"No signal summary for {ticker}, skipping")
            continue

        # Update with leadership score
        hiring = float(summary.technology_hiring_score or 0)
        innovation = float(summary.innovation_activity_score or 0)
        digital = float(summary.digital_presence_score or 0)
        signal_count = (summary.signal_count or 3) + 2  # +2 for glassdoor + board

        upsert_signal_summary(
            db,
            company_id=company.id,
            ticker=ticker,
            hiring_score=hiring,
            innovation_score=innovation,
            digital_score=digital,
            leadership_score=leadership,
            signal_count=signal_count,
        )

        logger.info(f"  {ticker}: leadership_signals_score = {leadership}/100")

    db.close()
    logger.info("Done. Re-run score_portfolio to see updated results.")


if __name__ == "__main__":
    main()
