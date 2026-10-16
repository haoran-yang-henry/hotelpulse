"""Persistence in schema ``insight``: explanation cache, request log and feedback."""

from typing import Any

import psycopg
from psycopg.types.json import Jsonb


class Store:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self.dsn, autocommit=True)

    def get(self, cache_key: str) -> tuple[int, dict[str, Any]] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT explanation_id, response FROM insight.explanations WHERE cache_key = %s",
                (cache_key,),
            ).fetchone()
        return (row[0], row[1]) if row else None

    def save(self, cache_key: str, record: dict[str, Any], response: dict[str, Any]) -> int:
        with self._connect() as conn:
            return conn.execute(
                """
                INSERT INTO insight.explanations (
                    cache_key, dashboard_id, card_id, card_name, parameters, data_hash, lang,
                    mode, model, prompt_version, verified, unverified_numbers, attempts,
                    prompt_tokens, completion_tokens, latency_ms, error, response
                ) VALUES (
                    %(cache_key)s, %(dashboard_id)s, %(card_id)s, %(card_name)s, %(parameters)s,
                    %(data_hash)s, %(lang)s, %(mode)s, %(model)s, %(prompt_version)s,
                    %(verified)s, %(unverified_numbers)s, %(attempts)s, %(prompt_tokens)s,
                    %(completion_tokens)s, %(latency_ms)s, %(error)s, %(response)s
                )
                ON CONFLICT (cache_key) DO UPDATE SET response = excluded.response
                RETURNING explanation_id
                """,
                {
                    **record,
                    "cache_key": cache_key,
                    "parameters": Jsonb(record["parameters"]),
                    "response": Jsonb(response),
                },
            ).fetchone()[0]

    def log_request(self, explanation_id: int, cache_hit: bool) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO insight.requests (explanation_id, cache_hit) VALUES (%s, %s)",
                (explanation_id, cache_hit),
            )

    def add_feedback(self, explanation_id: int, helpful: bool, comment: str | None) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO insight.feedback (explanation_id, helpful, comment)"
                " VALUES (%s, %s, %s)",
                (explanation_id, helpful, comment),
            )
