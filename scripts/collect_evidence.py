#!/usr/bin/env python
"""
Collect evidence for all target companies and persist to Snowflake.

This script:
1. Downloads SEC filings (10-K, 10-Q, 8-K) from EDGAR → parses → chunks
2. Scrapes job postings (python-jobspy / Indeed)
3. Queries USPTO PatentsView API for patents
4. Loads known tech stacks for target companies
5. Stores EVERYTHING in Snowflake (documents, chunks, signals, summaries)
6. Saves local JSON cache in data/signals/

Usage:
    python -m scripts.collect_evidence --companies all
    python -m scripts.collect_evidence --companies CAT,DE,UNH
    python -m scripts.collect_evidence --companies JPM --skip-sec
    python -m scripts.collect_evidence --companies all --signals-only
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
from app.services.snowflake import (
    get_company_by_ticker,
    get_script_db,
    insert_chunks,
    insert_document,
    insert_signal,
    upsert_signal_summary,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

TARGET_COMPANIES = {
    "CAT": {"name": "Caterpillar Inc.", "sector": "Manufacturing", "assignee": "Caterpillar"},
    "DE": {"name": "Deere & Company", "sector": "Manufacturing", "assignee": "Deere"},
    "UNH": {"name": "UnitedHealth Group", "sector": "Healthcare", "assignee": "UnitedHealth"},
    "HCA": {"name": "HCA Healthcare", "sector": "Healthcare", "assignee": "HCA"},
    "ADP": {"name": "Automatic Data Processing", "sector": "Services", "assignee": "Automatic Data Processing"},
    "PAYX": {"name": "Paychex Inc.", "sector": "Services", "assignee": "Paychex"},
    "WMT": {"name": "Walmart Inc.", "sector": "Retail", "assignee": "Walmart"},
    "TGT": {"name": "Target Corporation", "sector": "Retail", "assignee": "Target"},
    "JPM": {"name": "JPMorgan Chase", "sector": "Financial", "assignee": "JPMorgan"},
    "GS": {"name": "Goldman Sachs", "sector": "Financial", "assignee": "Goldman Sachs"},
}

# Output directories
DATA_DIR = Path("data")
SIGNALS_DIR = DATA_DIR / "signals"
SAMPLES_DIR = DATA_DIR / "samples"


def ensure_dirs():
    for d in [DATA_DIR / "raw", DATA_DIR / "processed", SIGNALS_DIR, SAMPLES_DIR]:
        d.mkdir(parents=True, exist_ok=True)


# ────────────────────────────────────────────────────────────────────────
# SEC Documents → Snowflake
# ────────────────────────────────────────────────────────────────────────


def collect_documents(ticker: str, company_id: str, db) -> dict:
    """Download SEC filings, parse, chunk, store in Snowflake."""
    logger.info(f"=== SEC EDGAR: {ticker} ===")

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
    logger.info(f"  Downloaded {len(filings)} filings for {ticker}")

    stats = {"10-K": 0, "10-Q": 0, "8-K": 0, "total": 0, "chunks": 0, "errors": 0}

    for filing_path in filings:
        try:
            doc = parser.parse_filing(filing_path, ticker)
            chunks = chunker.chunk_document(doc)

            # ── Store document in Snowflake ──
            doc_row = insert_document(
                db,
                company_id=company_id,
                ticker=ticker,
                filing_type=doc.filing_type,
                filing_date=doc.filing_date,
                content_hash=doc.content_hash,
                word_count=doc.word_count,
                chunk_count=len(chunks),
                source_path=doc.source_path,
                status="chunked",
            )

            # ── Store chunks in Snowflake ──
            insert_chunks(db, document_id=doc_row.id, chunks=chunks)

            stats["total"] += 1
            stats["chunks"] += len(chunks)
            ft = doc.filing_type
            if ft in stats:
                stats[ft] += 1

            logger.info(
                f"  ✓ {doc.filing_type} | words={doc.word_count:,} | "
                f"chunks={len(chunks)} → Snowflake"
            )
        except Exception as e:
            stats["errors"] += 1
            logger.error(f"  ✗ Failed {filing_path}: {e}")

    return stats


# ────────────────────────────────────────────────────────────────────────
# External Signals → Snowflake
# ────────────────────────────────────────────────────────────────────────


def collect_signals(ticker: str, company_id: str, db) -> dict:
    """Collect job, tech, patent signals and store in Snowflake."""
    logger.info(f"=== SIGNALS: {ticker} ===")
    info = TARGET_COMPANIES[ticker]
    result = {}

    # ── 1. Job Postings (python-jobspy → Indeed) ─────────────────
    logger.info(f"  [1/3] Scraping job postings for {info['name']}...")
    job_collector = JobSignalCollector()
    postings = job_collector.scrape_jobs(info["name"], max_results=25)
    postings = [job_collector.classify_posting(p) for p in postings]

    job_signal = job_collector.analyze_job_postings(
        company_id=company_id, company=info["name"], postings=postings,
    )

    insert_signal(
        db,
        company_id=company_id,
        category=job_signal.category.value,
        source=job_signal.source.value,
        signal_date=job_signal.signal_date,
        raw_value=job_signal.raw_value,
        normalized_score=job_signal.normalized_score,
        confidence=job_signal.confidence,
        metadata=job_signal.metadata,
    )
    result["hiring"] = job_signal.normalized_score
    logger.info(f"  Hiring: {job_signal.normalized_score}/100 ({job_signal.raw_value}) → Snowflake")
    time.sleep(1)

    # ── 2. Tech Stack (research-based known data) ────────────────
    logger.info(f"  [2/3] Loading tech stack for {ticker}...")
    tech_collector = TechStackCollector()
    technologies = tech_collector.get_known_technologies(ticker)
    tech_signal = tech_collector.analyze_tech_stack(
        company_id=company_id, technologies=technologies,
    )

    insert_signal(
        db,
        company_id=company_id,
        category=tech_signal.category.value,
        source=tech_signal.source.value,
        signal_date=tech_signal.signal_date,
        raw_value=tech_signal.raw_value,
        normalized_score=tech_signal.normalized_score,
        confidence=tech_signal.confidence,
        metadata=tech_signal.metadata,
    )
    result["tech"] = tech_signal.normalized_score
    logger.info(f"  Tech:   {tech_signal.normalized_score}/100 ({tech_signal.raw_value}) → Snowflake")

    # ── 3. Patents (USPTO PatentsView API) ───────────────────────
    logger.info(f"  [3/3] Searching USPTO patents for {info['assignee']}...")
    patent_collector = PatentSignalCollector()
    patents = patent_collector.search_patents(
        assignee_name=info["assignee"], max_results=50, years_back=5,
    )
    patent_signal = patent_collector.analyze_patents(
        company_id=company_id, patents=patents,
    )

    insert_signal(
        db,
        company_id=company_id,
        category=patent_signal.category.value,
        source=patent_signal.source.value,
        signal_date=patent_signal.signal_date,
        raw_value=patent_signal.raw_value,
        normalized_score=patent_signal.normalized_score,
        confidence=patent_signal.confidence,
        metadata=patent_signal.metadata,
    )
    result["patent"] = patent_signal.normalized_score
    logger.info(f"  Patent: {patent_signal.normalized_score}/100 ({patent_signal.raw_value}) → Snowflake")

    # ── 4. Upsert signal summary in Snowflake ────────────────────
    upsert_signal_summary(
        db,
        company_id=company_id,
        ticker=ticker,
        hiring_score=job_signal.normalized_score,
        innovation_score=patent_signal.normalized_score,
        digital_score=tech_signal.normalized_score,
        leadership_score=0.0,  # Not yet collected
        signal_count=3,
    )

    composite = (
        0.30 * job_signal.normalized_score
        + 0.25 * patent_signal.normalized_score
        + 0.25 * tech_signal.normalized_score
        + 0.20 * 0.0
    )
    result["composite"] = round(composite, 1)
    logger.info(f"  Composite: {result['composite']}/100 → Snowflake summary")

    # ── Save local JSON cache ────────────────────────────────────
    signal_file = SIGNALS_DIR / f"signals_{ticker}.json"
    with open(signal_file, "w") as f:
        json.dump(result, f, indent=2, default=str)

    return result


# ────────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────────


def main(companies: list[str], skip_sec: bool = False, signals_only: bool = False):
    ensure_dirs()

    # ── Open ONE Snowflake session for the entire run ────────────
    logger.info("Connecting to Snowflake...")
    db = get_script_db()
    logger.info("Connected to Snowflake ✓")

    stats = {"companies": 0, "documents": 0, "chunks": 0, "signals": 0, "errors": 0}
    all_signals = {}

    try:
        for ticker in companies:
            if ticker not in TARGET_COMPANIES:
                logger.warning(f"Unknown ticker: {ticker}")
                continue

            logger.info(f"\n{'='*60}")
            logger.info(f"PROCESSING: {ticker} — {TARGET_COMPANIES[ticker]['name']}")
            logger.info(f"{'='*60}")

            # ── Look up the company row in Snowflake ─────────────
            company_row = get_company_by_ticker(db, ticker)
            if not company_row:
                logger.error(
                    f"  Company {ticker} not found in Snowflake! "
                    f"Run the schema.sql seed data first."
                )
                stats["errors"] += 1
                continue

            company_id = company_row.id
            logger.info(f"  Company ID: {company_id}")

            try:
                # ── SEC Documents ─────────────────────────────────
                if not skip_sec and not signals_only:
                    doc_stats = collect_documents(ticker, company_id, db)
                    stats["documents"] += doc_stats["total"]
                    stats["chunks"] += doc_stats["chunks"]
                else:
                    logger.info(f"  Skipping SEC download for {ticker}")

                # ── External Signals ──────────────────────────────
                sig_result = collect_signals(ticker, company_id, db)
                stats["signals"] += 3
                all_signals[ticker] = sig_result

                stats["companies"] += 1

                # Delay between companies
                logger.info("  Waiting 3s before next company...")
                time.sleep(3)

            except Exception as e:
                logger.error(f"  Failed to process {ticker}: {e}")
                stats["errors"] += 1

        # ── Save combined summary ────────────────────────────────
        summary_file = SIGNALS_DIR / "signal_summary_all.json"
        with open(summary_file, "w") as f:
            json.dump(all_signals, f, indent=2, default=str)

        # ── Print final table ────────────────────────────────────
        logger.info(f"\n{'='*80}")
        logger.info("COLLECTION COMPLETE — ALL DATA STORED IN SNOWFLAKE")
        logger.info(f"{'='*80}")
        logger.info(f"Companies: {stats['companies']}  |  Documents: {stats['documents']}  |  "
                     f"Chunks: {stats['chunks']}  |  Signals: {stats['signals']}  |  Errors: {stats['errors']}")
        logger.info("")
        logger.info(f"{'Ticker':<8} {'Hiring':>8} {'Patent':>8} {'Tech':>8} {'Composite':>10}")
        logger.info(f"{'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*10}")
        for t, s in all_signals.items():
            logger.info(
                f"{t:<8} {s.get('hiring',0):>8.1f} {s.get('patent',0):>8.1f} "
                f"{s.get('tech',0):>8.1f} {s.get('composite',0):>10.1f}"
            )

    finally:
        db.close()
        logger.info("Snowflake session closed.")

    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect evidence for target companies")
    parser.add_argument("--companies", default="all", help="Comma-separated tickers or 'all'")
    parser.add_argument("--skip-sec", action="store_true", help="Skip SEC EDGAR download")
    parser.add_argument("--signals-only", action="store_true", help="Only collect external signals")
    args = parser.parse_args()

    if args.companies == "all":
        companies = list(TARGET_COMPANIES.keys())
    else:
        companies = [t.strip().upper() for t in args.companies.split(",")]

    main(companies, skip_sec=args.skip_sec, signals_only=args.signals_only)
