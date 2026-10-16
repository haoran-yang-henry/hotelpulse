"""Evaluate "Explain this chart" against the injected anomalies (ground truth).

    make evaluate      # needs the running stack; writes docs/insight-evaluation.md

For each chart where an anomaly should be visible, the running insight service is asked for
an explanation (default filters). Two levels are scored:

* **facts** - the deterministic engine flags the right series, direction and time window;
* **narrative** - the headline/observations name the affected series and the time window.

Control charts without an injected anomaly check that nothing is flagged in those windows.
"""

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import httpx
import psycopg

from hotelpulse import settings
from hotelpulse.metabase.client import MetabaseClient
from hotelpulse.simulator import anomalies

SIGNAL_KINDS = {"anomaly", "level_shift", "extreme_run", "divergence", "share_shift"}
# short-lived signals only: a seasonal level shift on a control chart is not a false alarm
POINT_KINDS = SIGNAL_KINDS - {"level_shift"}
SLACK = timedelta(days=7)
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]  # fmt: skip


@dataclass(frozen=True)
class Case:
    anomaly: str | None  # None = control chart
    dashboard: str
    card: str
    filters: dict[str, str]
    series: str
    direction: str | None
    keywords: tuple[str, ...] = ()


CASES = [
    Case("A1", "Website & Booking Funnel", "Payment success rate by device",
         {"period": "past12weeks"}, "mobile", "low", ("mobile",)),
    Case("A1", "Website & Booking Funnel", "Failed payments by error code",
         {"period": "past12weeks"}, "gateway_timeout", "high", ("gateway",)),
    Case("A1", "Revenue & Distribution", "Direct share of new bookings",
         {"period": "past26weeks"}, "Hotel website", "low", ("website",)),
    Case("A5", "Website & Booking Funnel", "Tracking coverage by week",
         {"period": "past12weeks"}, "Tracking coverage", "low", ("coverage",)),
    Case(None, "Revenue & Distribution", "Occupancy by week vs. last year",
         {"period": "past26weeks"}, "This year", None),
    Case(None, "Revenue & Distribution", "ADR and RevPAR by week",
         {"period": "past26weeks"}, "ADR", None),
]  # fmt: skip


def overlaps(meta: dict, start: date, end: date) -> bool:
    if "start" not in meta:
        return False
    f_start, f_end = date.fromisoformat(meta["start"]), date.fromisoformat(meta["end"])
    return f_start <= end + SLACK and f_end + timedelta(days=6) >= start - SLACK


def fact_hit(
    case: Case, facts: list[dict], start: date, end: date, kinds: set[str] = SIGNAL_KINDS
) -> bool:
    for f in facts:
        meta = f.get("meta") or {}
        if f["kind"] not in kinds or meta.get("series") != case.series:
            continue
        if case.direction and meta.get("direction") not in (None, case.direction):
            continue
        if overlaps(meta, start, end):
            return True
    return False


def mentions_window(text: str, start: date, end: date) -> bool:
    days = {start + timedelta(days=i) for i in range(-10, (end - start).days + 11)}
    if any(d.isoformat() in text for d in days):
        return True
    months = {MONTHS[d.month - 1] for d in (start, end)}
    return any(m in text or m[:3] in text for m in months)


def narrative_hit(case: Case, narrative: dict, start: date, end: date) -> bool:
    text = " ".join([narrative["headline"], *(o["text"] for o in narrative["observations"])])
    named = any(k.lower() in text.lower() for k in case.keywords)
    return named and mentions_window(text, start, end)


