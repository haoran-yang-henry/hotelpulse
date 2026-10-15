"""Connection ids, default arguments and reusable tasks."""

from datetime import timedelta

from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import task

from hotelpulse import quality, settings

DWH_CONN_ID = "dwh"
PMS_SOURCE_CONN_ID = "pms_source"
PMS_ADMIN_CONN_ID = "pms_admin"
LOCAL_TZ = "Europe/Lisbon"
SQL_DIR = str(settings.WAREHOUSE_DIR / "sql")

DEFAULT_ARGS = {
    "owner": "data-engineering",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
}


@task
def data_quality(suite: str, run_id: str | None = None) -> dict[str, int]:
    """Run a data-quality suite (e.g. ``pms/staging``); fail the task on error-level violations."""
    with PostgresHook(postgres_conn_id=DWH_CONN_ID).get_conn() as conn:
        results = quality.run_suite(conn, suite, run_id or "manual")
    quality.enforce(results)
    return {status: sum(r.status == status for r in results) for status in ("pass", "warn", "fail")}
