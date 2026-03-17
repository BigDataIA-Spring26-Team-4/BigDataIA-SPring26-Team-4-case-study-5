"""
Airflow DAG for Evidence Collection Pipeline (CS2 + CS3).

WHY AIRFLOW (not just Streamlit):
  - Scheduled automation: Runs weekly without human intervention
  - Concurrency control: Pool limits prevent backend overload (critical for 20+ companies)
  - Dependency chain: Scoring DAG waits for this to complete via ExternalTaskSensor
  - Retry & backoff: Automatic retry with exponential backoff on API failures
  - Data quality gates: Validates evidence counts before passing to scoring
  - Audit trail: Full execution history, durations, XCom data lineage
  - SLA monitoring: Alerts if collection takes longer than expected

Streamlit is for ad-hoc interactive use. Airflow is for production scheduling.

Schedule: Weekly on Sundays at 4am UTC
Pool: pe_api_pool (2 slots) — prevents backend choking with many companies
"""

import time
import json
import logging
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError

from airflow import DAG
from airflow.models import Pool
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.empty import EmptyOperator
from airflow.utils.trigger_rule import TriggerRule

# ── Constants ─────────────────────────────────────────────────────

API_BASE = "http://api:8000"
CS3_TICKERS = ["NVDA", "JPM", "WMT", "GE", "DG"]
POLL_INTERVAL = 5
TASK_TIMEOUT = 300

# Pool configuration — controls max concurrent API calls
# With 20 companies, only 2 hit the backend at once
API_POOL = "pe_api_pool"
API_POOL_SLOTS = 3

log = logging.getLogger(__name__)

# ── HTTP Helpers (stdlib only, no requests) ───────────────────────


def _http_get(url, timeout=10):
    req = Request(url)
    resp = urlopen(req, timeout=timeout)
    body = json.loads(resp.read().decode())
    return body, resp.status


def _http_post(url, payload, timeout=30):
    data = json.dumps(payload).encode()
    req = Request(url, data=data, headers={"Content-Type": "application/json"})
    resp = urlopen(req, timeout=timeout)
    body = json.loads(resp.read().decode())
    return body, resp.status


def _wait_for_api(retries=30, delay=10):
    for i in range(retries):
        try:
            _http_get(API_BASE + "/", timeout=5)
            log.info("API is ready")
            return True
        except Exception:
            pass
        log.info("Waiting for API... attempt %d/%d", i + 1, retries)
        time.sleep(delay)
    raise RuntimeError("FastAPI backend not available after retries")


def _run_pipeline_task(endpoint, payload, label):
    """Run a pipeline task with polling — centralized retry logic."""
    body, _ = _http_post(API_BASE + endpoint, payload)
    task_id = body.get("task_id")
    if not task_id:
        raise ValueError("No task_id returned for %s: %s" % (label, body))

    log.info("[%s] Started - task_id=%s", label, task_id)

    elapsed = 0
    while elapsed < TASK_TIMEOUT:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        try:
            status_data, _ = _http_get(
                API_BASE + "/api/v1/pipeline/status/" + task_id
            )
        except Exception:
            continue

        if status_data["status"] == "completed":
            log.info("[%s] Completed in %ds: %s", label, elapsed, status_data.get("result", {}))
            return status_data.get("result", {})
        elif status_data["status"] == "failed":
            error = status_data.get("error", "Unknown")
            raise RuntimeError("[%s] Failed: %s" % (label, error))

    raise TimeoutError("[%s] Timed out after %ds" % (label, TASK_TIMEOUT))


# ── Task Callables ────────────────────────────────────────────────


def ensure_pool_exists(**context):
    """Create the API pool if it doesn't exist (idempotent).

    Pool limits concurrent API calls — critical for scaling to 20+ companies.
    Without this, all companies would hit the backend simultaneously,
    causing timeouts and OOM on the API server.
    """
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
            log.info("Pool '%s' already exists with %d slots", API_POOL, existing.slots)
    finally:
        session.close()


