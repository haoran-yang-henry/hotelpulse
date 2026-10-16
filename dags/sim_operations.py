"""
### Simulated operational exports

Every night (02:30 Europe/Lisbon) writes yesterday's exports to the landing zone, like the
hotels' systems would deliver them: consumables usage per hotel and item (inventory system)
and the guest reviews posted that day (review-management tool). Both are consistent with the
simulated PMS; a watermark makes the simulation catch up after downtime. Tagged `simulation` -
in a real deployment this DAG does not exist.
"""

from datetime import UTC, datetime

import pendulum
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import dag, task
from airflow.timetables.interval import CronDataIntervalTimetable
from shared.common import DEFAULT_ARGS, LOCAL_TZ, PMS_ADMIN_CONN_ID

from hotelpulse import settings
from hotelpulse.simulator import operations


@dag(
    dag_id="sim_operations",
    schedule=CronDataIntervalTimetable("30 2 * * *", timezone=LOCAL_TZ),
    start_date=pendulum.datetime(2026, 10, 1, tz=LOCAL_TZ),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["simulation", "operations"],
    doc_md=__doc__,
)
def sim_operations():
    @task
    def export_yesterday() -> dict:
        with PostgresHook(postgres_conn_id=PMS_ADMIN_CONN_ID).get_conn() as conn:
            return operations.run(conn, settings.landing_dir(), datetime.now(UTC))

    export_yesterday()


sim_operations()
