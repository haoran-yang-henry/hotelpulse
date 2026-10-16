"""Platform observability: alerts, dataset freshness, DAG run history (ADR-0018).

``audit.alerts`` is the single alert sink. Alerts with the same dedupe key are recorded at
most once per ``DEDUPE_HOURS``; if ``ALERT_WEBHOOK_URL`` is set, new alerts are also posted
there as Slack-compatible ``{"text": ...}`` messages.
"""

import logging
import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import psycopg
from psycopg.types.json import Jsonb

from hotelpulse.pipelines import files

log = logging.getLogger(__name__)

DEDUPE_HOURS = 6


@dataclass(frozen=True)
class Alert:
    severity: str  # "error" | "warn"
    source: str
    message: str
    dedupe_key: str
    details: dict[str, Any] = field(default_factory=dict)


def notify(alert: Alert) -> bool:
    url = os.environ.get("ALERT_WEBHOOK_URL", "").strip()
    if not url:
        return False
    text = f"[{alert.severity.upper()}] {alert.source}: {alert.message}"
    try:
        httpx.post(url, json={"text": text}, timeout=10).raise_for_status()
        return True
    except httpx.HTTPError as exc:  # alerting must never break the pipeline
        log.warning("Alert webhook failed: %s", exc)
        return False


def raise_alert(conn: psycopg.Connection, alert: Alert) -> int | None:
    """Record an alert unless the same one was raised recently. Returns its id if new."""
    recent = conn.execute(
        "SELECT 1 FROM audit.alerts WHERE dedupe_key = %s"
        " AND raised_at > now() - make_interval(hours => %s)",
        (alert.dedupe_key, DEDUPE_HOURS),
    ).fetchone()
    if recent:
        return None
    alert_id = conn.execute(
        "INSERT INTO audit.alerts (severity, source, message, details, dedupe_key)"
        " VALUES (%s, %s, %s, %s, %s) RETURNING alert_id",
        (alert.severity, alert.source, alert.message, Jsonb(alert.details), alert.dedupe_key),
    ).fetchone()[0]
    if notify(alert):
        conn.execute("UPDATE audit.alerts SET notified = TRUE WHERE alert_id = %s", (alert_id,))
    log.warning("ALERT [%s] %s: %s", alert.severity, alert.source, alert.message)
    return alert_id


# --------------------------------------------------------------------------- freshness


@dataclass(frozen=True)
class FreshnessRule:
    dataset: str
    sql: str  # returns the timestamp of the latest update
    sla: timedelta
    severity: str = "error"


FRESHNESS_RULES = (
    FreshnessRule(
        "PMS reservations (core)", "SELECT max(_loaded_at) FROM core.fct_reservation",
        timedelta(hours=26),
    ),
    FreshnessRule(
        "Revenue marts", "SELECT max(built_at) FROM marts.hotel_daily_kpi", timedelta(hours=26)
    ),
    FreshnessRule(
        "Web events (staging)", "SELECT max(_loaded_at) FROM staging.web_events",
        timedelta(hours=3),
    ),
    FreshnessRule(
        "Web marts", "SELECT max(built_at) FROM marts.web_funnel_daily", timedelta(hours=3),
        "warn",
    ),
)  # fmt: skip


@dataclass(frozen=True)
class Freshness:
    dataset: str
    last_update: datetime | None
    age: timedelta | None
    sla: timedelta
    severity: str

    @property
    def status(self) -> str:
        if self.last_update is None:
            return "empty"
        return "stale" if self.age > self.sla else "ok"


def check_freshness(
    conn: psycopg.Connection, now: datetime, rules: Iterable[FreshnessRule] = FRESHNESS_RULES
) -> list[Freshness]:
    results = []
    for rule in rules:
        last = conn.execute(rule.sql).fetchone()[0]
        results.append(
            Freshness(rule.dataset, last, (now - last) if last else None, rule.sla, rule.severity)
        )
    return results


def record_freshness(conn: psycopg.Connection, now: datetime, results: list[Freshness]) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO audit.freshness"
            " (checked_at, dataset, last_update, age_hours, sla_hours, status)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            [
                (
                    now,
                    r.dataset,
                    r.last_update,
                    round(r.age.total_seconds() / 3600, 2) if r.age else None,
                    r.sla.total_seconds() / 3600,
                    r.status,
                )
                for r in results
            ],
        )


