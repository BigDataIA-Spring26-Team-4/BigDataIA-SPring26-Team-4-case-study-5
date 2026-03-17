#!/usr/bin/env python
"""
Initialize Snowflake database — create all tables and seed the 10 target companies.

Run this ONCE before running collect_evidence.py.

Usage:
    python -m scripts.init_db
"""

import logging
from pathlib import Path

from sqlalchemy import text

from app.services.snowflake import engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

SCHEMA_FILE = Path("app/database/schema.sql")


def run():
    logger.info("Reading schema file...")
    sql = SCHEMA_FILE.read_text(encoding="utf-8")

    # Split into individual statements (Snowflake needs them one at a time)
    statements = []
    for stmt in sql.split(";"):
        stmt = stmt.strip()
        # Skip empty lines and pure comments
        if not stmt:
            continue
        # Skip lines that are only comments
        lines = [l for l in stmt.splitlines() if l.strip() and not l.strip().startswith("--")]
        if not lines:
            continue
        statements.append(stmt)

    logger.info(f"Found {len(statements)} SQL statements to execute.")

    with engine.connect() as conn:
        for i, stmt in enumerate(statements, 1):
            # Show first 80 chars of each statement for progress
            preview = stmt.replace("\n", " ")[:80]
            try:
                conn.execute(text(stmt))
                conn.commit()
                logger.info(f"  [{i}/{len(statements)}] OK: {preview}...")
            except Exception as e:
                # Some statements may fail if objects already exist — that's fine
                err = str(e)
                if "already exists" in err.lower():
                    logger.info(f"  [{i}/{len(statements)}] SKIP (already exists): {preview}...")
                else:
                    logger.warning(f"  [{i}/{len(statements)}] WARN: {preview}... → {err[:120]}")

    # Verify seed data
    with engine.connect() as conn:
        result = conn.execute(text("SELECT ticker, name FROM companies ORDER BY ticker"))
        rows = result.fetchall()
        logger.info(f"\nCompanies in database: {len(rows)}")
        for r in rows:
            logger.info(f"  {r[0]:<6} {r[1]}")

        result = conn.execute(text("SELECT name, sector FROM industries ORDER BY name"))
        rows = result.fetchall()
        logger.info(f"\nIndustries in database: {len(rows)}")
        for r in rows:
            logger.info(f"  {r[0]:<25} ({r[1]})")

    logger.info("\nDone! Database is ready.")


if __name__ == "__main__":
    run()
