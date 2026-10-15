"""
### PMS ingestion

Runs every day after the hotels' night audit (03:00 Europe/Lisbon).

1. **extract** (one mapped task per source table) - rows whose `updated_at` falls in the
   data interval, extended by a look-back window, are streamed into `raw` with batch
   metadata. Small reference tables are copied in full. An empty warehouse, or the
   `full_refresh` param, triggers a full load.
2. **stage** - newest version per entity is merged into `staging`; PII is hashed.
3. **core** - dimensions are upserted; facts are rebuilt for exactly the changed reservations.
4. **quality** - checks after staging and core; error-level failures stop the run.

Completing the run updates the `core.fct_room_night` asset, which triggers `marts_build`.
"""

from datetime import UTC, datetime, timedelta

import pendulum
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import Param, chain, dag, get_current_context, task
from airflow.timetables.interval import CronDataIntervalTimetable
from shared.assets import FCT_ROOM_NIGHT
from shared.common import (
    DEFAULT_ARGS,
    DWH_CONN_ID,
    LOCAL_TZ,
    PMS_SOURCE_CONN_ID,
    SQL_DIR,
    data_quality,
)

from hotelpulse.pipelines import extract as ex
from hotelpulse.pipelines.pms import SOURCE_TABLES


@dag(
    dag_id="pms_ingest",
    schedule=CronDataIntervalTimetable("0 3 * * *", timezone=LOCAL_TZ),
    start_date=pendulum.datetime(2026, 10, 1, tz=LOCAL_TZ),
    catchup=False,
    max_active_runs=1,
    template_searchpath=[SQL_DIR],
    params={
        "full_refresh": Param(False, type="boolean", description="Reload everything from the PMS"),
        "lookback_days": Param(2, type="integer", minimum=0, description="Re-read window in days"),
    },
    default_args=DEFAULT_ARGS,
    tags=["ingestion", "pms"],
    doc_md=__doc__,
)
def pms_ingest():
    @task(map_index_template="{{ table_name }}")
    def extract(
        table_name: str,
        params: dict | None = None,
        run_id: str | None = None,
        data_interval_start: datetime | None = None,
        data_interval_end: datetime | None = None,
    ) -> int:
        get_current_context()["table_name"] = table_name  # label for the mapped task instance
        table = SOURCE_TABLES[table_name]
        end = data_interval_end or datetime.now(UTC)
        start = data_interval_start or end - timedelta(days=1)
        with (
            PostgresHook(postgres_conn_id=DWH_CONN_ID).get_conn() as dwh,
            PostgresHook(postgres_conn_id=PMS_SOURCE_CONN_ID).get_conn() as src,
        ):
            target_is_empty = not dwh.execute(
                "SELECT EXISTS (SELECT 1 FROM staging.pms_reservations)"
            ).fetchone()[0]
            window = ex.extraction_window(
                start,
                end,
                lookback=timedelta(days=params["lookback_days"]),
                full_refresh=params["full_refresh"],
                target_is_empty=target_is_empty,
            )
            if table.incremental_column is None:
                window = ex.Window(None, end)
            rows = ex.copy_to_raw(src, dwh, table, window, run_id, datetime.now(UTC))
            ex.log_load(dwh, run_id, f"pms.{table.name}", window, rows)
        return rows

    def sql_task(task_id: str, sql: str, **kwargs) -> SQLExecuteQueryOperator:
        return SQLExecuteQueryOperator(task_id=task_id, conn_id=DWH_CONN_ID, sql=sql, **kwargs)

    extracted = extract.expand(table_name=list(SOURCE_TABLES))

    stage_reference = sql_task("stage_reference", "staging/pms_reference.sql")
    stage_guests = sql_task(
        "stage_guests",
        "staging/pms_guests.sql",
        parameters={"salt": "{{ var.value.pii_hash_secret }}"},
    )
    stage_reservations = sql_task("stage_reservations", "staging/pms_reservations.sql")
    dq_staging = data_quality.override(task_id="dq_staging")("pms/staging")

    build_dimensions = sql_task("build_dimensions", "core/dimensions.sql")
    build_fct_reservation = sql_task("build_fct_reservation", "core/fct_reservation.sql")
    build_fct_room_night = sql_task("build_fct_room_night", "core/fct_room_night.sql")
    dq_core = data_quality.override(task_id="dq_core", outlets=[FCT_ROOM_NIGHT])("pms/core")

    chain(
        extracted,
        stage_reference,
        stage_guests,
        stage_reservations,
        dq_staging,
        build_dimensions,
        build_fct_reservation,
        build_fct_room_night,
        dq_core,
    )


pms_ingest()
