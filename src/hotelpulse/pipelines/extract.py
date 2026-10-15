"""Database-to-database extraction into the raw layer, streamed with COPY."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import psycopg
from psycopg import sql

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceTable:
    """A source table and the raw table it lands in.

    ``incremental_column`` set  -> rows changed inside the extraction window are copied.
    ``incremental_column`` None -> the whole table is copied (small reference data).
    """

    name: str
    source: str
    target: str
    columns: tuple[str, ...]
    incremental_column: str | None = None


@dataclass(frozen=True)
class Window:
    start: datetime | None  # None = from the beginning (full load)
    end: datetime

    @property
    def mode(self) -> str:
        return "full" if self.start is None else "incremental"


def extraction_window(
    interval_start: datetime,
    interval_end: datetime,
    lookback: timedelta,
    full_refresh: bool,
    target_is_empty: bool,
    now: datetime,
) -> Window:
    """Window of `updated_at` values to extract for one run.

    Incremental runs read the data interval plus a look-back period, so rows committed late
    in the source are not missed; duplicates are harmless because staging merges on the
    natural key. A full load (empty target or explicit refresh) reads everything up to *now*:
    the source keeps only the current version of a row, so a row last changed after the
    interval end would otherwise be missing - not just stale - until the next run.
    """
    if full_refresh or target_is_empty:
        return Window(None, now)
    return Window(interval_start - lookback, interval_end)


def build_select(table: SourceTable, window: Window, batch_id: str, extracted_at: datetime):
    columns = sql.SQL(", ").join(sql.Identifier(c) for c in table.columns)
    query = sql.SQL("SELECT {cols}, {batch} AS _batch_id, {ts} AS _extracted_at FROM {src}").format(
        cols=columns,
        batch=sql.Literal(batch_id),
        ts=sql.Literal(extracted_at),
        src=sql.Identifier(*table.source.split(".")),
    )
    if table.incremental_column:
        col = sql.Identifier(table.incremental_column)
        conditions = [sql.SQL("{} < {}").format(col, sql.Literal(window.end))]
        if window.start is not None:
            conditions.insert(0, sql.SQL("{} >= {}").format(col, sql.Literal(window.start)))
        query += sql.SQL(" WHERE ") + sql.SQL(" AND ").join(conditions)
    return query


def copy_to_raw(
    source: psycopg.Connection,
    target: psycopg.Connection,
    table: SourceTable,
    window: Window,
    batch_id: str,
    extracted_at: datetime,
) -> int:
    """Stream the selected source rows into the raw table. Returns the number of rows.

    Rows of an earlier attempt of the same batch are deleted first (same transaction), so
    re-running a DAG run does not duplicate the raw change log.
    """
    target.execute(
        sql.SQL("DELETE FROM {} WHERE _batch_id = %s").format(
            sql.Identifier(*table.target.split("."))
        ),
        (batch_id,),
    )
    select = build_select(table, window, batch_id, extracted_at)
    target_cols = sql.SQL(", ").join(
        sql.Identifier(c) for c in (*table.columns, "_batch_id", "_extracted_at")
    )
    copy_out = sql.SQL("COPY ({}) TO STDOUT").format(select)
    copy_in = sql.SQL("COPY {} ({}) FROM STDIN").format(
        sql.Identifier(*table.target.split(".")), target_cols
    )
    with source.cursor() as src_cur, target.cursor() as dst_cur:
        with src_cur.copy(copy_out) as reader, dst_cur.copy(copy_in) as writer:
            for chunk in reader:
                writer.write(chunk)
        rows = dst_cur.rowcount
    log.info("%s: %d rows (%s, %s .. %s)", table.name, rows, window.mode, window.start, window.end)
    return rows


def log_load(
    conn: psycopg.Connection, run_id: str, dataset: str, window: Window, rows: int
) -> None:
    conn.execute(
        "INSERT INTO audit.load_log (run_id, dataset, mode, window_start, window_end, rows_loaded)"
        " VALUES (%s, %s, %s, %s, %s, %s)",
        (run_id, dataset, window.mode, window.start, window.end, rows),
    )
