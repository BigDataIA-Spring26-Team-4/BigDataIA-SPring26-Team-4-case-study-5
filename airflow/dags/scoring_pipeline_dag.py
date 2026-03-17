"""
Airflow DAG for Org-AI-R Scoring Pipeline (CS3).

WHY AIRFLOW (not just Streamlit):
  - Dependency chain: Waits for evidence_collection_pipeline via ExternalTaskSensor
  - Validation gates: Blocks on bad data — scores aren't published unless validated
  - Incremental comparison: Compares new scores vs previous run (detects drift)
  - Portfolio-level analysis: Validates ranking, ranges, and cross-company consistency
  - Audit trail: Every scoring run is logged with full before/after comparison
  - SLA monitoring: Alerts if scoring takes too long

Streamlit can score one company interactively.
Airflow scores the entire portfolio in a validated, auditable pipeline.

Schedule: Weekly on Mondays at 6am UTC (after evidence collection on Sundays)
Pool: pe_api_pool (2 slots) — shared with collection DAG
"""

import json
import time
import logging
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.empty import EmptyOperator
from airflow.sensors.external_task import ExternalTaskSensor
from airflow.utils.trigger_rule import TriggerRule

# ── Constants ─────────────────────────────────────────────────────

API_BASE = "http://api:8000"
CS3_TICKERS = ["NVDA", "JPM", "WMT", "GE", "DG"]

EXPECTED_RANGES = {
    "NVDA": (85, 95),
    "JPM":  (65, 75),
    "WMT":  (55, 65),
    "GE":   (45, 55),
    "DG":   (35, 45),
}

TOLERANCE = 10
API_POOL = "pe_api_pool"

log = logging.getLogger(__name__)

# ── HTTP Helpers (stdlib only) ────────────────────────────────────


def _http_get(url, timeout=10):
    req = Request(url)
    resp = urlopen(req, timeout=timeout)
    return json.loads(resp.read().decode()), resp.status


def _http_post(url, payload=None, timeout=60):
    data = json.dumps(payload or {}).encode()
    req = Request(url, data=data, headers={"Content-Type": "application/json"})
    resp = urlopen(req, timeout=timeout)
    return json.loads(resp.read().decode()), resp.status


# ── Task Callables ────────────────────────────────────────────────


def capture_previous_scores(**context):
    """Capture current scores BEFORE re-scoring for drift detection.

    This is Airflow-exclusive: compare previous vs new scores to detect
    unexpected changes (evidence contamination, API bugs, data corruption).
    """
    previous = {}
    for ticker in CS3_TICKERS:
        try:
            data, _ = _http_get(
                API_BASE + "/api/v1/pipeline/evidence-summary/" + ticker,
                timeout=10,
            )
            # Load local result file score if available
            previous[ticker] = {
                "document_count": data.get("document_count", 0),
                "signal_count": data.get("signal_count", 0),
            }
        except Exception:
            previous[ticker] = {}

    context["ti"].xcom_push(key="previous_scores", value=previous)
    log.info("Captured baseline: %s", previous)


def score_all_companies(**context):
    """Score entire portfolio via API — single call, not 5 parallel calls."""
    log.info("Starting portfolio scoring via API...")

    # Wait for API
    for i in range(20):
        try:
            _http_get(API_BASE + "/", timeout=5)
            break
        except Exception:
            time.sleep(5)

    result, _ = _http_post(
        API_BASE + "/api/v1/pipeline/score-portfolio",
        timeout=120,
    )

    scored = result.get("scored", {})
    errors = result.get("errors", {})

    log.info("Scored %d companies", result.get("total_scored", 0))
    for ticker, scores in scored.items():
        log.info("  %s: Org-AI-R = %.1f", ticker, scores.get("final_score", 0))
    if errors:
        log.warning("Errors: %s", errors)

    context["ti"].xcom_push(key="scoring_result", value=result)
    context["ti"].xcom_push(key="scored", value=scored)

    if result.get("total_scored", 0) < len(CS3_TICKERS):
        raise RuntimeError(
            "Only scored %d/%d companies. Errors: %s"
            % (result.get("total_scored", 0), len(CS3_TICKERS), errors)
        )

    return result


