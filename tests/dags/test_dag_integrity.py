"""DAG integrity tests - run inside the Airflow image (`make test-dags`)."""

import sys
from pathlib import Path

import pytest

pytest.importorskip("airflow")

from airflow.dag_processing.dagbag import DagBag

DAGS_DIR = Path("/opt/airflow/dags")
EXPECTED = {
    "sim_pms_source",
    "pms_ingest",
    "marts_build",
    "sim_web_traffic",
    "web_events_ingest",
    "web_marts_build",
    "sim_operations",
    "operations_ingest",
    "operations_marts_build",
    "platform_health",
    "ops_alert_drill",
}


@pytest.fixture(scope="module")
def dagbag() -> DagBag:
    # the DAG processor puts the dags folder on sys.path (for `shared`); mirror that here
    sys.path.insert(0, str(DAGS_DIR))
    return DagBag(dag_folder=str(DAGS_DIR))


def test_no_import_errors(dagbag):
    assert dagbag.import_errors == {}


def test_expected_dags_present(dagbag):
    assert set(dagbag.dag_ids) >= EXPECTED


@pytest.mark.parametrize("dag_id", sorted(EXPECTED))
def test_dag_conventions(dagbag, dag_id):
    dag = dagbag.dags[dag_id]  # in memory; get_dag() also queries the metadata DB
    assert dag.tags, "every DAG is tagged"
    assert dag.doc_md, "every DAG is documented"
    assert not dag.catchup
    assert dag.max_active_runs == 1
    for task in dag.tasks:
        assert task.owner == "data-engineering"
        assert task.on_failure_callback, "failures must raise an alert"
        if dag_id != "ops_alert_drill":  # the drill fails on purpose, without retries
            assert task.retries >= 1


def test_pms_ingest_ends_with_quality_gate(dagbag):
    dag = dagbag.dags["pms_ingest"]
    leaves = {t.task_id for t in dag.leaves}
    assert leaves == {"dq_core"}
    assert dag.get_task("dq_core").outlets, "quality gate publishes the core asset"
