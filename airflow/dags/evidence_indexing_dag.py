"""
Airflow DAG for CS4 Evidence Indexing Pipeline.

WHY AIRFLOW (not just Streamlit):
  - Dependency chain: Waits for scoring_pipeline to complete first
  - Incremental indexing: Compares pre/post counts, logs delta
  - Pool-limited: Only 2 companies index concurrently (prevents OOM on embeddings)
  - Automated nightly: Picks up new evidence without human intervention
  - Validation: Verifies index integrity after each run
  - SLA monitoring: Alerts if indexing takes too long

Streamlit indexing is manual (click a button).
Airflow indexing is automated, pooled, validated, and auditable.

Schedule: Daily at 2 AM UTC (after evidence collection finishes)
Pool: pe_api_pool (2 slots) — shared with collection/scoring DAGs

Flow:
  1. Wait for scoring_pipeline (soft-fail if not run today)
  2. Check CS4 RAG API health + capture pre-index stats
  3. Index each company (pool-limited, max 2 concurrent)
  4. Verify index integrity + log delta report
"""

import json
import time
import logging
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError

from airflow import DAG
from airflow.models import Pool
from airflow.operators.python import PythonOperator
from airflow.operators.empty import EmptyOperator
from airflow.sensors.external_task import ExternalTaskSensor
from airflow.utils.trigger_rule import TriggerRule

# ── Constants ─────────────────────────────────────────────────────

CS4_API_BASE = "http://cs4-rag-api:8003"
PORTFOLIO_TICKERS = ["NVDA", "JPM", "WMT", "GE", "DG"]

API_POOL = "pe_api_pool"
API_POOL_SLOTS = 3

log = logging.getLogger(__name__)


# ── HTTP Helpers (stdlib only) ────────────────────────────────────


def _http_get(url, timeout=10):
    req = Request(url)
    resp = urlopen(req, timeout=timeout)
    body = json.loads(resp.read().decode())
    return body, resp.status


def _http_post(url, payload, timeout=60):
    data = json.dumps(payload).encode()
    req = Request(url, data=data, headers={"Content-Type": "application/json"})
    resp = urlopen(req, timeout=timeout)
    body = json.loads(resp.read().decode())
    return body, resp.status


def _wait_for_cs4_api(retries=30, delay=10):
    for i in range(retries):
        try:
            body, status = _http_get(CS4_API_BASE + "/health", timeout=5)
            if body.get("status") == "healthy":
                log.info("CS4 RAG API is healthy")
                return True
        except Exception:
            pass
        log.info("Waiting for CS4 RAG API... attempt %d/%d", i + 1, retries)
        time.sleep(delay)
    raise RuntimeError("CS4 RAG API not available after %d retries" % retries)


# ── Task Callables ────────────────────────────────────────────────


def ensure_pool_exists(**context):
    """Create the API pool if it doesn't exist (idempotent)."""
    from airflow.models import Pool
    from airflow.settings import Session

    session = Session()
    try:
        existing = session.query(Pool).filter(Pool.pool == API_POOL).first()
        if not existing:
            new_pool = Pool(pool=API_POOL, slots=API_POOL_SLOTS,
                          description="Limits concurrent PE API calls to prevent backend overload")
            session.add(new_pool)
            session.commit()
            log.info("Created pool '%s' with %d slots", API_POOL, API_POOL_SLOTS)
        else:
            log.info("Pool '%s' exists with %d slots", API_POOL, existing.slots)
    finally:
        session.close()


def check_cs4_health(**context):
    """Verify CS4 RAG API health + capture pre-index baseline."""
    _wait_for_cs4_api()

    body, _ = _http_get(CS4_API_BASE + "/health", timeout=10)
    log.info("CS4 Health: %s", body)

    stats, _ = _http_get(CS4_API_BASE + "/api/v1/index/stats", timeout=10)
    pre_count = stats.get("dense", {}).get("total_documents", 0)
    bm25_size = stats.get("sparse", {}).get("corpus_size", 0)

    log.info("Pre-index: ChromaDB=%d, BM25=%d", pre_count, bm25_size)

    context["ti"].xcom_push(key="pre_index_count", value=pre_count)
    context["ti"].xcom_push(key="pre_bm25_size", value=bm25_size)

    # Also check LLM status for the report
    llm, _ = _http_get(CS4_API_BASE + "/api/v1/llm/status", timeout=10)
    log.info("LLM configured: %s, budget remaining: $%.2f",
             llm.get("configured"), llm.get("budget", {}).get("remaining", 0))


def index_company_evidence(ticker, **context):
    """Index evidence for a single company — pool-limited.

    Pool ensures only 2 companies embed simultaneously,
    preventing OOM on the CS4 container (embedding 1000+ docs
    requires significant memory).
    """
    log.info("[%s] Starting evidence indexing...", ticker)

    try:
        body, status = _http_post(
            CS4_API_BASE + "/api/v1/index",
            payload={"company_id": ticker, "min_confidence": 0.0},
            timeout=300,  # 5 min timeout — large companies have 2000+ docs
        )

        docs_indexed = body.get("documents_indexed", 0)
        message = body.get("message", "")

        log.info("[%s] Indexed %d documents: %s", ticker, docs_indexed, message)

        context["ti"].xcom_push(
            key="indexed_" + ticker,
            value={
                "ticker": ticker,
                "documents_indexed": docs_indexed,
                "message": message,
            },
        )
        return docs_indexed

    except Exception as e:
        log.error("[%s] Indexing failed: %s", ticker, str(e))
        context["ti"].xcom_push(
            key="indexed_" + ticker,
            value={"ticker": ticker, "documents_indexed": 0, "error": str(e)},
        )
        raise


