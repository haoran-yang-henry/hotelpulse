"""
### Simulated website traffic

Every 15 minutes, sends the website visits that have "happened" since the last run to the
event collector over HTTP - like browsers do. Traffic is consistent with the simulated PMS:
each website booking has a converting visit carrying its confirmation code. A watermark makes
the simulation catch up after downtime. Tagged `simulation` - in a real deployment this DAG
does not exist.
"""

from datetime import UTC, datetime

import pendulum
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import dag, task
from shared.common import DEFAULT_ARGS, LOCAL_TZ, PMS_ADMIN_CONN_ID

from hotelpulse import settings
from hotelpulse.simulator import web


@dag(
    dag_id="sim_web_traffic",
    schedule="*/15 * * * *",
    start_date=pendulum.datetime(2026, 10, 1, tz=LOCAL_TZ),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["simulation", "web"],
    doc_md=__doc__,
)
def sim_web_traffic():
    @task
    def send_traffic() -> int:
        with PostgresHook(postgres_conn_id=PMS_ADMIN_CONN_ID).get_conn() as conn:
            return web.run_live(conn, settings.collector_url(), datetime.now(UTC))

    send_traffic()


sim_web_traffic()
