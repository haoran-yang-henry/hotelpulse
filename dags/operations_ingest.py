"""
### Operations ingestion

Every night (04:00 Europe/Lisbon) loads the operational export files - consumables usage and
guest reviews - with the same exactly-once file loader as website events (ADR-0011, ADR-0019):

1. **load** - every landing-zone file not yet in `audit.loaded_files` is copied into `raw`
   in its own transaction together with its manifest entry. If there is nothing new, the rest
   of the DAG is skipped.
2. **stage** - typed rows; a re-exported day or an edited review replaces the earlier version.
3. **quality** - the staging gate publishes the asset that triggers `operations_marts_build`.
"""

import pendulum
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import chain, dag, task
from airflow.timetables.interval import CronDataIntervalTimetable
from shared.assets import OPERATIONS_STAGED
from shared.common import DEFAULT_ARGS, DWH_CONN_ID, LOCAL_TZ, SQL_DIR, data_quality

from hotelpulse import settings
from hotelpulse.pipelines import files


@dag(
    dag_id="operations_ingest",
    schedule=CronDataIntervalTimetable("0 4 * * *", timezone=LOCAL_TZ),
    start_date=pendulum.datetime(2026, 10, 1, tz=LOCAL_TZ),
    catchup=False,
    max_active_runs=1,
    template_searchpath=[SQL_DIR],
    default_args=DEFAULT_ARGS,
    tags=["ingestion", "operations"],
    doc_md=__doc__,
)
def operations_ingest():
    @task.short_circuit
    def load_landing_files(run_id: str | None = None) -> bool:
        conn = PostgresHook(postgres_conn_id=DWH_CONN_ID).get_conn()
        conn.autocommit = True  # one transaction per file
        with conn:
            files.load_pending(conn, settings.landing_dir(), run_id, files.OPERATIONS_DATASETS)
            # continue if this run owns raw rows - also when an earlier attempt loaded them
            return conn.execute(
                "SELECT EXISTS (SELECT 1 FROM raw.inventory_usage WHERE _batch_id = %(b)s)"
                " OR EXISTS (SELECT 1 FROM raw.reviews WHERE _batch_id = %(b)s)",
                {"b": run_id},
            ).fetchone()[0]

    stage = [
        SQLExecuteQueryOperator(
            task_id=f"stage_{name}", conn_id=DWH_CONN_ID, sql=f"staging/operations_{name}.sql"
        )
        for name in ("inventory_usage", "reviews")
    ]
    dq_staging = data_quality.override(task_id="dq_staging", outlets=[OPERATIONS_STAGED])(
        "operations/staging"
    )

    chain(load_landing_files(), stage, dq_staging)


operations_ingest()
