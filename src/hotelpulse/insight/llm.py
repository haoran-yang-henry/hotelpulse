"""Minimal client for any OpenAI-compatible Chat Completions endpoint.

Configured with ``LLM_BASE_URL``, ``LLM_API_KEY`` and ``LLM_MODEL`` - by default OpenCode
serving ``deepseek-v4-pro``; OpenAI, DeepSeek or a local server (Ollama, vLLM) work the same.
Optional: ``LLM_REASONING_EFFORT`` (e.g. ``none`` for fast answers from reasoning models) and
``LLM_SESSION_HEADER`` - the header OpenCode Go uses to route a session's requests together.
"""

import os
import uuid
from dataclasses import dataclass

import httpx

DEFAULT_BASE_URL = "https://opencode.ai/zen/v1"
DEFAULT_MODEL = "deepseek-v4-pro"


class LLMError(RuntimeError):
    pass


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    timeout_s: float = 120
    reasoning_effort: str | None = None
    session_header: str | None = None

    @classmethod
    def from_env(cls) -> "LLMConfig | None":
        key = os.environ.get("LLM_API_KEY", "").strip()
        if not key:
            return None
        return cls(
            base_url=os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
            api_key=key,
            model=os.environ.get("LLM_MODEL", DEFAULT_MODEL),
            timeout_s=float(os.environ.get("LLM_TIMEOUT_S", "120")),
            reasoning_effort=os.environ.get("LLM_REASONING_EFFORT") or None,
            session_header=os.environ.get("LLM_SESSION_HEADER") or None,
        )


@dataclass(frozen=True)
class Completion:
    content: str
    prompt_tokens: int
    completion_tokens: int


class ChatClient:
    def __init__(self, cfg: LLMConfig, transport: httpx.BaseTransport | None = None) -> None:
        self.cfg = cfg
        self.model = cfg.model
        headers = {"Authorization": f"Bearer {cfg.api_key}"}
        if cfg.session_header:  # one session per service process
            headers[cfg.session_header] = f"hotelpulse-insight-{uuid.uuid4()}"
        self.http = httpx.Client(
            base_url=cfg.base_url, timeout=cfg.timeout_s, headers=headers, transport=transport
        )

    def complete(self, messages: list[dict[str, str]]) -> Completion:
        """JSON-mode completion; retried without optional parameters if a provider rejects them."""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        if self.cfg.reasoning_effort:
            payload["reasoning_effort"] = self.cfg.reasoning_effort
        try:
            response = self.http.post("/chat/completions", json=payload)
            if response.status_code == 400:
                minimal = {"model": self.model, "messages": messages}
                response = self.http.post("/chat/completions", json=minimal)
        except httpx.HTTPError as exc:
            raise LLMError(f"request failed: {exc}") from exc
        if response.is_error:
            raise LLMError(f"HTTP {response.status_code}: {response.text[:300]}")
        body = response.json()
        try:
            content = body["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"unexpected response: {str(body)[:300]}") from exc
        if not content.strip():
            raise LLMError("empty answer")
        usage = body.get("usage") or {}
        return Completion(
            content, int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
        )
