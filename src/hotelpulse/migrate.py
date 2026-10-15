"""Minimal, checksum-verified SQL migration runner for the warehouse.

Migrations live in ``warehouse/migrations`` and are named ``V###__description.sql``.
Each file runs in its own transaction; applied versions are recorded in
``audit.schema_migrations``. Editing an already-applied file is an error.
"""

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import psycopg

from hotelpulse import settings

log = logging.getLogger(__name__)

FILENAME_RE = re.compile(r"^V(?P<version>\d{3})__(?P<name>[a-z0-9_]+)\.sql$")
LOCK_ID = 7_310_001  # pg_advisory_lock key: one migration run at a time

BOOTSTRAP_SQL = """
CREATE SCHEMA IF NOT EXISTS audit;
CREATE TABLE IF NOT EXISTS audit.schema_migrations (
    version     integer PRIMARY KEY,
    name        text NOT NULL,
    checksum    text NOT NULL,
    applied_at  timestamptz NOT NULL DEFAULT now()
);
"""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path

    @property
    def sql(self) -> str:
        return self.path.read_text(encoding="utf-8")

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()


class MigrationError(RuntimeError):
    pass


def discover(directory: Path) -> list[Migration]:
    migrations = []
    for path in sorted(directory.glob("*.sql")):
        match = FILENAME_RE.match(path.name)
        if not match:
            raise MigrationError(f"Invalid migration filename: {path.name}")
        migrations.append(Migration(int(match["version"]), match["name"], path))
    versions = [m.version for m in migrations]
    if len(versions) != len(set(versions)):
        raise MigrationError(f"Duplicate migration versions in {directory}")
    return migrations


def pending(migrations: list[Migration], applied: dict[int, str]) -> list[Migration]:
    """Return migrations not yet applied; fail if an applied one was modified."""
    for m in migrations:
        if m.version in applied and applied[m.version] != m.checksum:
            raise MigrationError(
                f"V{m.version:03d} ({m.name}) was modified after being applied; "
                "add a new migration instead."
            )
    return [m for m in migrations if m.version not in applied]


def run(dsn: str, directory: Path | None = None) -> list[Migration]:
    directory = directory or settings.WAREHOUSE_DIR / "migrations"
    migrations = discover(directory)
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (LOCK_ID,))
        try:
            conn.execute(BOOTSTRAP_SQL)
            rows = conn.execute("SELECT version, checksum FROM audit.schema_migrations").fetchall()
            todo = pending(migrations, dict(rows))
            for m in todo:
                log.info("Applying V%03d %s", m.version, m.name)
                with conn.transaction():
                    conn.execute(m.sql)
                    conn.execute(
                        "INSERT INTO audit.schema_migrations (version, name, checksum)"
                        " VALUES (%s, %s, %s)",
                        (m.version, m.name, m.checksum),
                    )
            log.info("Warehouse schema up to date (%d applied now)", len(todo))
            return todo
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(settings.dwh_dsn())
