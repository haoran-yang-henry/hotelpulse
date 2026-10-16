"""Turn the filter values Metabase puts into a text-card link back into raw filter values.

Text cards substitute dashboard filters in *display* format ("Previous 12 weeks",
"July 1, 2026 - September 30, 2026", "mobile and tablet"); queries need the raw format
("past12weeks", "2026-07-01~2026-09-30", ["mobile", "tablet"]). The mapping below was
measured against Metabase 0.64 (see tests/unit/test_insight_filters.py). Raw values are
accepted as they are, so the API can also be called programmatically.
"""

import re
from datetime import datetime

UNITS = ("minute", "hour", "day", "week", "month", "quarter", "year")
_UNIT = r"(minute|hour|day|week|month|quarter|year)s?"
_DATE = r"([A-Z][a-z]+ \d{1,2}, \d{4})"

RAW_DATE = re.compile(
    r"^(?:(?:past|next)\d+(?:minute|hour|day|week|month|quarter|year)s~?"
    r"(?:-from-\d+(?:minute|hour|day|week|month|quarter|year)s)?"
    r"|this(?:day|week|month|quarter|year)|today|yesterday"
    r"|\d{4}-\d{2}-\d{2}(?:~(?:\d{4}-\d{2}-\d{2})?)?|~\d{4}-\d{2}-\d{2}"
    r"|\d{4}-\d{2}|Q[1-4]-\d{4})$"
)


def _iso(display_date: str) -> str:
    return datetime.strptime(display_date, "%B %d, %Y").date().isoformat()


def _plural(unit: str) -> str:
    return unit + "s"


DISPLAY_DATE = [
    (
        re.compile(rf"^Previous (\d+) {_UNIT}, starting (\d+) {_UNIT} ago$"),
        lambda m: f"past{m[1]}{_plural(m[2])}-from-{m[3]}{_plural(m[4])}",
    ),
    (re.compile(rf"^Previous (\d+) {_UNIT}$"), lambda m: f"past{m[1]}{_plural(m[2])}"),
    (re.compile(rf"^Previous {_UNIT}$"), lambda m: f"past1{_plural(m[1])}"),
    (re.compile(rf"^Next (\d+) {_UNIT}$"), lambda m: f"next{m[1]}{_plural(m[2])}"),
    (re.compile(rf"^Next {_UNIT}$"), lambda m: f"next1{_plural(m[1])}"),
    (re.compile(r"^Today$"), lambda m: "thisday"),
    (re.compile(r"^Yesterday$"), lambda m: "yesterday"),
    (re.compile(r"^This (day|week|month|quarter|year)$"), lambda m: f"this{m[1]}"),
    (re.compile(rf"^{_DATE} - {_DATE}$"), lambda m: f"{_iso(m[1])}~{_iso(m[2])}"),
    (re.compile(rf"^On {_DATE}$"), lambda m: _iso(m[1])),
    (re.compile(rf"^Before {_DATE}$"), lambda m: f"~{_iso(m[1])}"),
    (re.compile(rf"^After {_DATE}$"), lambda m: f"{_iso(m[1])}~"),
]


def is_unset(value: str | None) -> bool:
    """Empty, or the literal placeholder Metabase leaves when no value is selected."""
    return value is None or not value.strip() or bool(re.fullmatch(r"\{\{.*\}\}", value.strip()))


def parse_date(value: str) -> str | None:
    value = " ".join(value.split())
    if RAW_DATE.match(value):
        return value
    for pattern, to_raw in DISPLAY_DATE:
        match = pattern.match(value)
        if match:
            return to_raw(match)
    return None


def parse_list(value: str) -> list[str]:
    """'a', 'a and b', 'a, b, and c' -> list of values."""
    value = " ".join(value.split())
    parts = re.split(r",\s*(?:and\s+)?|\s+and\s+", value)
    return [p for p in (part.strip() for part in parts) if p]


def to_raw(parameter_type: str, values: list[str]) -> str | list[str] | None:
    """Raw Metabase value for a dashboard parameter, or None when unset/unparseable."""
    values = [v for v in values if not is_unset(v)]
    if not values:
        return None
    if parameter_type.startswith("date"):
        return parse_date(values[0])
    if len(values) > 1:  # repeated query parameters, e.g. from an API caller
        return values
    return parse_list(values[0])
