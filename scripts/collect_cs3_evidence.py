#!/usr/bin/env python
"""
CS3 evidence collection: seed new companies and run full pipeline.

This script:
1. Seeds the 3 new CS3 companies (NVDA, GE, DG) + Technology industry
2. Runs CS2 pipeline (SEC filings, job signals, tech stack, patents) for them
3. Runs CS3-only collectors (Glassdoor reviews, board composition) for all 5
4. Stores everything in Snowflake

Usage:
    python -m scripts.collect_cs3_evidence --companies all
    python -m scripts.collect_cs3_evidence --companies NVDA,JPM
    python -m scripts.collect_cs3_evidence --companies all --skip-sec
    python -m scripts.collect_cs3_evidence --companies all --cs3-only
"""

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from app.pipelines.document_parser import DocumentParser, SemanticChunker
from app.pipelines.job_signals import JobSignalCollector
from app.pipelines.patent_signals import PatentSignalCollector
from app.pipelines.sec_edgar import SECEdgarPipeline
from app.pipelines.tech_signals import TechStackCollector
from app.pipelines.glassdoor_collector import GlassdoorCultureCollector
from app.pipelines.board_analyzer import BoardCompositionAnalyzer
from app.services.snowflake import (
    get_company_by_ticker,
    get_script_db,
    insert_chunks,
    insert_document,
    insert_signal,
    upsert_signal_summary,
    IndustryRow,
    CompanyRow,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# The 5 CS3 target companies
CS3_COMPANIES = {
    "NVDA": {"name": "NVIDIA Corporation", "sector": "Technology", "assignee": "NVIDIA"},
    "JPM": {"name": "JPMorgan Chase", "sector": "Financial", "assignee": "JPMorgan"},
    "WMT": {"name": "Walmart Inc.", "sector": "Retail", "assignee": "Walmart"},
    "GE": {"name": "General Electric Company", "sector": "Manufacturing", "assignee": "General Electric"},
    "DG": {"name": "Dollar General Corporation", "sector": "Retail", "assignee": "Dollar General"},
}

# New companies that need CS2 pipeline run (not already in DB from CS2)
NEW_CS3_TICKERS = ["NVDA", "GE", "DG"]

DATA_DIR = Path("data")
SIGNALS_DIR = DATA_DIR / "signals"
RESULTS_DIR = Path("results")


def ensure_dirs():
    for d in [DATA_DIR / "raw", DATA_DIR / "processed", SIGNALS_DIR,
              DATA_DIR / "glassdoor", DATA_DIR / "board", RESULTS_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def seed_cs3_companies(db):
    """Insert Technology industry and 3 new companies if they don't exist."""
    logger.info("Checking CS3 seed data...")

    # Technology industry
    existing = db.query(IndustryRow).filter(IndustryRow.id == "550e8400-e29b-41d4-a716-446655440006").first()
    if not existing:
        row = IndustryRow(
            id="550e8400-e29b-41d4-a716-446655440006",
            name="Technology",
            sector="Technology",
            h_r_base=85,
        )
        db.add(row)
        db.commit()
        logger.info("  Inserted Technology industry")
    else:
        logger.info("  Technology industry already exists")

    seed_map = {
        "NVDA": ("550e8400-e29b-41d4-a716-446655440020", "NVIDIA Corporation", "550e8400-e29b-41d4-a716-446655440006"),
        "GE": ("550e8400-e29b-41d4-a716-446655440021", "General Electric Company", "550e8400-e29b-41d4-a716-446655440001"),
        "DG": ("550e8400-e29b-41d4-a716-446655440022", "Dollar General Corporation", "550e8400-e29b-41d4-a716-446655440004"),
    }

    for ticker, (cid, name, ind_id) in seed_map.items():
        existing = db.query(CompanyRow).filter(CompanyRow.id == cid).first()
        if not existing:
            row = CompanyRow(id=cid, name=name, ticker=ticker, industry_id=ind_id, position_factor=0.0)
            db.add(row)
            db.commit()
            logger.info(f"  Inserted {ticker}: {name}")
        else:
            logger.info(f"  {ticker} already exists")


def collect_sec_documents(ticker: str, company_id: str, db) -> dict:
    """Download SEC filings, parse, chunk, store in Snowflake."""
    logger.info(f"  [SEC] Downloading filings for {ticker}...")

    pipeline = SECEdgarPipeline(
        company_name="PE-OrgAIR-Platform",
        email="prajapati.dee@northeastern.edu",
    )
    parser = DocumentParser()
    chunker = SemanticChunker()

    filings = pipeline.download_filings(
        ticker=ticker,
        filing_types=["10-K", "10-Q", "8-K"],
        limit=10,
        after="2021-01-01",
    )
    logger.info(f"  Downloaded {len(filings)} filings")

    stats = {"total": 0, "chunks": 0, "errors": 0}
    for filing_path in filings:
        try:
            doc = parser.parse_filing(filing_path, ticker)
            chunks = chunker.chunk_document(doc)
            doc_row = insert_document(
                db, company_id=company_id, ticker=ticker,
                filing_type=doc.filing_type, filing_date=doc.filing_date,
                content_hash=doc.content_hash, word_count=doc.word_count,
                chunk_count=len(chunks), source_path=doc.source_path,
            )
            insert_chunks(db, document_id=doc_row.id, chunks=chunks)
            stats["total"] += 1
            stats["chunks"] += len(chunks)
            logger.info(f"    {doc.filing_type} | {doc.word_count:,} words | {len(chunks)} chunks")
        except Exception as e:
            stats["errors"] += 1
            logger.error(f"    Failed {filing_path}: {e}")
    return stats


def collect_cs2_signals(ticker: str, company_id: str, db) -> dict:
    """Collect CS2-style signals: jobs, tech stack, patents."""
    info = CS3_COMPANIES[ticker]
    result = {}

    # Jobs
    logger.info(f"  [Jobs] Scraping job postings for {info['name']}...")
    job_collector = JobSignalCollector()
    postings = job_collector.scrape_jobs(info["name"], max_results=25)
    postings = [job_collector.classify_posting(p) for p in postings]
    job_signal = job_collector.analyze_job_postings(
        company_id=company_id, company=info["name"], postings=postings,
    )
    insert_signal(db, company_id=company_id, category=job_signal.category.value,
                  source=job_signal.source.value, signal_date=job_signal.signal_date,
                  raw_value=job_signal.raw_value, normalized_score=job_signal.normalized_score,
                  confidence=job_signal.confidence, metadata=job_signal.metadata)
    result["hiring"] = job_signal.normalized_score
    logger.info(f"    Hiring score: {job_signal.normalized_score}/100")
    time.sleep(1)

    # Tech stack
    logger.info(f"  [Tech] Loading tech stack for {ticker}...")
    tech_collector = TechStackCollector()
    technologies = tech_collector.get_known_technologies(ticker)
    tech_signal = tech_collector.analyze_tech_stack(company_id=company_id, technologies=technologies)
    insert_signal(db, company_id=company_id, category=tech_signal.category.value,
                  source=tech_signal.source.value, signal_date=tech_signal.signal_date,
                  raw_value=tech_signal.raw_value, normalized_score=tech_signal.normalized_score,
                  confidence=tech_signal.confidence, metadata=tech_signal.metadata)
    result["tech"] = tech_signal.normalized_score
    logger.info(f"    Tech score: {tech_signal.normalized_score}/100")

    # Patents
    logger.info(f"  [Patents] Searching USPTO for {info['assignee']}...")
    patent_collector = PatentSignalCollector()
    patents = patent_collector.search_patents(assignee_name=info["assignee"], max_results=50)
    patent_signal = patent_collector.analyze_patents(company_id=company_id, patents=patents)
    insert_signal(db, company_id=company_id, category=patent_signal.category.value,
                  source=patent_signal.source.value, signal_date=patent_signal.signal_date,
                  raw_value=patent_signal.raw_value, normalized_score=patent_signal.normalized_score,
                  confidence=patent_signal.confidence, metadata=patent_signal.metadata)
    result["patent"] = patent_signal.normalized_score
    logger.info(f"    Patent score: {patent_signal.normalized_score}/100")

    # Summary
    upsert_signal_summary(
        db, company_id=company_id, ticker=ticker,
        hiring_score=job_signal.normalized_score,
        innovation_score=patent_signal.normalized_score,
        digital_score=tech_signal.normalized_score,
        leadership_score=0.0, signal_count=3,
    )

    return result


def collect_cs3_signals(ticker: str, company_id: str, db) -> dict:
    """Collect CS3-only signals: Glassdoor reviews + board composition."""
    result = {}

    # Glassdoor
    logger.info(f"  [Glassdoor] Fetching reviews for {ticker}...")
    gd = GlassdoorCultureCollector()
    reviews = gd.fetch_reviews(ticker, limit=50)
    culture = gd.analyze_reviews(company_id, ticker, reviews)
    result["glassdoor"] = {
        "review_count": culture.review_count,
        "overall_score": float(culture.overall_score),
        "innovation": float(culture.innovation_score),
        "data_driven": float(culture.data_driven_score),
        "ai_awareness": float(culture.ai_awareness_score),
        "change_readiness": float(culture.change_readiness_score),
        "avg_rating": float(culture.avg_rating),
        "confidence": float(culture.confidence),
    }

    # Store as signal in Snowflake
    insert_signal(
        db, company_id=company_id, category="leadership_signals",
        source="glassdoor", signal_date=datetime.now(timezone.utc),
        raw_value=f"{culture.review_count} reviews, overall={culture.overall_score}",
        normalized_score=float(culture.overall_score),
        confidence=float(culture.confidence),
        metadata=result["glassdoor"],
    )
    logger.info(f"    Glassdoor: {culture.review_count} reviews, score={culture.overall_score}/100")

    # Board composition
    logger.info(f"  [Board] Fetching board data for {ticker}...")
    ba = BoardCompositionAnalyzer()
    members, committees, strategy = ba.fetch_board_data(ticker)
    governance = ba.analyze_board(company_id, ticker, members, committees, strategy)
    result["board"] = {
        "governance_score": float(governance.governance_score),
        "has_tech_committee": governance.has_tech_committee,
        "has_ai_expertise": governance.has_ai_expertise,
        "has_data_officer": governance.has_data_officer,
        "ai_experts": governance.ai_experts,
        "confidence": float(governance.confidence),
    }

    insert_signal(
        db, company_id=company_id, category="leadership_signals",
        source="company_website", signal_date=datetime.now(timezone.utc),
        raw_value=f"Governance score={governance.governance_score}",
        normalized_score=float(governance.governance_score),
        confidence=float(governance.confidence),
        metadata=result["board"],
    )
    logger.info(f"    Board: governance={governance.governance_score}/100, "
                f"AI experts: {governance.ai_experts}")

    return result


def main(companies: list[str], skip_sec: bool = False, cs3_only: bool = False):
    ensure_dirs()
    db = get_script_db()
    logger.info("Connected to Snowflake")

    # Seed new companies
    seed_cs3_companies(db)

    all_results = {}

    try:
        for ticker in companies:
            if ticker not in CS3_COMPANIES:
                logger.warning(f"Unknown ticker: {ticker}")
                continue

            logger.info(f"\n{'='*60}")
            logger.info(f"  {ticker} — {CS3_COMPANIES[ticker]['name']}")
            logger.info(f"{'='*60}")

            company_row = get_company_by_ticker(db, ticker)
            if not company_row:
                logger.error(f"  {ticker} not found in Snowflake!")
                continue

            company_id = company_row.id
            result = {"ticker": ticker, "company_id": company_id}

            if not cs3_only:
                # Only run CS2 pipeline for NEW companies (JPM/WMT already have data)
                if ticker in NEW_CS3_TICKERS:
                    if not skip_sec:
                        doc_stats = collect_sec_documents(ticker, company_id, db)
                        result["documents"] = doc_stats
                    cs2_signals = collect_cs2_signals(ticker, company_id, db)
                    result["cs2_signals"] = cs2_signals
                else:
                    logger.info(f"  Skipping CS2 pipeline for {ticker} (already has data)")

            # CS3 signals for ALL 5 companies
            cs3_signals = collect_cs3_signals(ticker, company_id, db)
            result["cs3_signals"] = cs3_signals

            all_results[ticker] = result

            logger.info(f"  Evidence collection complete for {ticker}")

            time.sleep(2)

        # Summary
        logger.info(f"\n{'='*60}")
        logger.info("CS3 EVIDENCE COLLECTION COMPLETE")
        logger.info(f"{'='*60}")
        for ticker, r in all_results.items():
            cs3 = r.get("cs3_signals", {})
            gd = cs3.get("glassdoor", {})
            bd = cs3.get("board", {})
            logger.info(
                f"  {ticker}: Glassdoor={gd.get('overall_score', 'N/A')}/100 "
                f"({gd.get('review_count', 0)} reviews) | "
                f"Board={bd.get('governance_score', 'N/A')}/100"
            )

    finally:
        db.close()
        logger.info("Snowflake session closed.")

    return all_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CS3 evidence collection")
    parser.add_argument("--companies", default="all", help="Comma-separated tickers or 'all'")
    parser.add_argument("--skip-sec", action="store_true", help="Skip SEC EDGAR download")
    parser.add_argument("--cs3-only", action="store_true",
                        help="Only collect CS3 signals (Glassdoor + Board), skip CS2 pipeline")
    args = parser.parse_args()

    if args.companies == "all":
        tickers = list(CS3_COMPANIES.keys())
    else:
        tickers = [t.strip().upper() for t in args.companies.split(",")]

    main(tickers, skip_sec=args.skip_sec, cs3_only=args.cs3_only)
