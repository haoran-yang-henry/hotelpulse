"""
### Website marts build

Rebuilds the website marts whenever sessions **or** PMS reservations change - attribution and
tracking coverage join both sources: funnel, payment errors, first/last-touch attribution and
tracking coverage (tracked share of the PMS's website bookings).
"""

import pendulum
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator
from airflow.sdk import dag
from shared.assets import FCT_ROOM_NIGHT, FCT_WEB_SESSION, MARTS_WEB
from shared.common import DEFAULT_ARGS, DWH_CONN_ID, LOCAL_TZ, SQL_DIR, data_quality

MARTS = (
    "web_funnel_daily",
    "web_payment_errors_daily",
    "web_attribution",
    "tracking_coverage_daily",
)


@dag(
    dag_id="web_marts_build",
    schedule=(FCT_WEB_SESSION | FCT_ROOM_NIGHT),
    start_date=pendulum.datetime(2026, 10, 1, tz=LOCAL_TZ),
    catchup=False,
    max_active_runs=1,
    template_searchpath=[SQL_DIR],
    default_args=DEFAULT_ARGS,
    tags=["marts", "web"],
    doc_md=__doc__,
)
def web_marts_build():
    builds = [
        SQLExecuteQueryOperator(
            task_id=f"build_{name}", conn_id=DWH_CONN_ID, sql=f"marts/{name}.sql"
        )
        for name in MARTS
    ]
    dq_marts = data_quality.override(task_id="dq_marts", outlets=[MARTS_WEB])("web/marts")
    builds >> dq_marts


web_marts_build()
