"""Explain one dashboard chart: filters -> query -> facts -> narrative, with caching."""

import hashlib
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from hotelpulse.insight import facts, filters, narrative
from hotelpulse.insight.llm import ChatClient, LLMConfig
from hotelpulse.insight.store import Store
from hotelpulse.metabase import specs
from hotelpulse.metabase.client import MetabaseClient, MetabaseError

log = logging.getLogger("hotelpulse.insight")

# bump when facts or the response format change: cached explanations are keyed on it
FACTS_VERSION = "2026-10-16.4"
DASHBOARD_TTL_S = 60


class NotFound(LookupError):
    pass


@dataclass(frozen=True)
class Request:
    dashboard_id: int
    card_id: int
    filters: dict[str, list[str]]  # by parameter slug; display or raw values
    lang: str = "en"


def resolve_parameters(
    dashboard: dict, dashcard: dict, given: dict[str, list[str]]
) -> tuple[list[dict], list[str]]:
    """Metabase query parameters for a dashcard, plus a human-readable filter description.

    A filter present in the request but unset (``{{period}}``) was cleared by the user and is
    not applied; a filter absent from the request falls back to the dashboard default.
    """
    by_id = {p["id"]: p for p in dashboard.get("parameters", [])}
    query_params, described = [], []
    for mapping in dashcard.get("parameter_mappings", []):
        param = by_id.get(mapping["parameter_id"])
        if param is None:
            continue
        values = given.get(param["slug"])
        if values is None:
            raw, shown = param.get("default"), param.get("default")
        else:
            raw = filters.to_raw(param["type"], values)
            shown = ", ".join(v for v in values if not filters.is_unset(v)) or None
        if raw in (None, [], ""):
            described.append(f"{param['name']}: all")
            continue
        query_params.append(
            {"id": param["id"], "type": param["type"], "value": raw, "target": mapping["target"]}
        )
        described.append(f"{param['name']}: {shown if isinstance(shown, str) else raw}")
    return query_params, described


