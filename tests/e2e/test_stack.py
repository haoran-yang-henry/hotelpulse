"""End-to-end tests against the running stack - `make e2e` (or `make e2e-clean` from scratch).

They exercise the real paths: website -> PMS -> warehouse, tracker -> collector -> landing
zone -> warehouse, operational exports -> warehouse, dashboards, explanations, alerting and an
idempotent backfill.
"""

import json
import re
import time
import uuid
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest

from tests.e2e.conftest import URL, eventually

CORE_TABLES = (
    "core.fct_reservation",
    "core.fct_room_night",
    "core.fct_web_session",
    "marts.hotel_daily_kpi",
    "marts.booking_pace",
    "marts.web_funnel_daily",
    "marts.consumables_daily",
    "marts.guest_reviews",
    "marts.purchase_suggestion",
)


def count(dwh, table: str) -> int:
    return dwh.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def failing_error_checks(dwh) -> list[str]:
    rows = dwh.execute(
        """
        SELECT check_name FROM (
            SELECT DISTINCT ON (check_name) check_name, status
            FROM audit.dq_results ORDER BY check_name, checked_at DESC
        ) AS latest WHERE status = 'fail'
        """
    ).fetchall()
    return [r[0] for r in rows]


def test_services_are_healthy():
    for name, path in [
        ("metabase", "/api/health"),
        ("airflow", "/api/v2/monitor/health"),
        ("web", "/health"),
        ("collector", "/health"),
        ("insight", "/health"),
    ]:
        assert httpx.get(URL[name] + path, timeout=10).status_code == 200, name


def test_warehouse_is_loaded_and_trustworthy(dwh):
    for table in CORE_TABLES:
        assert count(dwh, table) > 0, f"{table} is empty"
    assert failing_error_checks(dwh) == []


def test_every_dashboard_card_runs(metabase, dashboards):
    assert {
        "Revenue & Distribution",
        "Website & Booking Funnel",
        "Operations & Guest Experience",
        "Data Platform Health",
    } <= set(dashboards)
    for dash in dashboards.values():
        params = {p["id"]: p for p in dash["parameters"]}
        for dc in dash["dashcards"]:
            if not dc.get("card_id"):
                continue
            values = [
                {
                    "id": m["parameter_id"],
                    "type": params[m["parameter_id"]]["type"],
                    "value": params[m["parameter_id"]]["default"],
                    "target": m["target"],
                }
                for m in dc["parameter_mappings"]
                if params[m["parameter_id"]].get("default")
            ]
            result = metabase.run_dashcard(dash["id"], dc["id"], dc["card_id"], values)
            assert "data" in result, f"{dash['name']} / {dc['card']['name']}"


def test_website_booking_reaches_the_warehouse(airflow, dwh):
    web = httpx.Client(base_url=URL["web"], timeout=30)
    checkin = date.today() + timedelta(days=45)
    stay = {
        "hotel": "CITY",
        "checkin": checkin.isoformat(),
        "checkout": (checkin + timedelta(days=2)).isoformat(),
        "adults": 2,
        "children": 0,
    }
    rooms = web.get("/rooms", params=stay)
    assert rooms.status_code == 200
    room = re.search(r"room=([A-Z])", rooms.text)
    assert room, "no bookable room offered"
    booked = web.post(
        "/book",
        data={**stay, "room": room[1], "first_name": "E2E", "last_name": "Test",
              "email": "e2e@example.com", "country": "DEU", "card_number": "4242424242424242"},
    )  # fmt: skip
    assert booked.status_code == 303
    code = re.search(r"/confirmation/(HP\d+)", booked.headers["location"])[1]

    assert airflow.wait("pms_ingest", airflow.trigger("pms_ingest")) == "success"
    row = dwh.execute(
        "SELECT channel_code, status FROM core.fct_reservation WHERE confirmation_code = %s",
        (code,),
    ).fetchone()
    assert row == ("website", "confirmed")