def freshness_alerts(results: list[Freshness]) -> list[Alert]:
    alerts = []
    for r in results:
        if r.status == "ok":
            continue
        hours = r.sla.total_seconds() / 3600
        message = (
            "no data loaded yet"
            if r.last_update is None
            else f"last update {r.age.total_seconds() / 3600:.1f} h ago (SLA {hours:.0f} h)"
        )
        # an empty dataset right after deployment is expected; a stale one is a failure
        severity = "warn" if r.status == "empty" else r.severity
        alerts.append(
            Alert(severity, r.dataset, f"Dataset is {r.status}: {message}", f"fresh:{r.dataset}")
        )
    return alerts


def pending_file_alerts(
    conn: psycopg.Connection, landing_root: Path, now: datetime, max_age: timedelta
) -> list[Alert]:
    """Landing files still not loaded after `max_age` (ingestion stuck or failing)."""
    alerts = []
    for dataset in files.WEB_DATASETS:
        stuck = [
            key
            for key, path in files.pending_files(conn, landing_root, dataset, limit=10_000)
            if now.timestamp() - path.stat().st_mtime > max_age.total_seconds()
        ]
        if stuck:
            alerts.append(
                Alert(
                    "error",
                    f"landing/{dataset.name}",
                    f"{len(stuck)} landing files waiting longer than "
                    f"{max_age.total_seconds() / 3600:.0f} h to be loaded",
                    f"landing:{dataset.name}",
                    {"oldest": stuck[0]},
                )
            )
    return alerts


# --------------------------------------------------------------------------- data quality


def dq_alerts(conn: psycopg.Connection, since: datetime) -> list[Alert]:
    """Warn-level check failures recorded since the last watchdog run (errors already fail tasks
    and alert through the failure callback)."""
    rows = conn.execute(
        """
        SELECT DISTINCT ON (check_name) check_name, failing_rows, description
        FROM audit.dq_results
        WHERE status = 'warn' AND checked_at >= %s
        ORDER BY check_name, checked_at DESC
        """,
        (since,),
    ).fetchall()
    return [
        Alert(
            "warn",
            name,
            f"Data-quality warning: {description} ({failing} violating rows)",
            f"dq:{name}",
            {"failing_rows": failing},
        )
        for name, failing, description in rows
    ]


# --------------------------------------------------------------------------- DAG runs


def fetch_dag_runs(api_url: str, since: datetime) -> list[dict]:
    """DAG runs started since `since`, from the Airflow REST API."""
    with httpx.Client(base_url=api_url.rstrip("/"), timeout=30) as client:
        token = client.get("/auth/token").json()["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"
        runs, offset = [], 0
        while True:
            page = client.get(
                "/api/v2/dags/~/dagRuns",
                params={"start_date_gte": since.isoformat(), "limit": 100, "offset": offset},
            ).json()
            runs += page.get("dag_runs", [])
            offset += 100
            if offset >= page.get("total_entries", 0):
                return runs


def sync_dag_runs(conn: psycopg.Connection, runs: list[dict]) -> int:
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO audit.dag_runs (
                dag_id, run_id, run_type, state, data_interval_start, data_interval_end,
                start_date, end_date, duration_s
            ) VALUES (%(dag_id)s, %(dag_run_id)s, %(run_type)s, %(state)s,
                      %(data_interval_start)s, %(data_interval_end)s, %(start_date)s,
                      %(end_date)s, %(duration_s)s)
            ON CONFLICT (dag_id, run_id) DO UPDATE SET
                state = excluded.state,
                end_date = excluded.end_date,
                duration_s = excluded.duration_s,
                synced_at = now()
            """,
            [{**r, "duration_s": duration(r)} for r in runs],
        )
    return len(runs)


def duration(run: dict) -> float | None:
    if not run.get("start_date") or not run.get("end_date"):
        return None
    start = datetime.fromisoformat(run["start_date"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(run["end_date"].replace("Z", "+00:00"))
    return round((end - start).total_seconds(), 1)
