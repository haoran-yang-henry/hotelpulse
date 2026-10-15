"""
### Website events ingestion

Hourly, file-based and exactly-once (ADR-0011):

1. **load** - every landing-zone file not yet in `audit.loaded_files` is copied into `raw`
   in its own transaction together with its manifest entry. Late files are picked up by the
   next run. If there is nothing new for this run, the rest of the DAG is skipped.
2. **stage** - deduplicate by `event_id`, correct device clocks, classify devices and bots,
   parse UTM parameters.
3. **sessions** - rebuild all sessions of every visitor seen in this batch (ADR-0012).
4. **quality** - checks after staging and core; the core gate publishes the session asset.
"""

import pendulum
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import chain, dag, task
from shared.assets import FCT_WEB_SESSION
from shared.common import DEFAULT_ARGS, DWH_CONN_ID, LOCAL_TZ, SQL_DIR, data_quality

from hotelpulse import settings
from hotelpulse.pipelines import files


@dag(
    dag_id="web_events_ingest",
    schedule="5 * * * *",
    start_date=pendulum.datetime(2026, 10, 1, tz=LOCAL_TZ),
    catchup=False,
    max_active_runs=1,
    template_searchpath=[SQL_DIR],
    default_args=DEFAULT_ARGS,
    tags=["ingestion", "web"],
    doc_md=__doc__,
)
def web_events_ingest():
    @task.short_circuit
    def load_landing_files(run_id: str | None = None) -> bool:
        conn = PostgresHook(postgres_conn_id=DWH_CONN_ID).get_conn()
        conn.autocommit = True  # one transaction per file
        with conn:
            files.load_pending(conn, settings.landing_dir(), run_id)
            # continue if this run owns raw events - also when an earlier attempt loaded them
            return conn.execute(
                "SELECT EXISTS (SELECT 1 FROM raw.web_events WHERE _batch_id = %s)", (run_id,)
            ).fetchone()[0]

    stage = SQLExecuteQueryOperator(
        task_id="stage_web_events", conn_id=DWH_CONN_ID, sql="staging/web_events.sql"
    )
    dq_staging = data_quality.override(task_id="dq_staging")("web/staging")
    sessions = SQLExecuteQueryOperator(
        task_id="build_sessions", conn_id=DWH_CONN_ID, sql="core/web_sessions.sql"
    )
    dq_core = data_quality.override(task_id="dq_core", outlets=[FCT_WEB_SESSION])("web/core")

    chain(load_landing_files(), stage, dq_staging, sessions, dq_core)


web_events_ingest()