def run(insight_url: str, mb: MetabaseClient, anchor: date, today: date) -> str:
    catalogue = anomalies.load(anchor)
    windows = {  # ongoing anomalies (A5) end today
        k: (a.start, min(a.end - timedelta(days=1), today)) for k, a in catalogue.items()
    }
    dashboards = {
        d["name"]: d["id"]
        for d in mb.get("/collection/root/items", params={"models": "dashboard"})["data"]
    }
    for c in mb.get("/collection"):
        if c.get("name") == "HotelPulse":
            for d in mb.get(f"/collection/{c['id']}/items", params={"models": "dashboard"})["data"]:
                dashboards[d["name"]] = d["id"]
    rows, scores = [], {"facts": [], "narrative": [], "verified": [], "false_positive": []}
    for case in CASES:
        dash_id = dashboards[case.dashboard]
        dash = mb.get(f"/dashboard/{dash_id}")
        card_id = next(dc["card_id"] for dc in dash["dashcards"]
                       if dc.get("card") and dc["card"]["name"] == case.card)  # fmt: skip
        body = httpx.get(
            f"{insight_url}/api/explain",
            params={"dashboard": dash_id, "card": card_id, **case.filters},
            timeout=300,
        ).json()
        verified = body["verification"]["verified"]
        scores["verified"].append(verified)
        meta = body["meta"]
        if case.anomaly:
            start, end = windows[case.anomaly]
            f_hit = fact_hit(case, body["facts"], start, end)
            n_hit = narrative_hit(case, body["narrative"], start, end)
            scores["facts"].append(f_hit)
            scores["narrative"].append(n_hit)
            result = f"facts {'✅' if f_hit else '❌'} · narrative {'✅' if n_hit else '❌'}"
        else:
            # short-lived signals in the A1 window on charts A1 does not touch = false alarm
            fp = fact_hit(case, body["facts"], *windows["A1"], kinds=POINT_KINDS)
            scores["false_positive"].append(fp)
            result = "false alarm ❌" if fp else "no false alarm ✅"
        rows.append(
            f"| {case.anomaly or 'control'} | {case.card} | {result} | "
            f"{'✅' if verified else '⚠'} | {meta['latency_ms'] / 1000:.1f} s | "
            f"{body['narrative']['headline']} |"
        )

    def rate(values: list[bool]) -> str:
        return f"{sum(values)}/{len(values)} ({100 * sum(values) / max(len(values), 1):.0f} %)"

    lines = [
        "# Explain-this-chart evaluation",
        "",
        "Generated by `make evaluate` against the running stack: the insight service explains",
        "the charts in which the injected anomalies should be visible (default filters), and two",
        "control charts that the anomalies do not touch (a short-lived signal there during the A1"
        " window counts as a false alarm). Ground truth: "
        "`src/hotelpulse/simulator/anomalies.yaml`.",
        "",
        f"- Model: `{meta['model'] or 'template'}`, anchor date {anchor.isoformat()}",
        f"- Fact-level detection: **{rate(scores['facts'])}**",
        f"- Narrative-level detection: **{rate(scores['narrative'])}**",
        f"- All numbers verified: **{rate(scores['verified'])}**",
        f"- False alarms on control charts: **{rate(scores['false_positive'])}**",
        "",
        "| Anomaly | Chart | Detected | Numbers verified | Latency | Headline |",
        "|---|---|---|---|---|---|",
        *rows,
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--insight-url", default="http://localhost:8020")
    parser.add_argument("--metabase-url", default="http://localhost:3001")
    parser.add_argument(
        "--out", default=str(settings.PROJECT_ROOT / "docs" / "insight-evaluation.md")
    )
    args = parser.parse_args()
    dsn = (
        f"postgresql://pms_admin:{os.environ['PMS_ADMIN_PASSWORD']}@localhost:"
        f"{os.environ.get('POSTGRES_PORT', '5433')}/pms"
    )
    with psycopg.connect(dsn) as conn:
        anchor = date.fromisoformat(
            conn.execute("SELECT value FROM sim.config WHERE key = 'anchor_date'").fetchone()[0]
        )
    mb = MetabaseClient(args.metabase_url)
    mb.login(os.environ["MB_ADMIN_EMAIL"], os.environ["MB_ADMIN_PASSWORD"])
    report = run(args.insight_url, mb, anchor, date.today())
    Path(args.out).write_text(report)
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
