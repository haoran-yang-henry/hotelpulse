"""Fixtures for end-to-end tests against the running stack (`make e2e`)."""

import os
import time
from collections.abc import Callable

import httpx
import psycopg
import pytest

from hotelpulse.metabase.client import MetabaseClient

PORT = {
    "airflow": os.environ.get("AIRFLOW_PORT", "8081"),
    "metabase": os.environ.get("METABASE_PORT", "3001"),
    "web": os.environ.get("WEB_PORT", "8030"),
    "collector": os.environ.get("COLLECTOR_PORT", "8010"),
    "insight": os.environ.get("INSIGHT_PORT", "8020"),
    "postgres": os.environ.get("POSTGRES_PORT", "5433"),
}
URL = {name: f"http://localhost:{port}" for name, port in PORT.items() if name != "postgres"}
PIPELINES = ("pms_ingest", "marts_build", "web_events_ingest", "web_marts_build")


def pytest_addoption(parser):
    parser.addoption(
        "--wait-for-pipelines",
        action="store_true",
        help="on a fresh stack, wait until the first runs of the pipelines have succeeded",
    )


class Airflow:
    def __init__(self, url: str) -> None:
        self.http = httpx.Client(base_url=url, timeout=30)
        token = self.http.get("/auth/token").json()["access_token"]
        self.http.headers["Authorization"] = f"Bearer {token}"

    def trigger(self, dag_id: str) -> str:
        run_id = f"e2e__{dag_id}__{time.time_ns()}"
        response = self.http.post(
            f"/api/v2/dags/{dag_id}/dagRuns", json={"dag_run_id": run_id, "logical_date": None}
        )
        response.raise_for_status()
        return run_id

    def state(self, dag_id: str, run_id: str) -> str:
        return self.http.get(f"/api/v2/dags/{dag_id}/dagRuns/{run_id}").json()["state"]

    def wait(self, dag_id: str, run_id: str, timeout_s: int = 600) -> str:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            state = self.state(dag_id, run_id)
            if state in ("success", "failed"):
                return state
            time.sleep(3)
        raise TimeoutError(f"{dag_id}/{run_id} did not finish in {timeout_s} s")

    def runs(self, dag_id: str, **params) -> list[dict]:
        return self.http.get(f"/api/v2/dags/{dag_id}/dagRuns", params=params).json()["dag_runs"]


def eventually(check: Callable[[], bool], timeout_s: int = 120, every_s: float = 3) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(every_s)
    return False


@pytest.fixture(scope="session")
def airflow(request) -> Airflow:
    client = Airflow(URL["airflow"])
    if request.config.getoption("--wait-for-pipelines"):
        for dag_id in PIPELINES:
            ok = eventually(
                lambda d=dag_id: any(r["state"] == "success" for r in client.runs(d)),
                timeout_s=900,
                every_s=10,
            )
            assert ok, f"{dag_id} never succeeded"
        time.sleep(30)  # let asset-triggered marts finish
    return client


@pytest.fixture(scope="session")
def dwh(airflow) -> psycopg.Connection:
    dsn = f"postgresql://dwh_etl:{os.environ['DWH_ETL_PASSWORD']}@localhost:{PORT['postgres']}/dwh"
    with psycopg.connect(dsn, autocommit=True) as conn:
        yield conn


@pytest.fixture(scope="session")
def metabase() -> MetabaseClient:
    client = MetabaseClient(URL["metabase"])
    client.login(os.environ["MB_ADMIN_EMAIL"], os.environ["MB_ADMIN_PASSWORD"])
    return client


@pytest.fixture(scope="session")
def dashboards(metabase) -> dict[str, dict]:
    collection = next(c for c in metabase.get("/collection") if c.get("name") == "HotelPulse")
    items = metabase.get(f"/collection/{collection['id']}/items", params={"models": "dashboard"})
    return {d["name"]: metabase.get(f"/dashboard/{d['id']}") for d in items["data"]}
