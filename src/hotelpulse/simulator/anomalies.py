"""Load the injected-anomaly catalogue (anomalies.yaml)."""

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

CATALOGUE = Path(__file__).with_name("anomalies.yaml")


@dataclass(frozen=True)
class Anomaly:
    id: str
    name: str
    description: str
    start: date
    end: date  # exclusive
    effects: dict[str, dict[str, Any]] = field(default_factory=dict)

    def active_on(self, day: date) -> bool:
        return self.start <= day < self.end

    def effect(self, source: str, key: str, default: Any = None) -> Any:
        return self.effects.get(source, {}).get(key, default)


def load(anchor: date, path: Path = CATALOGUE) -> dict[str, Anomaly]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))["anomalies"]
    return {
        a["id"]: Anomaly(
            id=a["id"],
            name=a["name"],
            description=a["description"].strip(),
            start=anchor + timedelta(days=a["start_offset_days"]),
            end=anchor + timedelta(days=a["end_offset_days"]),
            effects=a.get("effects", {}),
        )
        for a in raw
    }
