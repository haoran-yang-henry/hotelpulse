import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from hotelpulse import landing
from hotelpulse.tracking import collector
from hotelpulse.tracking.schema import TrackingEvent

NOW = datetime(2026, 10, 15, 14, 30, tzinfo=UTC)


def event(**overrides):
    e = {
        "schema_version": 1,
        "event_id": "6f1c1d8e-5d3a-4c9f-9a49-1d2f3c4b5a60",
        "event_name": "search_availability",
        "event_ts": "2026-10-15T14:29:58.120Z",
        "sent_at": "2026-10-15T14:29:59.000Z",
        "anonymous_id": "0b7d8f3e-2a1c-4b5d-8e9f-0a1b2c3d4e5f",
        "page_url": "https://www.hotelpulse.example/rooms?hotel=CITY",
        "properties": {"hotel_code": "CITY", "checkin": "2026-11-01", "checkout": "2026-11-03",
                       "adults": 2},
    }  # fmt: skip
    e.update(overrides)
    return e


def test_valid_event_parses():
    parsed = TrackingEvent.model_validate(event())
    assert parsed.event_name == "search_availability"


@pytest.mark.parametrize(
    "overrides",
    [
        {"properties": {"hotel_code": "CITY"}},  # required properties missing
        {"event_name": "PageView"},  # not in the contract
        {"event_ts": "2026-10-15T14:29:58"},  # timezone-naive
        {"utm_source": "google"},  # unknown top-level field
        {"schema_version": 2},
    ],
)
def test_invalid_events_are_rejected(overrides):
    with pytest.raises(ValidationError):
        TrackingEvent.model_validate(event(**overrides))


def test_process_splits_and_enriches():
    accepted, rejected = collector.process([event(), event(event_name="PageView")], "UA/1.0", NOW)
    assert len(accepted) == 1 and len(rejected) == 1
    assert accepted[0]["collector_ts"] == NOW.isoformat()
    assert accepted[0]["user_agent"] == "UA/1.0"
    assert rejected[0]["payload"]["event_name"] == "PageView"
    assert "event_name" in rejected[0]["error"]


def test_landing_files_are_written_atomically(tmp_path):
    writer = landing.LandingWriter(tmp_path / "ds")
    writer.add_many([{"a": 1}, {"a": 2}], NOW)
    writer.add_many([{"a": 3}], NOW + timedelta(hours=1))
    files = writer.flush()
    assert len(files) == 2
    assert {f.parent.relative_to(tmp_path / "ds").as_posix() for f in files} == {
        "dt=2026-10-15/hour=14",
        "dt=2026-10-15/hour=15",
    }
    assert not list(tmp_path.rglob("*.tmp"))
    assert landing.list_files(tmp_path / "ds") == sorted(files)
    rows = [json.loads(line) for f in sorted(files) for line in landing.read_lines(f)]
    assert rows == [{"a": 1}, {"a": 2}, {"a": 3}]


@pytest.fixture
def client(tmp_path):
    app = collector.create_app(tmp_path)
    with TestClient(app) as c:
        c.landing = tmp_path
        yield c


def test_collect_endpoint_writes_landing_zone(client):
    body = json.dumps({"events": [event(), event(event_name="Nope")]})
    response = client.post(
        "/collect", content=body, headers={"Content-Type": "text/plain", "User-Agent": "UA/2"}
    )
    assert response.status_code == 200
    assert response.json() == {"accepted": 1, "rejected": 1}
    client.app.state.flush()
    (accepted_file,) = landing.list_files(client.landing / landing.WEB_EVENTS)
    (rejected_file,) = landing.list_files(client.landing / landing.WEB_EVENTS_REJECTED)
    record = json.loads(next(landing.read_lines(accepted_file)))
    assert record["user_agent"] == "UA/2" and record["event_name"] == "search_availability"
    rejected = json.loads(next(landing.read_lines(rejected_file)))
    assert rejected["payload"]["event_name"] == "Nope"


@pytest.mark.parametrize("body", ["not json", "{}", json.dumps({"events": []})])
def test_collect_rejects_malformed_batches(client, body):
    assert client.post("/collect", content=body).status_code == 400


def test_tracker_script_is_served(client):
    response = client.get("/tracker.js")
    assert response.status_code == 200
    assert "setConsent" in response.text


def test_committed_tracking_plan_is_up_to_date():
    from pathlib import Path

    from hotelpulse.tracking import plan

    committed = Path(__file__).parents[2] / "docs" / "tracking-plan.md"
    assert committed.read_text() == plan.render(), "run: python -m hotelpulse.tracking.plan"
