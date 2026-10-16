"""Insight service HTTP API and the "Explain this chart" page.

Run with ``uvicorn --factory hotelpulse.insight.app:create_app``.

* ``GET /explain?dashboard=..&card=..&<filter slug>=<value>`` - page opened from Metabase
* ``GET /api/explain`` - same parameters, JSON (also accepts raw filter values)
* ``POST /api/feedback`` - ``{"explanation_id": 1, "helpful": true, "comment": "..."}``
"""

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from hotelpulse.insight import narrative
from hotelpulse.insight.service import InsightService, NotFound
from hotelpulse.insight.service import Request as ExplainRequest
from hotelpulse.metabase.client import MetabaseError

HERE = Path(__file__).parent
RESERVED = {"dashboard", "card", "lang"}
log = logging.getLogger("hotelpulse.insight")


class Feedback(BaseModel):
    explanation_id: int
    helpful: bool
    comment: str | None = Field(None, max_length=1000)


def parse_request(request: Request) -> ExplainRequest:
    q = request.query_params
    try:
        dashboard_id, card_id = int(q["dashboard"]), int(q["card"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, "dashboard and card must be integers") from exc
    lang = q.get("lang", "en")
    if lang not in narrative.LANGUAGES:
        lang = "en"
    given: dict[str, list[str]] = {}
    for key, value in q.multi_items():
        if key not in RESERVED:
            given.setdefault(key, []).append(value)
    return ExplainRequest(dashboard_id, card_id, given, lang)


def create_app(service: InsightService | None = None) -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    app = FastAPI(title="HotelPulse insight service", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")
    svc = service or InsightService.from_env()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "llm": svc.chat.model if svc.chat else "disabled"}

    @app.get("/explain", response_class=HTMLResponse)
    def page(request: Request) -> HTMLResponse:
        parse_request(request)  # validate early
        return templates.TemplateResponse(
            request, "explain.html", {"languages": narrative.LANGUAGES}
        )

    @app.get("/api/explain")
    def explain(request: Request) -> JSONResponse:
        req = parse_request(request)
        try:
            return JSONResponse(svc.explain(req))
        except NotFound as exc:
            raise HTTPException(404, f"Not found: {exc}") from exc
        except MetabaseError as exc:
            log.warning("Metabase error: %s", exc)
            raise HTTPException(502, "Metabase could not run the chart's query.") from exc

    @app.post("/api/feedback")
    def feedback(body: Feedback) -> dict[str, str]:
        if svc.store is None:
            raise HTTPException(503, "feedback storage is not configured")
        svc.store.add_feedback(body.explanation_id, body.helpful, body.comment)
        return {"status": "thanks"}

    return app
