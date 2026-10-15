"""Event collector: receives tracker batches, validates them, writes the landing zone.

Run with ``uvicorn --factory hotelpulse.tracking.collector:create_app``.

* ``POST /collect`` - body ``{"events": [...]}`` (sent as ``text/plain`` so browsers treat it
  as a simple CORS request and ``navigator.sendBeacon`` works). Each event is validated on
  its own: valid events are enriched with the collector timestamp and user agent, invalid
  ones go to the dead-letter dataset together with the validation error.
* ``GET /tracker.js`` - the JavaScript tracker, served like any analytics vendor's snippet.
* ``GET /health``

No IP address is stored.
"""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError

from hotelpulse import landing, settings
from hotelpulse.tracking.schema import MAX_BATCH_SIZE, TrackingEvent

log = logging.getLogger("hotelpulse.collector")

STATIC_DIR = Path(__file__).with_name("static")
FLUSH_INTERVAL_S = 5.0


def process(
    raw_events: list[Any], user_agent: str | None, collector_ts: datetime
) -> tuple[list[dict], list[dict]]:
    """Validate and enrich a batch. Returns (accepted_records, rejected_records)."""
    received = collector_ts.astimezone(UTC).isoformat()
    accepted: list[dict] = []
    rejected: list[dict] = []
    for raw in raw_events:
        try:
            event = TrackingEvent.model_validate(raw)
        except ValidationError as exc:
            first = exc.errors()[0]
            error = f"{'.'.join(str(p) for p in first['loc']) or 'event'}: {first['msg']}"
            rejected.append(
                {"collector_ts": received, "user_agent": user_agent, "error": error, "payload": raw}
            )
            continue
        record = event.model_dump(mode="json")
        record["collector_ts"] = received
        record["user_agent"] = user_agent
        accepted.append(record)
    return accepted, rejected


def create_app(landing_root: Path | None = None) -> FastAPI:
    root = landing_root or settings.landing_dir()
    events_writer = landing.LandingWriter(root / landing.WEB_EVENTS)
    rejected_writer = landing.LandingWriter(root / landing.WEB_EVENTS_REJECTED)

    def flush() -> None:
        events_writer.flush()
        rejected_writer.flush()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        async def flush_periodically() -> None:
            while True:
                await asyncio.sleep(FLUSH_INTERVAL_S)
                flush()

        task = asyncio.create_task(flush_periodically())
        yield
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        flush()

    app = FastAPI(title="HotelPulse event collector", lifespan=lifespan)
    origins = [o for o in os.environ.get("COLLECTOR_ALLOWED_ORIGINS", "*").split(",") if o]
    app.add_middleware(
        CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["*"]
    )
    app.state.flush = flush

    @app.post("/collect")
    async def collect(request: Request) -> JSONResponse:
        try:
            body = json.loads(await request.body())
        except ValueError:
            return JSONResponse({"error": "body must be JSON"}, status_code=400)
        events = body.get("events") if isinstance(body, dict) else None
        if not isinstance(events, list) or not 0 < len(events) <= MAX_BATCH_SIZE:
            return JSONResponse(
                {"error": f"expected 1-{MAX_BATCH_SIZE} events under 'events'"}, status_code=400
            )
        now = datetime.now(UTC)
        accepted, rejected = process(events, request.headers.get("user-agent"), now)
        events_writer.add_many(accepted, now)
        rejected_writer.add_many(rejected, now)
        return JSONResponse({"accepted": len(accepted), "rejected": len(rejected)})

    @app.get("/tracker.js")
    async def tracker() -> FileResponse:
        return FileResponse(
            STATIC_DIR / "tracker.js",
            media_type="application/javascript",
            headers={"Cache-Control": "public, max-age=300"},
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
