"""
### Marts build

Triggered whenever `core.fct_room_night` is updated. Rebuilds the dashboard-facing marts
(each in a single transaction, so dashboards never see half-built tables), then runs the
mart-level quality checks.
"""

import pendulum
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator
from airflow.sdk import dag
from shared.assets import FCT_ROOM_NIGHT, MARTS_REVENUE
from shared.common import DEFAULT_ARGS, DWH_CONN_ID, LOCAL_TZ, SQL_DIR, data_quality

MARTS = ("hotel_daily_kpi", "channel_daily", "channel_bookings_daily", "booking_pace")


@dag(
    dag_id="marts_build",
    schedule=[FCT_ROOM_NIGHT],
    start_date=pendulum.datetime(2026, 10, 1, tz=LOCAL_TZ),
    catchup=False,
    max_active_runs=1,
    template_searchpath=[SQL_DIR],
    default_args=DEFAULT_ARGS,
    tags=["marts", "revenue"],
    doc_md=__doc__,
)
def marts_build():
    builds = [
        SQLExecuteQueryOperator(
            task_id=f"build_{name}", conn_id=DWH_CONN_ID, sql=f"marts/{name}.sql"
        )
        for name in MARTS
    ]
    dq_marts = data_quality.override(task_id="dq_marts", outlets=[MARTS_REVENUE])("marts")
    builds >> dq_marts


marts_build()
