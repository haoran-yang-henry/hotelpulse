"""
### Platform health watchdog

Every 15 minutes, independent of the pipelines it watches (ADR-0018):

1. **sync_dag_runs** - mirror recent DAG runs from the Airflow REST API into
   `audit.dag_runs` (success rates and durations on the Data Platform Health dashboard);
2. **check_freshness** - compare each dataset's latest update with its SLA, record the result
   in `audit.freshness` and alert on stale or empty datasets;
3. **check_landing_zone** - alert when landing files wait too long to be loaded;
4. **escalate_dq_warnings** - turn new warn-level data-quality results into alerts.

Task failures alert immediately through the shared failure callback.
"""

import os
from datetime import UTC, datetime, timedelta

import pendulum
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import dag, task
from shared.common import DEFAULT_ARGS, DWH_CONN_ID, LOCAL_TZ

from hotelpulse import observability, settings

LANDING_MAX_WAIT = timedelta(hours=2)


def dwh():
    return PostgresHook(postgres_conn_id=DWH_CONN_ID).get_conn()


@dag(
    dag_id="platform_health",
    schedule="*/15 * * * *",
    start_date=pendulum.datetime(2026, 10, 1, tz=LOCAL_TZ),
    catchup=False,
    max_active_runs=1,
    default_args={**DEFAULT_ARGS, "retries": 1},
    tags=["observability"],
    doc_md=__doc__,
)
def platform_health():
    @task
    def sync_dag_runs() -> int:
        api = os.environ.get("AIRFLOW_API_URL", "http://airflow-apiserver:8080")
        runs = observability.fetch_dag_runs(api, datetime.now(UTC) - timedelta(days=3))
        with dwh() as conn:
            return observability.sync_dag_runs(conn, runs)

    @task
    def check_freshness() -> dict[str, str]:
        now = datetime.now(UTC)
        with dwh() as conn:
            results = observability.check_freshness(conn, now)
            observability.record_freshness(conn, now, results)
            for alert in observability.freshness_alerts(results):
                observability.raise_alert(conn, alert)
        return {r.dataset: r.status for r in results}

    @task
    def check_landing_zone() -> int:
        with dwh() as conn:
            alerts = observability.pending_file_alerts(
                conn, settings.landing_dir(), datetime.now(UTC), LANDING_MAX_WAIT
            )
            for alert in alerts:
                observability.raise_alert(conn, alert)
        return len(alerts)

    @task
    def escalate_dq_warnings() -> int:
        with dwh() as conn:
            alerts = observability.dq_alerts(conn, datetime.now(UTC) - timedelta(minutes=20))
            return sum(observability.raise_alert(conn, a) is not None for a in alerts)

    sync_dag_runs()
    check_freshness()
    check_landing_zone()
    escalate_dq_warnings()


platform_health()
