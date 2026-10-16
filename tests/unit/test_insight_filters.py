import pytest

from hotelpulse.insight.filters import is_unset, parse_date, parse_list, to_raw

# Measured against Metabase 0.64: raw value -> what a text card shows.
# Re-run the probe when upgrading Metabase (ADR-0015).
OBSERVED = [
    ("past26weeks", "Previous 26 weeks"),
    ("past30days", "Previous 30 days"),
    ("next7days", "Next 7 days"),
    ("past3months-from-3months", "Previous 3 months, starting 3 months ago"),
    ("thisday", "Today"),
    ("yesterday", "Yesterday"),
    ("thisweek", "This week"),
    ("thismonth", "This month"),
    ("thisquarter", "This quarter"),
    ("thisyear", "This year"),
    ("past1weeks", "Previous week"),
    ("past2years", "Previous 2 years"),
    ("2026-07-01~2026-09-30", "July 1, 2026 - September 30, 2026"),
    ("2026-07-01", "On July 1, 2026"),
    ("~2026-07-01", "Before July 1, 2026"),
    ("2026-07-01~", "After July 1, 2026"),
]


@pytest.mark.parametrize(("raw", "display"), OBSERVED)
def test_display_values_map_back_to_raw(raw, display):
    assert parse_date(display) == raw


@pytest.mark.parametrize("raw", [raw for raw, _ in OBSERVED] + ["past12weeks~", "Q3-2026"])
def test_raw_values_pass_through(raw):
    assert parse_date(raw) == raw


def test_unparseable_date_is_none():
    assert parse_date("Some time ago") is None


@pytest.mark.parametrize(
    ("display", "values"),
    [
        ("mobile", ["mobile"]),
        ("mobile and tablet", ["mobile", "tablet"]),
        ("Email, Direct, and Paid search", ["Email", "Direct", "Paid search"]),
        ("HotelPulse City Lisbon and HotelPulse Resort Algarve",
         ["HotelPulse City Lisbon", "HotelPulse Resort Algarve"]),
    ],
)  # fmt: skip
def test_lists(display, values):
    assert parse_list(display) == values


def test_unset_placeholders_are_ignored():
    assert is_unset("{{period}}") and is_unset("") and is_unset(None)
    assert to_raw("date/all-options", ["{{period}}"]) is None
    assert to_raw("string/=", ["{{device}}"]) is None


def test_to_raw_by_parameter_type():
    assert to_raw("date/all-options", ["Previous 12 weeks"]) == "past12weeks"
    assert to_raw("string/=", ["mobile and tablet"]) == ["mobile", "tablet"]
    assert to_raw("string/=", ["mobile", "desktop"]) == ["mobile", "desktop"]
