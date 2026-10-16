"""Exactly-once loading of landing-zone files into the raw layer (ADR-0011).

Each file is loaded in its own transaction together with its manifest entry in
``audit.loaded_files``: a file is either fully loaded and registered, or not at all. Files
that arrive late are simply picked up by the next run.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg import sql

from hotelpulse import landing

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FileDataset:
    name: str  # directory in the landing zone
    table: str  # raw table with (payload, _file, _line, _batch_id)


WEB_DATASETS = (
    FileDataset(landing.WEB_EVENTS, "raw.web_events"),
    FileDataset(landing.WEB_EVENTS_REJECTED, "raw.web_events_rejected"),
)
OPERATIONS_DATASETS = (
    FileDataset(landing.INVENTORY, "raw.inventory_usage"),
    FileDataset(landing.REVIEWS, "raw.reviews"),
)
ALL_DATASETS = WEB_DATASETS + OPERATIONS_DATASETS


def pending_files(
    conn: psycopg.Connection, root: Path, dataset: FileDataset, limit: int
) -> list[tuple[str, Path]]:
    """Landing files of a dataset that are not in the manifest yet, oldest first."""
    loaded = {
        row[0]
        for row in conn.execute(
            "SELECT file_key FROM audit.loaded_files WHERE dataset = %s", (dataset.name,)
        )
    }
    files = ((f.relative_to(root).as_posix(), f) for f in landing.list_files(root / dataset.name))
    return [(key, path) for key, path in files if key not in loaded][:limit]


def load_file(
    conn: psycopg.Connection, dataset: FileDataset, key: str, path: Path, batch_id: str
) -> int:
    """Load one file and register it, atomically. Requires an autocommit connection."""
    table = sql.Identifier(*dataset.table.split("."))
    rows = 0
    with conn.transaction():
        conn.execute(sql.SQL("DELETE FROM {} WHERE _file = %s").format(table), (key,))
        with (
            conn.cursor() as cur,
            cur.copy(
                sql.SQL("COPY {} (payload, _file, _line, _batch_id) FROM STDIN").format(table)
            ) as copy,
        ):
            for rows, line in enumerate(landing.read_lines(path), start=1):
                copy.write_row((line, key, rows, batch_id))
        conn.execute(
            "INSERT INTO audit.loaded_files (file_key, dataset, file_bytes, rows_loaded, batch_id)"
            " VALUES (%s, %s, %s, %s, %s)",
            (key, dataset.name, path.stat().st_size, rows, batch_id),
        )
    return rows


def load_pending(
    conn: psycopg.Connection,
    root: Path,
    batch_id: str,
    datasets: Iterable[FileDataset] = WEB_DATASETS,
    limit: int = 10_000,
) -> dict[str, dict[str, int]]:
    """Load every pending file of the given datasets. Returns files/rows per dataset."""
    if not conn.autocommit:
        raise ValueError("load_pending needs an autocommit connection (one transaction per file)")
    summary = {}
    for dataset in datasets:
        files = pending_files(conn, root, dataset, limit)
        rows = sum(load_file(conn, dataset, key, path, batch_id) for key, path in files)
        summary[dataset.name] = {"files": len(files), "rows": rows}
        log.info("%s: loaded %d files, %d rows", dataset.name, len(files), rows)
    return summary
