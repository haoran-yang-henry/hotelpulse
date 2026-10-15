"""Dashboards as code: provision Metabase from ``bi/metabase`` through its REST API.

Idempotent - safe to run on every start:

1. complete the first-run setup (admin account) or log in;
2. register the warehouse with the read-only ``bi_reader`` role (schemas core, marts, audit);
3. wait for the metadata sync, resolve field ids for field filters;
4. create or update the collection, the native-SQL questions and the dashboards (matched by name).
"""

import logging
import os
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml

from hotelpulse import settings
from hotelpulse.settings import require_env

log = logging.getLogger("hotelpulse.metabase")

COLLECTION_NAME = "HotelPulse"
DATABASE_NAME = "HotelPulse Warehouse"
DEFINITIONS_DIR = settings.BI_DIR / "metabase"
WIDGET_TYPES = {"string/=": "string/=", "date/all-options": "date/all-options"}


@dataclass(frozen=True)
class Config:
    url: str
    admin_email: str
    admin_password: str
    dwh_host: str
    dwh_port: int
    dwh_password: str

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            url=os.environ.get("MB_URL", "http://localhost:3001"),
            admin_email=require_env("MB_ADMIN_EMAIL"),
            admin_password=require_env("MB_ADMIN_PASSWORD"),
            dwh_host=os.environ.get("MB_DWH_HOST", "postgres"),
            dwh_port=int(os.environ.get("MB_DWH_PORT", "5432")),
            dwh_password=require_env("BI_READER_PASSWORD"),
        )


class MetabaseClient:
    def __init__(self, url: str) -> None:
        self.http = httpx.Client(base_url=url.rstrip("/"), timeout=60)

    def _call(self, method: str, path: str, **kwargs) -> Any:
        response = self.http.request(method, f"/api{path}", **kwargs)
        if response.is_error:
            raise RuntimeError(f"{method} {path} -> {response.status_code}: {response.text[:500]}")
        return response.json() if response.content else None

    def get(self, path: str, **kw) -> Any:
        return self._call("GET", path, **kw)

    def post(self, path: str, body: Any = None) -> Any:
        return self._call("POST", path, json=body)

    def put(self, path: str, body: Any) -> Any:
        return self._call("PUT", path, json=body)

    # ------------------------------------------------------------------ session
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

    def setup_or_login(self, cfg: Config) -> bool:
        """Log in, running the first-time setup if needed. Returns True on a fresh instance."""
        props = self.get("/session/properties")
        fresh = not props.get("has-user-setup")
        if fresh:
            log.info("Running first-time setup")
            session = self.post(
                "/setup",
                {
                    "token": props["setup-token"],
                    "user": {
                        "email": cfg.admin_email,
                        "password": cfg.admin_password,
                        "first_name": "HotelPulse",
                        "last_name": "Admin",
                        "site_name": "HotelPulse",
                    },
                    "prefs": {
                        "site_name": "HotelPulse",
                        "site_locale": "en",
                        "allow_tracking": False,
                    },
                },
            )
        else:
            session = self.post(
                "/session", {"username": cfg.admin_email, "password": cfg.admin_password}
            )
        self.http.headers["X-Metabase-Session"] = session["id"]
        return fresh

    def remove_sample_content(self) -> None:
        """Drop Metabase's bundled sample database and example collection (fresh instance only)."""
        for db in self.get("/database")["data"]:
            if db.get("is_sample"):
                self._call("DELETE", f"/database/{db['id']}")
        for c in self.get("/collection"):
            if c.get("name") == "Examples" and not c.get("archived"):
                self.put(f"/collection/{c['id']}", {"archived": True})

    def set_homepage(self, dashboard_id: int) -> None:
        self.put("/setting/custom-homepage", {"value": True})
        self.put("/setting/custom-homepage-dashboard", {"value": dashboard_id})

    # ------------------------------------------------------------------ database
    def ensure_database(self, cfg: Config) -> int:
        details = {
            "host": cfg.dwh_host,
            "port": cfg.dwh_port,
            "dbname": "dwh",
            "user": "bi_reader",
            "password": cfg.dwh_password,
            "ssl": False,
            "tunnel-enabled": False,
            "advanced-options": True,
            "schema-filters-type": "inclusion",
            "schema-filters-patterns": "core,marts,audit",
        }
        existing = {db["name"]: db for db in self.get("/database")["data"]}
        if DATABASE_NAME in existing:
            db_id = existing[DATABASE_NAME]["id"]
            self.put(f"/database/{db_id}", {"details": details})
        else:
            log.info("Registering warehouse connection")
            db_id = self.post(
                "/database",
                {
                    "engine": "postgres",
                    "name": DATABASE_NAME,
                    "details": details,
                    "is_full_sync": True,
                },
            )["id"]
        self.post(f"/database/{db_id}/sync_schema")
        return db_id

    def field_ids(self, db_id: int, required: set[str], timeout_s: int = 300) -> dict[str, int]:
        """Map 'schema.table.column' -> field id, waiting for the sync to pick them up."""
        deadline = time.monotonic() + timeout_s
        while True:
            metadata = self.get(f"/database/{db_id}/metadata")
            ids = {
                f"{t['schema']}.{t['name']}.{f['name']}": f["id"]
                for t in metadata["tables"]
                for f in t["fields"]
            }
            missing = required - ids.keys()
            if not missing:
                return ids
            if time.monotonic() > deadline:
                raise TimeoutError(f"Fields not synced: {sorted(missing)}")
            time.sleep(5)

    # ------------------------------------------------------------------ content
    def ensure_collection(self, name: str) -> int:
        for c in self.get("/collection"):
            if (
                c.get("name") == name
                and not c.get("archived")
                and c.get("personal_owner_id") is None
            ):
                return c["id"]
        return self.post("/collection", {"name": name, "color": "#509EE3"})["id"]

    def items(self, collection_id: int, model: str) -> dict[str, int]:
        data = self.get(f"/collection/{collection_id}/items", params={"models": model})["data"]
        return {item["name"]: item["id"] for item in data}