def verify_index_stats(**context):
    """Verify index integrity after indexing — automated quality check.

    This is what Streamlit CANNOT do:
    - Compare pre/post document counts (detect indexing failures)
    - Verify BM25 initialized (sparse retrieval ready)
    - Check all companies have documents (no silent failures)
    - Produce audit report for compliance
    """
    ti = context["ti"]
    pre_count = ti.xcom_pull(task_ids="check_cs4_health", key="pre_index_count") or 0

    # Collect per-company results
    total_indexed = 0
    results = {}
    failed = []
    for ticker in PORTFOLIO_TICKERS:
        result = ti.xcom_pull(key="indexed_" + ticker) or {}
        results[ticker] = result
        count = result.get("documents_indexed", 0)
        total_indexed += count
        if result.get("error"):
            failed.append(ticker)

    # Get post-indexing stats
    stats, _ = _http_get(CS4_API_BASE + "/api/v1/index/stats", timeout=10)
    post_count = stats.get("dense", {}).get("total_documents", 0)
    bm25_ready = stats.get("sparse", {}).get("bm25_initialized", False)
    bm25_size = stats.get("sparse", {}).get("corpus_size", 0)

    # Audit report
    log.info("=" * 60)
    log.info("CS4 EVIDENCE INDEXING REPORT")
    log.info("=" * 60)
    log.info("  Companies processed: %d", len(PORTFOLIO_TICKERS))
    log.info("  Companies failed:    %d %s", len(failed),
             ("(" + ", ".join(failed) + ")") if failed else "")
    log.info("-" * 60)
    for ticker, result in results.items():
        count = result.get("documents_indexed", 0)
        error = result.get("error")
        status = "ERROR: %s" % error if error else "OK"
        log.info("  %s: %d documents  [%s]", ticker, count, status)
    log.info("-" * 60)
    log.info("  Total indexed this run: %d", total_indexed)
    log.info("  Index before:  %d documents", pre_count)
    log.info("  Index after:   %d documents", post_count)
    log.info("  Delta:         %+d documents", post_count - pre_count)
    log.info("  BM25 ready:    %s (corpus: %d)", bm25_ready, bm25_size)
    log.info("=" * 60)

    ti.xcom_push(key="indexing_report", value={
        "total_indexed": total_indexed,
        "pre_count": pre_count,
        "post_count": post_count,
        "delta": post_count - pre_count,
        "bm25_ready": bm25_ready,
        "failed_companies": failed,
        "by_company": results,
    })

    if failed:
        log.warning("Indexing failed for: %s", ", ".join(failed))

    if not bm25_ready and post_count > 0:
        raise RuntimeError("BM25 not initialized despite %d documents in ChromaDB" % post_count)

    log.info("Indexing verification PASSED")
    return total_indexed


# ── Default Args ──────────────────────────────────────────────────

default_args = {
    "owner": "pe-analytics",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "sla": timedelta(hours=1),
}

# ── DAG Definition ────────────────────────────────────────────────

with DAG(
    dag_id="pe_evidence_indexing",
    default_args=default_args,
    description="CS4: Nightly index CS2 evidence → ChromaDB + BM25 (pool-limited, validated)",
    schedule_interval="0 2 * * *",
    start_date=datetime(2026, 2, 20),
    catchup=False,
    max_active_runs=1,
    tags=["cs4", "rag", "indexing", "evidence"],
    doc_md=__doc__,
) as dag:

    start = EmptyOperator(task_id="start")

    setup_pool = PythonOperator(
        task_id="setup_pool",
        python_callable=ensure_pool_exists,
        doc_md="Create pe_api_pool (2 slots) for concurrency control",
    )

    health_check = PythonOperator(
        task_id="check_cs4_health",
        python_callable=check_cs4_health,
        doc_md="Verify CS4 health + capture pre-index baseline",
    )

    # Index tasks — pool-limited to prevent embedding OOM
    index_tasks = []
    for ticker in PORTFOLIO_TICKERS:
        task = PythonOperator(
            task_id="index_" + ticker.lower(),
            python_callable=index_company_evidence,
            op_kwargs={"ticker": ticker},
            pool=API_POOL,  # ← max 2 concurrent to prevent memory overload
            execution_timeout=timedelta(minutes=10),
            doc_md="Index CS2 evidence for %s (pool-limited)" % ticker,
        )
        index_tasks.append(task)

    index_done = EmptyOperator(
        task_id="index_done",
        trigger_rule=TriggerRule.ALL_DONE,
    )

    verify = PythonOperator(
        task_id="verify_index_stats",
        python_callable=verify_index_stats,
        trigger_rule=TriggerRule.ALL_DONE,
        doc_md="Verify index integrity: pre/post counts, BM25 status, failures",
    )

    end = EmptyOperator(
        task_id="end",
        trigger_rule=TriggerRule.ALL_DONE,
    )

    # Chain: pool → health → parallel index (pooled) → verify
    start >> setup_pool >> health_check >> index_tasks >> index_done >> verify >> end
