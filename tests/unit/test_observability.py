from datetime import UTC, datetime, timedelta

from hotelpulse import observability
from hotelpulse.observability import Freshness

NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)


def fresh(age_h: float | None, sla_h: float = 3, severity: str = "error") -> Freshness:
    last = None if age_h is None else NOW - timedelta(hours=age_h)
    age = None if age_h is None else timedelta(hours=age_h)
    return Freshness("Web marts", last, age, timedelta(hours=sla_h), severity)


def test_freshness_status():
    assert fresh(1).status == "ok"
    assert fresh(5).status == "stale"
    assert fresh(None).status == "empty"


def test_freshness_alerts_only_for_problems():
    alerts = observability.freshness_alerts([fresh(1), fresh(5), fresh(None)])
    assert [(a.severity, a.dedupe_key) for a in alerts] == [
        ("error", "fresh:Web marts"),
        ("warn", "fresh:Web marts"),
    ]
    assert "5.0 h ago (SLA 3 h)" in alerts[0].message


def test_run_duration():
    run = {"start_date": "2026-10-16T09:00:00Z", "end_date": "2026-10-16T09:01:30.5Z"}
    assert observability.duration(run) == 90.5
    assert observability.duration({"start_date": None, "end_date": None}) is None


def test_webhook_is_optional(monkeypatch):
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    assert observability.notify(observability.Alert("warn", "x", "y", "k")) is False
