#!/usr/bin/env python
"""
Score SEC filing text for AI evidence using the fixed DocumentParser.

v3: Improved keyword lists with:
  - Financial-sector AI terms (technology spend, digital capabilities, etc.)
  - Separated genuine AI governance from generic IT/compliance language
  - Generic compliance terms (cybersecurity, data breach) are NOT counted

Reads raw 10-K filings from disk, uses DocumentParser to extract
real section content, then scores for AI keyword density.

Usage:
    poetry run python -m scripts.score_sec_text_v2
    poetry run python -m scripts.score_sec_text_v2 --ticker NVDA
"""

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.pipelines.document_parser import DocumentParser
from app.services.snowflake import (
    get_script_db, get_company_by_ticker, insert_signal,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

CS3_TICKERS = ["NVDA", "JPM", "WMT", "GE", "DG"]
RAW_DIR = Path("data/raw/sec/sec-edgar-filings")
RESULTS_DIR = Path("results")

# ─── Keyword lists ──────────────────────────────────────────────────
# ONLY terms that genuinely indicate AI investment/capability.
# Generic compliance terms (cybersecurity, risk management, data breach)
# are deliberately EXCLUDED — they appear in every 10-K and inflate
# scores for companies like DG that have no real AI activity.

AI_EVIDENCE_KEYWORDS = {
    "strategy": [
        "artificial intelligence", "machine learning", "deep learning",
        "ai strategy", "ai-driven", "ai-powered", "ai capabilities",
        "generative ai", "large language model", "neural network",
        "ai platform", "ai infrastructure",
        # Financial-sector: how banks/insurers talk about AI
        "technology-driven", "digital capabilities",
        "advanced analytics", "predictive analytics",
        "algorithmic", "quantitative models",
        "natural language processing",
    ],
    "investment": [
        "technology investment", "r&d spending", "research and development",
        "digital transformation", "cloud infrastructure", "data center",
        "capital expenditure",
        # Financial-sector additions
        "technology spend", "tech investment", "technology budget",
        "innovation investment", "modernization",
    ],
    "deployment": [
        "deployed", "in production", "production environment",
        "ml platform", "automated", "automation", "use case",
        "ai application", "ai solution", "ai product",
        # Financial-sector: concrete AI use cases in banking
        "real-time", "straight-through processing",
        "fraud detection", "anti-money laundering",
        "customer experience", "personalization",
    ],
    "talent": [
        "data scientist", "ml engineer", "ai team", "ai talent",
        "ai research", "machine learning team",
        # Broader talent signals
        "technology professionals", "engineering team",
        "data engineering", "analytics team",
    ],
    "governance": [
        # ONLY genuinely AI-related governance terms
        "ai governance", "responsible ai", "ai ethics",
        "model risk", "model validation", "model governance",
        "ai oversight", "ai policy", "algorithmic bias",
        "data governance",
        # NOT included: cybersecurity, risk management, data privacy,
        # data breach — these are generic IT compliance, not AI governance
    ],
}


def count_keywords(text: str) -> dict:
    text_lower = text.lower()
    counts = {}
    total = 0
    for category, keywords in AI_EVIDENCE_KEYWORDS.items():
        cat_count = sum(text_lower.count(kw) for kw in keywords)
        counts[category] = cat_count
        total += cat_count
    counts["total"] = total
    return counts


def score_section(section: str, text: str) -> dict:
    if not text or len(text.split()) < 50:
        return {"section": section, "score": 10.0, "total_mentions": 0,
                "word_count": 0, "density_per_1k": 0, "keyword_counts": {}}

    word_count = len(text.split())
    kw_counts = count_keywords(text)
    total = kw_counts["total"]
    density = (total / max(word_count, 1)) * 1000

    if density >= 10:
        score = min(100, 75 + (density - 10) * 2)
    elif density >= 3:
        score = 50 + (density - 3) * 3.5
    elif density >= 1:
        score = 30 + (density - 1) * 10
    elif total > 0:
        score = 15 + total * 2
    else:
        score = 10

    score = max(0, min(100, score))

    return {
        "section": section,
        "score": round(score, 2),
        "keyword_counts": kw_counts,
        "total_mentions": total,
        "word_count": word_count,
        "density_per_1k": round(density, 2),
    }


def process_company(ticker: str, db) -> dict:
    company = get_company_by_ticker(db, ticker)
    if not company:
        logger.error(f"{ticker} not found")
        return {}

    filing_dir = RAW_DIR / ticker / "10-K"
    if not filing_dir.exists():
        logger.warning(f"No 10-K directory for {ticker}")
        return {}

    parser = DocumentParser()
    accession_dirs = sorted(filing_dir.iterdir(), reverse=True)
    logger.info(f"  Found {len(accession_dirs)} 10-K filings")

    # Parse the 2 most recent filings and aggregate section text
    section_texts = {"item_1": [], "item_1a": [], "item_7": []}

    for acc_dir in accession_dirs[:2]:
        filing_file = acc_dir / "full-submission.txt"
        if not filing_file.exists():
            continue

        logger.info(f"  Parsing {acc_dir.name}...")
        doc = parser.parse_filing(filing_file, ticker)
        logger.info(f"    {doc.word_count} total words, sections: {list(doc.sections.keys())}")

        for section in ["item_1", "item_1a", "item_7"]:
            if section in doc.sections:
                sec_text = doc.sections[section]
                sec_words = len(sec_text.split())
                if sec_words > 50:
                    section_texts[section].append(sec_text)
                    logger.info(f"    {section}: {sec_words} words")

    results = {}
    for section in ["item_1", "item_1a", "item_7"]:
        combined = " ".join(section_texts[section])
        section_result = score_section(section, combined)
        results[section] = section_result

        category = "leadership_signals" if section != "item_1" else "digital_presence"
        insert_signal(
            db, company_id=company.id,
            category=category,
            source=f"sec_{section}",
            signal_date=datetime.now(timezone.utc),
            raw_value=f"{section}: {section_result['total_mentions']} AI mentions in {section_result['word_count']} words",
            normalized_score=section_result["score"],
            confidence=min(0.6 + section_result["word_count"] / 50000, 0.90),
            metadata=section_result,
        )

        logger.info(
            f"    => {section}: score={section_result['score']}/100, "
            f"{section_result['total_mentions']} mentions, "
            f"density={section_result['density_per_1k']}/1k"
        )

    return results


def main(tickers: list):
    RESULTS_DIR.mkdir(exist_ok=True)
    db = get_script_db()

    logger.info("=" * 60)
    logger.info("SEC TEXT ANALYSIS v3 — Clean Keywords (no noise)")
    logger.info("=" * 60)

    all_results = {}
    for ticker in tickers:
        logger.info(f"\n{ticker}:")
        results = process_company(ticker, db)
        all_results[ticker] = results

        out_path = RESULTS_DIR / f"{ticker.lower()}_sec_scores.json"
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2, default=str)

    logger.info(f"\n{'='*60}")
    logger.info("SEC TEXT v3 SUMMARY")
    logger.info(f"{'='*60}")
    logger.info(f"{'Ticker':<6} {'Item1':>7} {'Item1A':>7} {'Item7':>7} {'Avg':>7}")
    logger.info("-" * 38)

    for ticker in tickers:
        r = all_results.get(ticker, {})
        s1 = r.get("item_1", {}).get("score", 0)
        s1a = r.get("item_1a", {}).get("score", 0)
        s7 = r.get("item_7", {}).get("score", 0)
        avg = (s1 + s1a + s7) / 3 if r else 0
        logger.info(f"{ticker:<6} {s1:>7.1f} {s1a:>7.1f} {s7:>7.1f} {avg:>7.1f}")

    db.close()
    logger.info("\nDone. Run: poetry run python -m scripts.score_portfolio")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", help="Single ticker")
    args = parser.parse_args()

    if args.ticker:
        main([args.ticker.upper()])
    else:
        main(CS3_TICKERS)