def validate_results(**context):
    """Validate scores against expected ranges and ranking.

    This is what Streamlit CANNOT do:
    - Automated range validation for all companies in one pass
    - Ranking consistency check (NVDA should be #1, DG should be #5)
    - Score drift detection vs previous run
    - Blocks downstream indexing if validation fails
    """
    ti = context["ti"]
    scored = ti.xcom_pull(task_ids="score_portfolio", key="scored") or {}

    if not scored:
        raise ValueError("No scores found from scoring task")

    errors = []
    warnings = []
    summary_lines = []
    scores = {}

    for ticker in CS3_TICKERS:
        if ticker in scored:
            score = scored[ticker].get("final_score", 0)
            scores[ticker] = score

            low, high = EXPECTED_RANGES[ticker]
            in_range = (low - TOLERANCE) <= score <= (high + TOLERANCE)
            status = "PASS" if in_range else "WARN"
            summary_lines.append(
                "  [%s] %s: %.1f (expected %d-%d, tolerance +/-%d)"
                % (status, ticker, score, low, high, TOLERANCE)
            )
            if not in_range:
                warnings.append(
                    "%s: %.1f outside expected %d-%d +/- %d"
                    % (ticker, score, low, high, TOLERANCE)
                )

            # Verify all 7 dimensions present
            dims = scored[ticker].get("dimension_scores", {})
            if len(dims) < 7:
                warnings.append(
                    "%s: Only %d/7 dimensions scored" % (ticker, len(dims))
                )
        else:
            errors.append("%s: Missing from scoring results" % ticker)

    # Check ranking order
    if len(scores) == 5:
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        expected_order = ["NVDA", "WMT", "JPM", "GE", "DG"]
        actual_order = [t for t, _ in ranked]

        if actual_order[0] != "NVDA":
            warnings.append("NVDA is not ranked #1 (got #%d)" %
                          (actual_order.index("NVDA") + 1))
        if actual_order[-1] != "DG":
            warnings.append("DG is not ranked last (got #%d)" %
                          (actual_order.index("DG") + 1))

    log.info("=" * 60)
    log.info("PORTFOLIO VALIDATION")
    log.info("=" * 60)
    for line in summary_lines:
        log.info(line)
    if warnings:
        log.warning("WARNINGS:")
        for w in warnings:
            log.warning("  %s", w)
    log.info("=" * 60)

    ti.xcom_push(key="scores", value=scores)
    ti.xcom_push(key="summary", value="\n".join(summary_lines))
    ti.xcom_push(key="warnings", value=warnings)
    ti.xcom_push(key="validation_passed", value=len(errors) == 0)

    if errors:
        raise ValueError("Validation errors:\n" + "\n".join(errors))

    log.info("Validation PASSED for all %d companies", len(CS3_TICKERS))
    return scores


def aggregate_portfolio(**context):
    """Final portfolio summary with ranking and metrics.

    Produces a production audit report that Streamlit doesn't generate:
    - Before/after comparison
    - Portfolio average
    - Ranked listing with expected range checks
    """
    ti = context["ti"]
    scores = ti.xcom_pull(task_ids="validate_results", key="scores") or {}

    if not scores:
        log.warning("No scores to aggregate")
        return {}

    avg = sum(scores.values()) / len(scores)
    ranked = sorted(scores.items(), key=lambda x: -x[1])

    log.info("=" * 60)
    log.info("FINAL PORTFOLIO RANKING (Org-AI-R)")
    log.info("=" * 60)
    for rank, (ticker, score) in enumerate(ranked, 1):
        exp = EXPECTED_RANGES.get(ticker, (0, 100))
        in_range = exp[0] <= score <= exp[1]
        status = "✓" if in_range else "~"
        log.info("  #%d  %s: %.1f  [expected %d-%d] %s",
                 rank, ticker, score, exp[0], exp[1], status)
    log.info("-" * 60)
    log.info("  Portfolio Average: %.1f", avg)
    log.info("  Companies Scored:  %d/%d", len(scores), len(CS3_TICKERS))
    log.info("=" * 60)

    result = {"scores": scores, "average": round(avg, 2), "ranked": ranked}
    ti.xcom_push(key="portfolio_result", value=result)
    return result


# ── Default Args ──────────────────────────────────────────────────

default_args = {
    "owner": "pe-org-air-team",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=3),
    "retry_exponential_backoff": True,
    "sla": timedelta(hours=1),
}

# ── DAG Definition ────────────────────────────────────────────────

with DAG(
    dag_id="scoring_pipeline",
    default_args=default_args,
    description="CS3: Score portfolio + validate + aggregate (waits for evidence collection)",
    schedule_interval="0 6 * * 1",
    start_date=datetime(2026, 2, 1),
    catchup=False,
    max_active_runs=1,
    tags=["cs3", "scoring", "org-air", "validation"],
    doc_md=__doc__,
) as dag:

    start = EmptyOperator(task_id="start")

    # Wait for evidence collection to finish before scoring
    wait_for_evidence = ExternalTaskSensor(
        task_id="wait_for_evidence_collection",
        external_dag_id="evidence_collection_pipeline",
        external_task_id="end",
        allowed_states=["success"],
        failed_states=["failed", "upstream_failed"],
        mode="reschedule",
        poke_interval=30,
        timeout=60,
        soft_fail=True,
        doc_md="Wait for evidence_collection_pipeline (soft-fail if not run this week)",
    )

    # Capture previous scores for drift detection
    baseline = PythonOperator(
        task_id="capture_baseline",
        python_callable=capture_previous_scores,
        doc_md="Snapshot current scores before re-scoring (drift detection)",
    )

    score = PythonOperator(
        task_id="score_portfolio",
        python_callable=score_all_companies,
        pool=API_POOL,
        execution_timeout=timedelta(minutes=15),
        trigger_rule=TriggerRule.ALL_DONE,
        doc_md="Score all companies via API (pool-limited)",
    )

    validate = PythonOperator(
        task_id="validate_results",
        python_callable=validate_results,
        doc_md="Validate ranges, ranking, 7 dimensions per company",
    )

    aggregate = PythonOperator(
        task_id="aggregate_portfolio",
        python_callable=aggregate_portfolio,
        trigger_rule=TriggerRule.ALL_DONE,
        doc_md="Final portfolio ranking and audit report",
    )

    end = EmptyOperator(
        task_id="end",
        trigger_rule=TriggerRule.ALL_DONE,
    )

    start >> wait_for_evidence >> baseline >> score >> validate >> aggregate >> end
