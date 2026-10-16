"""Landing zone for file-based ingestion (see ADR-0011).

Files are gzip-compressed JSON lines, partitioned by the hour they were *received*:
``<dataset>/dt=YYYY-MM-DD/hour=HH/part-<timestamp>-<id>.jsonl.gz``. Writers create a
``.tmp`` file and atomically rename it, so readers never see a partial file. Locally the
landing zone is a directory; in production this module is the one place to swap for an
object store (S3/GCS).
"""

import gzip
import json
import threading
from collections import defaultdict
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

WEB_EVENTS = "web_events"
WEB_EVENTS_REJECTED = "web_events_rejected"
INVENTORY = "inventory"  # daily consumables export
REVIEWS = "reviews"  # daily review-platform export
FILE_GLOB = "dt=*/hour=*/*.jsonl.gz"


def partition(received_at: datetime) -> str:
    ts = received_at.astimezone(UTC)
    return f"dt={ts:%Y-%m-%d}/hour={ts:%H}"


def write_file(directory: Path, lines: list[str]) -> Path:
    """Write one immutable landing file atomically and return its path."""
    directory.mkdir(parents=True, exist_ok=True)
    name = f"part-{datetime.now(UTC):%Y%m%dT%H%M%S%f}-{uuid4().hex[:8]}.jsonl.gz"
    target = directory / name
    tmp = directory / f".{name}.tmp"
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    tmp.replace(target)  # atomic rename within the same directory
    return target


class LandingWriter:
    """Buffers records per hourly partition and flushes them as landing files. Thread-safe."""

    def __init__(self, directory: Path, max_buffered: int = 2000) -> None:
        self.directory = directory
        self.max_buffered = max_buffered
        self._buffers: dict[str, list[str]] = defaultdict(list)
        self._count = 0
        self._lock = threading.Lock()

    def add_many(self, records: Iterable[dict], received_at: datetime) -> None:
        lines = [json.dumps(r, separators=(",", ":"), ensure_ascii=False) for r in records]
        if not lines:
            return
        with self._lock:
            self._buffers[partition(received_at)].extend(lines)
            self._count += len(lines)
            full = self._count >= self.max_buffered
        if full:
            self.flush()

    def flush(self) -> list[Path]:
        with self._lock:
            buffers, self._buffers, self._count = self._buffers, defaultdict(list), 0
        return [
            write_file(self.directory / part, lines) for part, lines in buffers.items() if lines
        ]


def list_files(directory: Path) -> list[Path]:
    """All complete landing files of a dataset, oldest partition first."""
    return sorted(directory.glob(FILE_GLOB))


def read_lines(path: Path) -> Iterator[str]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield line.rstrip("\n")
