"""
### Operations marts build

Rebuilds the operations marts whenever new exports are staged **or** the revenue marts
change - both join the PMS: consumables per room night (occupancy from `hotel_daily_kpi`),
reviews linked to their stay (occupancy during the stay) and the purchase suggestion for the
next 14 nights (rooms on the books from `booking_pace`).
"""

import pendulum
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator
from airflow.sdk import dag
from shared.assets import MARTS_OPERATIONS, MARTS_REVENUE, OPERATIONS_STAGED
from shared.common import DEFAULT_ARGS, DWH_CONN_ID, LOCAL_TZ, SQL_DIR, data_quality


def build(name: str) -> SQLExecuteQueryOperator:
    return SQLExecuteQueryOperator(
        task_id=f"build_{name}", conn_id=DWH_CONN_ID, sql=f"marts/{name}.sql"
    )


@dag(
    dag_id="operations_marts_build",
    schedule=(OPERATIONS_STAGED | MARTS_REVENUE),
    start_date=pendulum.datetime(2026, 10, 1, tz=LOCAL_TZ),
    catchup=False,
    max_active_runs=1,
    template_searchpath=[SQL_DIR],
    default_args=DEFAULT_ARGS,
    tags=["marts", "operations"],
    doc_md=__doc__,
)
def operations_marts_build():
    dq_marts = data_quality.override(task_id="dq_marts", outlets=[MARTS_OPERATIONS])(
        "operations/marts"
    )
    build("consumables_daily") >> build("purchase_suggestion") >> dq_marts
    build("guest_reviews") >> dq_marts


operations_marts_build()
