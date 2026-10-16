"""Thin Metabase REST API client shared by provisioning and the insight service."""

import time
from typing import Any

import httpx


class MetabaseError(RuntimeError):
    pass


class MetabaseClient:
    def __init__(self, url: str, timeout_s: float = 60) -> None:
        self.url = url.rstrip("/")
        self.http = httpx.Client(base_url=self.url, timeout=timeout_s)

    def _call(self, method: str, path: str, **kwargs) -> Any:
        response = self.http.request(method, f"/api{path}", **kwargs)
        if response.is_error:
            raise MetabaseError(f"{method} {path} -> {response.status_code}: {response.text[:500]}")
        return response.json() if response.content else None

    def get(self, path: str, **kw) -> Any:
        return self._call("GET", path, **kw)

    def post(self, path: str, body: Any = None) -> Any:
        return self._call("POST", path, json=body)

    def put(self, path: str, body: Any) -> Any:
        return self._call("PUT", path, json=body)

    def delete(self, path: str) -> Any:
        return self._call("DELETE", path)

    def wait_until_healthy(self, timeout_s: int = 600) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                if self.http.get("/api/health").json().get("status") == "ok":
                    return
            except (httpx.HTTPError, ValueError):
                pass
            time.sleep(5)
        raise TimeoutError("Metabase did not become healthy")

    def login(self, email: str, password: str) -> None:
        session = self.post("/session", {"username": email, "password": password})
        self.http.headers["X-Metabase-Session"] = session["id"]

    def run_dashcard(
        self, dashboard_id: int, dashcard_id: int, card_id: int, parameters: list[dict]
    ) -> dict:
        """Run a dashboard card exactly as the dashboard does, with the given filter values."""
        result = self.post(
            f"/dashboard/{dashboard_id}/dashcard/{dashcard_id}/card/{card_id}/query",
            {"parameters": parameters},
        )
        if result.get("error"):
            raise MetabaseError(f"Query failed: {str(result['error'])[:300]}")
        return result
