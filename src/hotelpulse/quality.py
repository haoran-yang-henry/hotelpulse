"""Data-quality checks as code.

A check is a SQL file under ``warehouse/tests/<layer>/`` that **returns the violating rows**;
zero rows means the check passes. A header declares its severity and description::

    -- severity: error
    -- description: Occupancy is between 0 and 100 %.
    SELECT ... FROM marts.hotel_daily_kpi WHERE occupancy > 1

Results are persisted to ``audit.dq_results``. Failing ``error`` checks raise
``DataQualityError`` (failing the Airflow task); failing ``warn`` checks are only recorded.
"""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg import sql

from hotelpulse import settings

log = logging.getLogger(__name__)

HEADER_RE = re.compile(r"^--\s*(?P<key>severity|description)\s*:\s*(?P<value>.+?)\s*$")
SEVERITIES = ("error", "warn")
SAMPLE_SIZE = 5


@dataclass(frozen=True)
class Check:
    name: str
    layer: str
    severity: str
    description: str
    query: str


@dataclass(frozen=True)
class Result:
    check: Check
    failing_rows: int
    sample: list[dict]

    @property
    def status(self) -> str:
        if self.failing_rows == 0:
            return "pass"
        return "fail" if self.check.severity == "error" else "warn"


class DataQualityError(RuntimeError):
    pass


def parse_check(path: Path, layer: str) -> Check:
    text = path.read_text(encoding="utf-8")
    meta: dict[str, str] = {}
    for line in text.splitlines():
        match = HEADER_RE.match(line)
        if match:
            meta[match["key"]] = match["value"]
        elif line.strip() and not line.lstrip().startswith("--"):
            break
    severity = meta.get("severity", "")
    if severity not in SEVERITIES:
        raise ValueError(f"{path}: header '-- severity:' must be one of {SEVERITIES}")
    if "description" not in meta:
        raise ValueError(f"{path}: header '-- description:' is required")
    query = text.strip().rstrip(";")
    return Check(f"{layer}.{path.stem}", layer, severity, meta["description"], query)


def discover(layer: str, root: Path | None = None) -> list[Check]:
    directory = (root or settings.WAREHOUSE_DIR / "tests") / layer
    checks = [parse_check(p, layer) for p in sorted(directory.glob("*.sql"))]
    if not checks:
        raise FileNotFoundError(f"No data-quality checks found in {directory}")
    return checks


def execute(conn: psycopg.Connection, check: Check) -> Result:
    inner = sql.SQL(check.query)  # trusted: checks are files in this repository
    count = conn.execute(sql.SQL("SELECT count(*) FROM ({}) AS q").format(inner)).fetchone()[0]
    sample: list[dict] = []
    if count:
        rows = conn.execute(
            sql.SQL("SELECT row_to_json(q)::text FROM ({}) AS q LIMIT {}").format(
                inner, sql.Literal(SAMPLE_SIZE)
            )
        ).fetchall()
        sample = [json.loads(r[0]) for r in rows]
    return Result(check, count, sample)


def record(conn: psycopg.Connection, run_id: str, results: list[Result]) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO audit.dq_results"
            " (run_id, check_name, layer, severity, status, failing_rows, description, sample)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            [
                (
                    run_id,
                    r.check.name,
                    r.check.layer,
                    r.check.severity,
                    r.status,
                    r.failing_rows,
                    r.check.description,
                    json.dumps(r.sample, default=str) if r.sample else None,
                )
                for r in results
            ],
        )


def run_layer(conn: psycopg.Connection, layer: str, run_id: str) -> list[Result]:
    """Run every check of a layer, persist the results and return them."""
    results = [execute(conn, check) for check in discover(layer)]
    record(conn, run_id, results)
    conn.commit()
    for r in results:
        log.log(
            logging.INFO if r.status == "pass" else logging.WARNING,
            "[%s] %s - %d violating rows",
            r.status.upper(),
            r.check.name,
            r.failing_rows,
        )
    return results


def enforce(results: list[Result]) -> None:
    failed = [r for r in results if r.status == "fail"]
    if failed:
        names = ", ".join(f"{r.check.name} ({r.failing_rows})" for r in failed)
        raise DataQualityError(f"{len(failed)} error-level check(s) failed: {names}")
