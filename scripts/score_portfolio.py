#!/usr/bin/env python
"""
Score 5 CS3 companies and generate portfolio results.

CS3 Task 6.5: Runs the full Org-AI-R pipeline for NVDA, JPM, WMT, GE, DG
using real evidence from Snowflake, and validates against expected ranges.

Usage:
    poetry run python -m scripts.score_portfolio
    poetry run python -m scripts.score_portfolio --ticker NVDA
"""

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.scoring.integration_service import ScoringIntegrationService
from app.services.snowflake import (
    get_script_db, get_company_by_ticker,
    get_signal_summary, get_evidence_stats,
    list_documents_db, list_signals_db,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

RESULTS_DIR = Path("results")

EXPECTED_RANGES = {
    "NVDA": (85, 95),
    "JPM": (65, 75),
    "WMT": (55, 65),
    "GE": (45, 55),
    "DG": (35, 45),
}

CS3_TICKERS = ["NVDA", "JPM", "WMT", "GE", "DG"]


def load_company_evidence(ticker: str, db) -> dict:
    """Load all evidence for a company from Snowflake."""
    company = get_company_by_ticker(db, ticker)
    if not company:
        logger.error(f"{ticker} not found in Snowflake")
        return {}

    summary = get_signal_summary(db, company.id)
    docs = list_documents_db(db, company_id=company.id)
    signals = list_signals_db(db, company_id=company.id)

    cs2_signals = {}
    glassdoor_score = 0.0
    board_score = 0.0
    sec_scores = {}

    if summary:
        cs2_signals = {
            "technology_hiring_score": float(summary.technology_hiring_score or 0),
            "innovation_activity_score": float(summary.innovation_activity_score or 0),
            "digital_presence_score": float(summary.digital_presence_score or 0),
            "leadership_signals_score": float(summary.leadership_signals_score or 0),
        }

    news_score = 0.0

    for sig in signals:
        score_val = float(sig.normalized_score) if sig.normalized_score else 0
        source = sig.source or ""
        category = sig.category or ""

        if source == "glassdoor" and category == "leadership_signals":
            glassdoor_score = max(glassdoor_score, score_val)
        elif source == "company_website" and category == "leadership_signals":
            board_score = max(board_score, score_val)
        elif source == "news_press_releases" and category == "leadership_signals":
            news_score = max(news_score, score_val)
        elif source.startswith("sec_item"):
            key = source.replace("sec_", "")  # sec_item_1 -> item_1
            sec_scores[key] = max(sec_scores.get(key, 0), score_val)

    evidence_count = len(docs) + len(signals)

    return {
        "company_id": company.id,
        "cs2_signals": cs2_signals,
        "glassdoor_score": glassdoor_score,
        "board_score": board_score,
        "news_score": news_score,
        "sec_scores": sec_scores,
        "evidence_count": evidence_count,
        "document_count": len(docs),
        "signal_count": len(signals),
    }


def score_company(ticker: str, evidence: dict, service: ScoringIntegrationService) -> dict:
    """Score a single company."""
    result = service.score_company(
        ticker=ticker,
        cs2_signals=evidence["cs2_signals"],
        glassdoor_score=evidence["glassdoor_score"],
        board_score=evidence["board_score"],
        evidence_count=evidence["evidence_count"],
        sec_scores=evidence.get("sec_scores"),
        news_score=evidence.get("news_score", 0.0),
    )

    result["document_count"] = evidence["document_count"]
    result["signal_count"] = evidence["signal_count"]
    result["scored_at"] = datetime.now(timezone.utc).isoformat()
    result["cs2_signals"] = evidence["cs2_signals"]
    result["glassdoor_score"] = evidence["glassdoor_score"]
    result["board_score"] = evidence["board_score"]
    result["news_score"] = evidence.get("news_score", 0.0)
    result["sec_scores"] = evidence.get("sec_scores", {})

    return result


def validate_score(ticker: str, score: float) -> str:
    expected = EXPECTED_RANGES.get(ticker)
    if not expected:
        return "no expected range"
    low, high = expected
    if low <= score <= high:
        return "WITHIN RANGE"
    elif score < low:
        return f"BELOW expected ({low}-{high})"
    else:
        return f"ABOVE expected ({low}-{high})"


def main(tickers: list):
    RESULTS_DIR.mkdir(exist_ok=True)
    db = get_script_db()
    service = ScoringIntegrationService()

    logger.info("=" * 70)
    logger.info("CS3 PORTFOLIO SCORING — Org-AI-R Full Pipeline")
    logger.info("=" * 70)

    all_results = {}

    for ticker in tickers:
        logger.info(f"\nScoring {ticker}...")

        evidence = load_company_evidence(ticker, db)
        if not evidence:
            continue

        logger.info(f"  Evidence: {evidence['document_count']} docs, "
                     f"{evidence['signal_count']} signals")
        logger.info(f"  CS2 signals: {evidence['cs2_signals']}")
        logger.info(f"  Glassdoor: {evidence['glassdoor_score']}, "
                     f"Board: {evidence['board_score']}")

        result = score_company(ticker, evidence, service)
        all_results[ticker] = result

        # Save individual result
        out_path = RESULTS_DIR / f"{ticker.lower()}.json"
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2, default=str)

        validation = validate_score(ticker, result["final_score"])
        logger.info(f"  Final Score: {result['final_score']:.2f} — {validation}")
        logger.info(f"  VR={result['vr_score']:.2f} HR={result['hr_score']:.2f} "
                     f"Synergy={result['synergy_score']:.2f}")
        logger.info(f"  CI: [{result['ci_lower']:.2f}, {result['ci_upper']:.2f}]")

    # Summary table
    logger.info(f"\n{'='*70}")
    logger.info("PORTFOLIO SUMMARY")
    logger.info(f"{'='*70}")
    logger.info(f"{'Ticker':<6} {'Final':>7} {'VR':>7} {'HR':>7} {'Syn':>7} "
                f"{'PF':>6} {'TC':>6} {'CI':>14} {'Validation'}")
    logger.info("-" * 85)

    for ticker in tickers:
        r = all_results.get(ticker)
        if not r:
            continue
        val = validate_score(ticker, r["final_score"])
        logger.info(
            f"{ticker:<6} {r['final_score']:>7.2f} {r['vr_score']:>7.2f} "
            f"{r['hr_score']:>7.2f} {r['synergy_score']:>7.2f} "
            f"{r['position_factor']:>6.2f} {r['talent_concentration']:>6.2f} "
            f"[{r['ci_lower']:>5.1f},{r['ci_upper']:>5.1f}] {val}"
        )

    db.close()
    logger.info("\nAll results saved to results/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", help="Score a single ticker")
    args = parser.parse_args()

    if args.ticker:
        main([args.ticker.upper()])
    else:
        main(CS3_TICKERS)
