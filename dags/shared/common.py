"""Connection ids, default arguments and reusable tasks."""

import logging
from datetime import timedelta

from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import task

from hotelpulse import observability, quality, settings

log = logging.getLogger(__name__)

DWH_CONN_ID = "dwh"
PMS_SOURCE_CONN_ID = "pms_source"
PMS_ADMIN_CONN_ID = "pms_admin"
LOCAL_TZ = "Europe/Lisbon"
SQL_DIR = str(settings.WAREHOUSE_DIR / "sql")


def alert_on_failure(context) -> None:
    """Task failed after its last retry: record an error alert right away (ADR-0018)."""
    try:
        ti = context["ti"]
        error = str(context.get("exception") or "unknown error").splitlines()[0][:300]
        alert = observability.Alert(
            "error",
            f"{ti.dag_id}.{ti.task_id}",
            f"Task failed after {ti.try_number} attempt(s): {error}",
            f"task:{ti.dag_id}.{ti.task_id}:{ti.run_id}",
            {"dag_id": ti.dag_id, "task_id": ti.task_id, "run_id": ti.run_id},
        )
        with PostgresHook(postgres_conn_id=DWH_CONN_ID).get_conn() as conn:
            observability.raise_alert(conn, alert)
    except Exception:  # never let alerting hide the original failure
        log.exception("Could not record failure alert")


DEFAULT_ARGS = {
    "owner": "data-engineering",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
    "on_failure_callback": alert_on_failure,
}


@task
def data_quality(suite: str, run_id: str | None = None) -> dict[str, int]:
    """Run a data-quality suite (e.g. ``pms/staging``); fail the task on error-level violations."""
    with PostgresHook(postgres_conn_id=DWH_CONN_ID).get_conn() as conn:
        results = quality.run_suite(conn, suite, run_id or "manual")
    quality.enforce(results)
    return {status: sum(r.status == status for r in results) for status in ("pass", "warn", "fail")}