class InsightService:
    def __init__(
        self,
        metabase: MetabaseClient,
        credentials: tuple[str, str],
        store: Store | None,
        chat: ChatClient | None,
    ) -> None:
        self.metabase, self.credentials = metabase, credentials
        self.store, self.chat = store, chat
        self._dashboards: dict[int, tuple[float, dict]] = {}
        self._lock = threading.Lock()
        self._logged_in = False

    @classmethod
    def from_env(cls) -> "InsightService":
        cfg = LLMConfig.from_env()
        dsn = os.environ.get("HOTELPULSE_INSIGHT_DSN")
        return cls(
            MetabaseClient(os.environ.get("MB_URL", "http://localhost:3001")),
            (
                os.environ.get("MB_INSIGHT_EMAIL", "insight.service@example.com"),
                os.environ.get("MB_INSIGHT_PASSWORD", ""),
            ),
            Store(dsn) if dsn else None,
            ChatClient(cfg) if cfg else None,
        )

    # ------------------------------------------------------------------ metabase
    def _call(self, fn, *args):
        with self._lock:
            if not self._logged_in:
                self.metabase.login(*self.credentials)
                self._logged_in = True
        try:
            return fn(*args)
        except MetabaseError as exc:
            if " 401" not in str(exc):
                raise
            with self._lock:  # session expired
                self.metabase.login(*self.credentials)
            return fn(*args)

    def dashboard(self, dashboard_id: int) -> dict:
        cached = self._dashboards.get(dashboard_id)
        if cached and time.monotonic() - cached[0] < DASHBOARD_TTL_S:
            return cached[1]
        try:
            dash = self._call(self.metabase.get, f"/dashboard/{dashboard_id}")
        except MetabaseError as exc:
            raise NotFound(f"dashboard {dashboard_id}") from exc
        self._dashboards[dashboard_id] = (time.monotonic(), dash)
        return dash

    # ------------------------------------------------------------------ explain
    def explain(self, req: Request) -> dict[str, Any]:
        started = time.monotonic()
        dash = self.dashboard(req.dashboard_id)
        dashcard = next((d for d in dash["dashcards"] if d.get("card_id") == req.card_id), None)
        if dashcard is None:
            raise NotFound(f"card {req.card_id} on dashboard {req.dashboard_id}")
        card = dashcard["card"]
        params, described = resolve_parameters(dash, dashcard, req.filters)
        result = self._call(
            self.metabase.run_dashcard, dash["id"], dashcard["id"], card["id"], params
        )

        spec = specs.card_specs().get((dash["name"], card["name"]))
        explain_spec = spec.explain if spec else {}
        sheet = facts.extract(card, result, explain_spec)
        columns = [c["name"] for c in result["data"]["cols"]]
        context = {
            "description": card.get("description") or "",
            "intent": explain_spec.get("intent", ""),
            "filters": "; ".join(described) or "none",
            "glossary": specs.relevant_glossary(
                card["name"], card.get("description") or "", *columns
            ),
        }
        rows_json = json.dumps(result["data"]["rows"], default=str, sort_keys=True)
        data_hash = hashlib.sha256(rows_json.encode()).hexdigest()
        model = self.chat.model if self.chat else "template"
        cache_key = hashlib.sha256(
            json.dumps(
                [req.card_id, req.dashboard_id, params, data_hash, model,
                 narrative.PROMPT_VERSION, FACTS_VERSION, req.lang],
                default=str,
            ).encode()
        ).hexdigest()  # fmt: skip

        if self.store:
            hit = self.store.get(cache_key)
            if hit:
                explanation_id, response = hit
                self.store.log_request(explanation_id, cache_hit=True)
                response["explanation_id"] = explanation_id
                response["filters"] = described  # as this caller wrote them (display vs raw)
                response["meta"] |= {
                    "cache_hit": True,
                    "latency_ms": round((time.monotonic() - started) * 1000),
                }
                return response

        out = narrative.generate(sheet, context, req.lang, self.chat)
        latency_ms = round((time.monotonic() - started) * 1000)
        checked = sum(len(narrative.extract_numbers(t)) for t in out.narrative.texts())
        response = {
            "explanation_id": None,
            "chart": {
                "title": card["name"],
                "dashboard": dash["name"],
                "description": card.get("description") or "",
                "display": card.get("display"),
            },
            "filters": described,
            "narrative": out.narrative.model_dump(),
            "facts": [
                {"id": f.id, "kind": f.kind, "text": f.text, "meta": f.meta} for f in sheet.facts
            ],
            "verification": {
                "verified": out.verified,
                "numbers_checked": checked,
                "unverified": out.unverified,
            },
            "meta": {
                "mode": out.mode,
                "model": out.model,
                "lang": req.lang,
                "cache_hit": False,
                "latency_ms": latency_ms,
                "prompt_tokens": out.prompt_tokens,
                "completion_tokens": out.completion_tokens,
                "attempts": out.attempts,
                "error": out.error,
                "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            },
        }
        if self.store:
            record = {
                "dashboard_id": req.dashboard_id,
                "card_id": req.card_id,
                "card_name": card["name"],
                "parameters": params,
                "data_hash": data_hash,
                "lang": req.lang,
                "mode": out.mode,
                "model": out.model,
                "prompt_version": narrative.PROMPT_VERSION,
                "verified": out.verified,
                "unverified_numbers": out.unverified,
                "attempts": out.attempts,
                "prompt_tokens": out.prompt_tokens,
                "completion_tokens": out.completion_tokens,
                "latency_ms": latency_ms,
                "error": out.error,
            }
            # Reuse only answers worth repeating: verified model output, or the template when no
            # model is configured. Others are stored for analysis under a one-off key.
            reusable = (out.mode == "llm" and out.verified) or (
                out.mode == "template" and not self.chat
            )
            key = cache_key if reusable else f"{cache_key}:{uuid.uuid4()}"
            explanation_id = self.store.save(key, record, response)
            response["explanation_id"] = explanation_id
            self.store.log_request(explanation_id, cache_hit=False)
        return response
