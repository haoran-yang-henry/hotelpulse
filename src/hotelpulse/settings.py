"""Runtime configuration, read from environment variables (see .env.example)."""

import os
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get("HOTELPULSE_ROOT", Path(__file__).resolve().parents[2]))
WAREHOUSE_DIR = PROJECT_ROOT / "warehouse"
DATA_DIR = PROJECT_ROOT / "data"
BI_DIR = PROJECT_ROOT / "bi"


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Environment variable {name} is not set")
    return value


def dwh_dsn() -> str:
    return require_env("HOTELPULSE_DWH_DSN")


def pms_admin_dsn() -> str:
    return require_env("HOTELPULSE_PMS_ADMIN_DSN")


def sim_anchor_date() -> date | None:
    """Date the dataset's "today" is aligned to; None means "use today"."""
    value = os.environ.get("SIM_ANCHOR_DATE", "").strip()
    return date.fromisoformat(value) if value else None