def test_tracking_event_reaches_the_warehouse(airflow, dwh):
    event_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    event = {
        "schema_version": 1, "event_id": event_id, "event_name": "page_view",
        "event_ts": now, "sent_at": now, "anonymous_id": str(uuid.uuid4()),
        "page_url": "https://www.hotelpulse.example/?utm_source=e2e&utm_medium=email",
        "properties": {"page_type": "landing"},
    }  # fmt: skip
    response = httpx.post(
        URL["collector"] + "/collect",
        content=json.dumps({"events": [event]}),
        headers={"Content-Type": "text/plain", "User-Agent": "Mozilla/5.0 (X11; Linux) e2e"},
    )
    assert response.json() == {"accepted": 1, "rejected": 0}
    time.sleep(7)  # the collector flushes its buffer every 5 seconds

    assert airflow.wait("web_events_ingest", airflow.trigger("web_events_ingest")) == "success"
    session = dwh.execute(
        "SELECT s.medium FROM core.fct_web_event AS e"
        " JOIN core.fct_web_session AS s ON s.session_id = e.session_id WHERE e.event_id = %s",
        (event_id,),
    ).fetchone()
    assert session == ("email",)


def test_reviews_are_linked_to_pms_stays(dwh):
    linked, reviews = dwh.execute(
        "SELECT count(reservation_id), count(*) FROM marts.guest_reviews"
    ).fetchone()
    assert reviews > 0 and linked / reviews > 0.95
    assert count(dwh, "marts.purchase_suggestion") == 2 * count(dwh, "core.dim_consumable")


def test_explanation_is_grounded_in_the_data(dashboards):
    dash = dashboards["Website & Booking Funnel"]
    card = next(
        dc for dc in dash["dashcards"]
        if (dc.get("card") or {}).get("name") == "Payment success rate by device"
    )  # fmt: skip
    body = httpx.get(
        URL["insight"] + "/api/explain",
        params={"dashboard": dash["id"], "card": card["card_id"], "period": "Previous 12 weeks"},
        timeout=300,
    ).json()
    assert body["facts"], "no facts computed"
    assert body["meta"]["mode"] in ("llm", "template")
    assert body["verification"]["verified"], body["verification"]["unverified"]
    assert body["filters"][0] == "Period: Previous 12 weeks"


def test_failed_task_raises_an_alert(airflow, dwh):
    started = datetime.now(UTC)
    assert airflow.wait("ops_alert_drill", airflow.trigger("ops_alert_drill")) == "failed"

    def alerted() -> bool:
        return bool(
            dwh.execute(
                "SELECT 1 FROM audit.alerts WHERE source = 'ops_alert_drill.fail_on_purpose'"
                " AND severity = 'error' AND raised_at >= %s",
                (started,),
            ).fetchone()
        )

    assert eventually(alerted, timeout_s=60)


def test_watchdog_records_runs_and_freshness(airflow, dwh):
    started = datetime.now(UTC)
    assert airflow.wait("platform_health", airflow.trigger("platform_health")) == "success"
    statuses = dict(
        dwh.execute(
            "SELECT dataset, status FROM audit.freshness WHERE checked_at >= %s", (started,)
        ).fetchall()
    )
    assert statuses and all(s == "ok" for s in statuses.values()), statuses
    assert count(dwh, "audit.dag_runs") > 0


@pytest.mark.parametrize("days_back", [3])
def test_backfill_is_idempotent(airflow, dwh, days_back):
    """Re-running past PMS ingestion windows must not change any layer."""

    def snapshot() -> tuple:
        return dwh.execute(
            "SELECT (SELECT count(*) FROM staging.pms_reservations),"
            " (SELECT count(*) FROM core.fct_reservation),"
            " (SELECT count(*) FROM core.fct_room_night),"
            " (SELECT sum(booked_revenue) FROM core.fct_reservation)"
        ).fetchone()

    before = snapshot()
    today = datetime.now(UTC).date()
    response = airflow.http.post(
        "/api/v2/backfills",
        json={
            "dag_id": "pms_ingest",
            "from_date": f"{today - timedelta(days=days_back)}T00:00:00Z",
            "to_date": f"{today - timedelta(days=1)}T00:00:00Z",
            "reprocess_behavior": "completed",
            "max_active_runs": 1,
        },
    )
    response.raise_for_status()
    backfill_id = response.json()["id"]

    def finished() -> bool:
        return (
            airflow.http.get(f"/api/v2/backfills/{backfill_id}").json()["completed_at"] is not None
        )

    assert eventually(finished, timeout_s=900, every_s=5)
    runs = airflow.runs("pms_ingest", run_type="backfill")
    assert runs and all(r["state"] == "success" for r in runs)
    assert snapshot() == before
    assert failing_error_checks(dwh) == []