# ---------------------------------------------------------------------- builders


def card_payload(
    card: dict, db_id: int, collection_id: int, fields: dict[str, int], params: dict[str, dict]
) -> dict:
    query = (DEFINITIONS_DIR / "cards" / card["sql"]).read_text(encoding="utf-8")
    template_tags = {
        tag: {
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{card['name']}/{tag}")),
            "name": tag,
            "display-name": params[tag]["name"],
            "type": "dimension",
            "dimension": ["field", fields[field], None],
            "widget-type": WIDGET_TYPES[params[tag]["type"]],
        }
        for tag, field in card.get("filters", {}).items()
    }
    viz: dict[str, Any] = dict(card.get("visualization", {}))
    if card.get("columns"):
        viz["column_settings"] = {
            f'["name","{column}"]': settings_ for column, settings_ in card["columns"].items()
        }
    return {
        "name": card["name"],
        "description": card.get("description"),
        "display": card["display"],
        "collection_id": collection_id,
        "visualization_settings": viz,
        "dataset_query": {
            "type": "native",
            "database": db_id,
            "native": {"query": query, "template-tags": template_tags},
        },
    }


def dashcards(spec: dict, card_ids: dict[str, int]) -> list[dict]:
    result: list[dict] = []
    next_id = -1
    for section in spec["sections"]:
        row, col, width, height = section["position"]
        result.append(
            {
                "id": next_id,
                "card_id": None,
                "row": row,
                "col": col,
                "size_x": width,
                "size_y": height,
                "parameter_mappings": [],
                "visualization_settings": {
                    "virtual_card": {
                        "name": None,
                        "display": "heading",
                        "visualization_settings": {},
                        "dataset_query": {},
                        "archived": False,
                    },
                    "text": section["heading"],
                    "dashcard.background": False,
                },
            }
        )
        next_id -= 1
        for card in section["cards"]:
            row, col, width, height = card["position"]
            card_id = card_ids[card["name"]]
            result.append(
                {
                    "id": next_id,
                    "card_id": card_id,
                    "row": row,
                    "col": col,
                    "size_x": width,
                    "size_y": height,
                    "visualization_settings": {},
                    "parameter_mappings": [
                        {
                            "parameter_id": tag,
                            "card_id": card_id,
                            "target": ["dimension", ["template-tag", tag]],
                        }
                        for tag in card.get("filters", {})
                    ],
                }
            )
            next_id -= 1
    return result


def dashboard_parameters(spec: dict) -> list[dict]:
    return [
        {k: v for k, v in p.items() if k in {"id", "name", "slug", "type", "sectionId", "default"}}
        for p in spec["parameters"]
    ]


# ---------------------------------------------------------------------- main


def provision(cfg: Config, definitions: Path = DEFINITIONS_DIR) -> None:
    client = MetabaseClient(cfg.url)
    client.wait_until_healthy()
    if client.setup_or_login(cfg):
        client.remove_sample_content()
    db_id = client.ensure_database(cfg)
    collection_id = client.ensure_collection(COLLECTION_NAME)

    specs = [
        yaml.safe_load(p.read_text(encoding="utf-8"))
        for p in sorted((definitions / "dashboards").glob("*.yaml"))
    ]
    required = {
        field
        for spec in specs
        for section in spec["sections"]
        for card in section["cards"]
        for field in card.get("filters", {}).values()
    }
    fields = client.field_ids(db_id, required)

    existing_cards = client.items(collection_id, "card")
    existing_dashboards = client.items(collection_id, "dashboard")
    for spec in specs:
        params = {p["id"]: p for p in spec["parameters"]}
        card_ids: dict[str, int] = {}
        for section in spec["sections"]:
            for card in section["cards"]:
                payload = card_payload(card, db_id, collection_id, fields, params)
                if card["name"] in existing_cards:
                    card_id = existing_cards[card["name"]]
                    client.put(f"/card/{card_id}", payload)
                else:
                    card_id = client.post("/card", payload)["id"]
                card_ids[card["name"]] = card_id

        if spec["name"] in existing_dashboards:
            dashboard_id = existing_dashboards[spec["name"]]
        else:
            dashboard_id = client.post(
                "/dashboard", {"name": spec["name"], "collection_id": collection_id}
            )["id"]
        client.put(
            f"/dashboard/{dashboard_id}",
            {
                "description": spec.get("description"),
                "width": "full",
                "parameters": dashboard_parameters(spec),
                "dashcards": dashcards(spec, card_ids),
            },
        )
        if spec.get("homepage"):
            client.set_homepage(dashboard_id)
        log.info("Dashboard '%s' -> %s/dashboard/%s", spec["name"], cfg.url, dashboard_id)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    provision(Config.from_env())
    return 0


if __name__ == "__main__":
    sys.exit(main())