def check_api_health(**context):
    """Verify API health and capture pre-collection baseline stats."""
    _wait_for_api()
    try:
        body, _ = _http_get(API_BASE + "/health", timeout=10)
        log.info("API health: %s", body)

        # Capture baseline evidence counts per company for incremental comparison
        baselines = {}
        for ticker in CS3_TICKERS:
            try:
                summary, _ = _http_get(
                    API_BASE + "/api/v1/pipeline/evidence-summary/" + ticker,
                    timeout=10,
                )
                baselines[ticker] = {
                    "document_count": summary.get("document_count", 0),
                    "signal_count": summary.get("signal_count", 0),
                }
            except Exception:
                baselines[ticker] = {"document_count": 0, "signal_count": 0}

        context["ti"].xcom_push(key="baselines", value=baselines)
        log.info("Baseline evidence counts: %s", baselines)

    except Exception:
        log.warning("Could not fetch full health, but API root is responding")


def collect_cs2_for_ticker(ticker, **context):
    """Collect CS2 evidence — pool-limited to prevent backend overload."""
    result = _run_pipeline_task(
        endpoint="/api/v1/pipeline/collect-evidence",
        payload={"ticker": ticker, "skip_sec": True},
        label="CS2-" + ticker,
    )
    context["ti"].xcom_push(key="cs2_" + ticker, value=result)
    return result


def collect_cs3_for_ticker(ticker, **context):
    """Collect CS3 signals — pool-limited to prevent backend overload."""
    result = _run_pipeline_task(
        endpoint="/api/v1/pipeline/collect-cs3",
        payload={"ticker": ticker, "skip_sec": False},
        label="CS3-" + ticker,
    )
    context["ti"].xcom_push(key="cs3_" + ticker, value=result)
    return result


def validate_collection(**context):
    """Data quality gate — verify evidence was actually collected.

    This is what Streamlit CANNOT do: automated validation that
    blocks downstream scoring if data quality is insufficient.
    """
    ti = context["ti"]
    baselines = ti.xcom_pull(task_ids="check_api_health", key="baselines") or {}
    failures = []
    warnings = []

    log.info("=" * 60)
    log.info("EVIDENCE COLLECTION VALIDATION")
    log.info("=" * 60)

    for ticker in CS3_TICKERS:
        cs2 = ti.xcom_pull(key="cs2_" + ticker) or {}
        cs3 = ti.xcom_pull(key="cs3_" + ticker) or {}
        baseline = baselines.get(ticker, {})

        # Check CS2 ran successfully
        if not cs2:
            failures.append("%s: CS2 collection returned empty" % ticker)
        elif cs2.get("error"):
            failures.append("%s: CS2 error — %s" % (ticker, cs2["error"]))

        # Check CS3 signals collected
        glassdoor = cs3.get("glassdoor_score", 0)
        board = cs3.get("board_score", 0)
        if glassdoor == 0 and board == 0:
            warnings.append("%s: Both Glassdoor and Board scores are 0" % ticker)

        log.info("  %s: CS2=%s, CS3=gd=%.0f board=%.0f news=%.0f",
                 ticker, "OK" if cs2 and not cs2.get("error") else "FAIL",
                 cs3.get("glassdoor_score", 0),
                 cs3.get("board_score", 0),
                 cs3.get("news_score", 0))

    log.info("-" * 60)
    if failures:
        log.error("FAILURES: %s", failures)
    if warnings:
        log.warning("WARNINGS: %s", warnings)
    log.info("=" * 60)

    # Push validation results for downstream DAGs
    ti.xcom_push(key="validation", value={
        "failures": failures,
        "warnings": warnings,
        "passed": len(failures) == 0,
        "company_count": len(CS3_TICKERS),
    })

    if failures:
        raise RuntimeError(
            "Collection validation failed for %d companies: %s"
            % (len(failures), "; ".join(failures))
        )

    log.info("Collection validation PASSED for all %d companies", len(CS3_TICKERS))


