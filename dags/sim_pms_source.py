"""
### Simulated PMS

Advances the simulated property management system to the current time: bookings,
check-ins, check-outs, cancellations and no-shows that have "happened" since the last run
become visible to the extraction account. Tagged `simulation` - in a real deployment this
DAG does not exist; the PMS changes by itself.
"""

from datetime import UTC, datetime

import pendulum
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import dag, task
from shared.common import DEFAULT_ARGS, LOCAL_TZ, PMS_ADMIN_CONN_ID

from hotelpulse.simulator import pms


@dag(
    dag_id="sim_pms_source",
    schedule="@hourly",
    start_date=pendulum.datetime(2026, 10, 1, tz=LOCAL_TZ),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["simulation", "pms"],
    doc_md=__doc__,
)
def sim_pms_source():
    @task
    def reveal() -> dict[str, int]:
        with PostgresHook(postgres_conn_id=PMS_ADMIN_CONN_ID).get_conn() as conn:
            guests, reservations = pms.reveal(conn, datetime.now(UTC))
        return {"guests": guests, "reservation_changes": reservations}

    reveal()


sim_pms_source()
