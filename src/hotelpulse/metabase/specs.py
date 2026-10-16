"""Dashboard definitions (bi/metabase/dashboards/*.yaml) and the KPI glossary."""

from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from hotelpulse import settings

DEFINITIONS_DIR = settings.BI_DIR / "metabase"


@dataclass(frozen=True)
class CardSpec:
    dashboard: str
    name: str
    description: str
    explain: dict[str, Any]  # intent, targets, ... used by the insight service


def load_dashboards(definitions: Path = DEFINITIONS_DIR) -> list[dict]:
    return [
        yaml.safe_load(p.read_text(encoding="utf-8"))
        for p in sorted((definitions / "dashboards").glob("*.yaml"))
    ]


def iter_cards(spec: dict):
    for section in spec["sections"]:
        yield from section.get("cards", [])


@cache
def card_specs(definitions: Path = DEFINITIONS_DIR) -> dict[tuple[str, str], CardSpec]:
    return {
        (spec["name"], card["name"]): CardSpec(
            dashboard=spec["name"],
            name=card["name"],
            description=" ".join(str(card.get("description", "")).split()),
            explain=card.get("explain") or {},  # `explain: false` = no explain link
        )
        for spec in load_dashboards(definitions)
        for card in iter_cards(spec)
    }


@cache
def glossary(definitions: Path = DEFINITIONS_DIR) -> dict[str, dict[str, Any]]:
    path = definitions / "glossary.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def relevant_glossary(*texts: str, definitions: Path = DEFINITIONS_DIR) -> dict[str, str]:
    """Glossary entries whose match words occur in the given texts (title, columns, ...)."""
    haystack = " ".join(t.lower().replace("_", " ") for t in texts if t)
    return {
        name: " ".join(str(entry["text"]).split())
        for name, entry in glossary(definitions).items()
        if any(word.lower() in haystack for word in entry.get("match", []))
    }
