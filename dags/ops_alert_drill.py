"""
### Alert fire drill

Manual only. Its single task fails on purpose so the alerting path - failure callback,
`audit.alerts`, optional webhook, Data Platform Health dashboard - can be tested end to end
(`make e2e` triggers it).
"""

import pendulum
from airflow.sdk import dag, task
from shared.common import DEFAULT_ARGS, LOCAL_TZ


@dag(
    dag_id="ops_alert_drill",
    schedule=None,
    start_date=pendulum.datetime(2026, 10, 1, tz=LOCAL_TZ),
    catchup=False,
    max_active_runs=1,
    default_args={**DEFAULT_ARGS, "retries": 0},
    tags=["observability", "drill"],
    doc_md=__doc__,
)
def ops_alert_drill():
    @task
    def fail_on_purpose() -> None:
        raise RuntimeError("Fire drill: this task fails on purpose to test alerting")

    fail_on_purpose()


ops_alert_drill()
