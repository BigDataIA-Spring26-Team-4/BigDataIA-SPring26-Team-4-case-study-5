#!/usr/bin/env python
"""
Re-chunk all 10-K filings with the fixed section parser.

The CS2 chunking stored only TOC snippets (19-36 words per section)
because _extract_sections found the TOC occurrence first. The fixed
parser now finds ALL occurrences and keeps the longest (real body).

This script:
1. Reads raw 10-K files from disk
2. Re-parses with the fixed DocumentParser
3. Deletes old chunks from Snowflake for each document
4. Inserts new properly-extracted chunks

Usage:
    poetry run python -m scripts.rechunk_filings
    poetry run python -m scripts.rechunk_filings --ticker NVDA
"""

import argparse
import logging
from pathlib import Path

from app.pipelines.document_parser import DocumentParser, SemanticChunker
from app.services.snowflake import (
    get_script_db, get_company_by_ticker,
    list_documents_db, insert_chunks,
    DocumentChunkRow,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

CS3_TICKERS = ["NVDA", "JPM", "WMT", "GE", "DG"]
RAW_DIR = Path("data/raw/sec/sec-edgar-filings")


def rechunk_company(ticker: str, db):
    company = get_company_by_ticker(db, ticker)
    if not company:
        logger.error(f"{ticker} not found")
        return

    docs = list_documents_db(db, company_id=company.id, filing_type="10-K")
    logger.info(f"  {len(docs)} 10-K documents in Snowflake")

    filing_dir = RAW_DIR / ticker / "10-K"
    if not filing_dir.exists():
        logger.warning(f"  No raw 10-K files for {ticker}")
        return

    parser = DocumentParser()
    chunker = SemanticChunker(chunk_size=1000, chunk_overlap=100, min_chunk_size=200)

    # Map accession numbers to document IDs
    acc_dirs = {d.name: d for d in filing_dir.iterdir() if d.is_dir()}

    rechunked = 0
    for doc_row in docs:
        # Find the raw file for this document
        # The local_path or source_path might help, but let's match by content_hash
        # or just iterate through accession dirs
        raw_file = None
        for acc_name, acc_dir in acc_dirs.items():
            candidate = acc_dir / "full-submission.txt"
            if candidate.exists():
                # Check if this accession matches the document
                # Simple heuristic: match by checking if accession is in local_path
                local = doc_row.local_path or ""
                if acc_name in local:
                    raw_file = candidate
                    break

        if not raw_file:
            # Try matching by order (most recent first)
            continue

        logger.info(f"  Re-parsing {raw_file.parent.name}...")

        try:
            doc = parser.parse_filing(raw_file, ticker)

            if not doc.sections:
                logger.warning(f"    No sections found, skipping")
                continue

            chunks = chunker.chunk_document(doc)
            total_words = sum(c.word_count for c in chunks)

            if total_words < 100:
                logger.warning(f"    Only {total_words} words in chunks, skipping")
                continue

            # Delete old chunks
            old_chunks = (
                db.query(DocumentChunkRow)
                .filter(DocumentChunkRow.document_id == doc_row.id)
                .all()
            )
            old_count = len(old_chunks)
            for oc in old_chunks:
                db.delete(oc)
            db.commit()

            # Insert new chunks
            new_count = insert_chunks(db, document_id=doc_row.id, chunks=chunks)

            # Update document word count and chunk count
            doc_row.word_count = doc.word_count
            doc_row.chunk_count = new_count
            db.commit()

            logger.info(
                f"    Replaced {old_count} old chunks with {new_count} new chunks "
                f"({total_words} words across {len(doc.sections)} sections)"
            )
            rechunked += 1

        except Exception as e:
            logger.error(f"    Failed: {e}")

    # For documents we couldn't match by path, try a second pass matching by order
    if rechunked < len(docs):
        unmatched_docs = []
        matched_accs = set()

        for doc_row in docs:
            local = doc_row.local_path or ""
            matched = False
            for acc_name in acc_dirs:
                if acc_name in local:
                    matched = True
                    matched_accs.add(acc_name)
                    break
            if not matched:
                unmatched_docs.append(doc_row)

        unmatched_accs = sorted(
            [a for a in acc_dirs if a not in matched_accs], reverse=True
        )

        for doc_row, acc_name in zip(unmatched_docs, unmatched_accs):
            raw_file = acc_dirs[acc_name] / "full-submission.txt"
            if not raw_file.exists():
                continue

            logger.info(f"  Re-parsing {acc_name} (matched by order)...")
            try:
                doc = parser.parse_filing(raw_file, ticker)
                if not doc.sections:
                    continue

                chunks = chunker.chunk_document(doc)
                if sum(c.word_count for c in chunks) < 100:
                    continue

                old_chunks = (
                    db.query(DocumentChunkRow)
                    .filter(DocumentChunkRow.document_id == doc_row.id)
                    .all()
                )
                for oc in old_chunks:
                    db.delete(oc)
                db.commit()

                new_count = insert_chunks(db, document_id=doc_row.id, chunks=chunks)
                doc_row.chunk_count = new_count
                db.commit()

                total_words = sum(c.word_count for c in chunks)
                logger.info(f"    {new_count} chunks ({total_words} words)")
                rechunked += 1

            except Exception as e:
                logger.error(f"    Failed: {e}")

    logger.info(f"  Re-chunked {rechunked}/{len(docs)} documents for {ticker}")


def main(tickers: list):
    db = get_script_db()

    logger.info("=" * 60)
    logger.info("RE-CHUNKING 10-K FILINGS WITH FIXED PARSER")
    logger.info("=" * 60)

    for ticker in tickers:
        logger.info(f"\n{ticker}:")
        rechunk_company(ticker, db)

    db.close()
    logger.info("\nDone. Snowflake chunks are now properly extracted.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", help="Single ticker")
    args = parser.parse_args()

    if args.ticker:
        main([args.ticker.upper()])
    else:
        main(CS3_TICKERS)