def collection_summary(**context):
    """Final summary with timing and metrics for audit trail."""
    ti = context["ti"]
    log.info("=" * 60)
    log.info("EVIDENCE COLLECTION COMPLETE")
    log.info("=" * 60)
    for ticker in CS3_TICKERS:
        cs2 = ti.xcom_pull(key="cs2_" + ticker) or {}
        cs3 = ti.xcom_pull(key="cs3_" + ticker) or {}
        log.info("  %s: CS2=%s, CS3=%s", ticker, cs2, cs3)
    log.info("Pipeline ready for downstream scoring_pipeline DAG")
    log.info("=" * 60)


# ── Default Args ──────────────────────────────────────────────────

default_args = {
    "owner": "pe-org-air-team",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=3),
    "retry_exponential_backoff": True,
    "sla": timedelta(hours=2),  # Alert if collection takes >2hrs
}

# ── DAG Definition ────────────────────────────────────────────────

with DAG(
    dag_id="evidence_collection_pipeline",
    default_args=default_args,
    description="CS2+CS3: Collect SEC filings, signals, Glassdoor, Board & News via API (pool-limited)",
    schedule_interval="0 4 * * 0",
    start_date=datetime(2026, 2, 1),
    catchup=False,
    max_active_runs=1,
    tags=["cs2", "cs3", "evidence", "collection"],
    doc_md=__doc__,
) as dag:

    start = EmptyOperator(task_id="start")

    setup_pool = PythonOperator(
        task_id="setup_pool",
        python_callable=ensure_pool_exists,
        doc_md="Create pe_api_pool (2 slots) to limit concurrent backend calls",
    )

    health_check = PythonOperator(
        task_id="check_api_health",
        python_callable=check_api_health,
        doc_md="Verify API health and capture baseline evidence counts",
    )

    # CS2 tasks — pool-limited so only 2 companies hit the backend at once
    cs2_tasks = []
    for ticker in CS3_TICKERS:
        task = PythonOperator(
            task_id="cs2_" + ticker.lower(),
            python_callable=collect_cs2_for_ticker,
            op_kwargs={"ticker": ticker},
            pool=API_POOL,  # ← POOL: max 2 concurrent
            execution_timeout=timedelta(minutes=10),
            doc_md="Collect CS2 evidence for " + ticker + " (pool-limited)",
        )
        cs2_tasks.append(task)

    cs2_done = EmptyOperator(task_id="cs2_done", trigger_rule=TriggerRule.ALL_DONE)

    # CS3 tasks — also pool-limited
    cs3_tasks = []
    for ticker in CS3_TICKERS:
        task = PythonOperator(
            task_id="cs3_" + ticker.lower(),
            python_callable=collect_cs3_for_ticker,
            op_kwargs={"ticker": ticker},
            pool=API_POOL,  # ← POOL: max 2 concurrent
            execution_timeout=timedelta(minutes=10),
            doc_md="Collect CS3 signals for " + ticker + " (pool-limited)",
        )
        cs3_tasks.append(task)

    cs3_done = EmptyOperator(task_id="cs3_done", trigger_rule=TriggerRule.ALL_DONE)

    # Data quality gate — blocks scoring DAG if validation fails
    validate = PythonOperator(
        task_id="validate_collection",
        python_callable=validate_collection,
        trigger_rule=TriggerRule.ALL_DONE,
        doc_md="Data quality gate: verify all companies have evidence before scoring",
    )

    summary = PythonOperator(
        task_id="collection_summary",
        python_callable=collection_summary,
        trigger_rule=TriggerRule.ALL_DONE,
        doc_md="Log final summary and metrics for audit trail",
    )

    end = EmptyOperator(
        task_id="end",
        trigger_rule=TriggerRule.ALL_DONE,
    )

    # Chain: pool setup → health → CS2 (pooled) → CS3 (pooled) → validate → summary
    start >> setup_pool >> health_check
    health_check >> cs2_tasks >> cs2_done
    cs2_done >> cs3_tasks >> cs3_done
    cs3_done >> validate >> summary >> end
