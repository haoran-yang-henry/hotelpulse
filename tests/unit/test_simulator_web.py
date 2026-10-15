from collections import Counter
from datetime import UTC, date, datetime, timedelta

import pytest

from hotelpulse.simulator import web
from hotelpulse.tracking import collector

ANCHOR = date(2026, 10, 15)
NOW = datetime(2026, 10, 15, 12, tzinfo=UTC)


def booking(i: int, created_at: datetime, leaked: bool = False) -> web.WebBooking:
    arrival = created_at.date() + timedelta(days=30)
    return web.WebBooking(
        reservation_id=1_000_000 + i,
        confirmation_code=f"HP{1_000_000 + i}",
        hotel_code="CITY" if i % 2 else "RESORT",
        room_type_code="A",
        arrival=arrival,
        departure=arrival + timedelta(days=3),
        adults=2,
        children=0,
        adr=110.0,
        meal_plan="BB",
        created_at=created_at,
        leaked=leaked,
    )


@pytest.fixture(scope="module")
def model():
    start = NOW - timedelta(days=40)
    bookings = [booking(i, start + timedelta(hours=7 * i)) for i in range(140)]
    a1_day = datetime.combine(ANCHOR - timedelta(days=17), datetime.min.time(), UTC)
    bookings += [booking(500 + i, a1_day + timedelta(hours=i), leaked=True) for i in range(10)]
    return web.TrafficModel(ANCHOR, bookings)


@pytest.fixture(scope="module")
def window_events(model):
    return model.events(NOW - timedelta(days=30), NOW - timedelta(days=1))


def by_name(events, name):
    return [e for e in events if e.payload["event_name"] == name]


def test_each_website_booking_converts_exactly_once(model):
    b = next(b for b in model.bookings if not b.leaked)
    sessions = model.booking_sessions(b)
    confirmations = [e for s in sessions for e in by_name(s, "booking_confirmed")]
    assert len(confirmations) == 1
    assert confirmations[0].payload["properties"]["confirmation_code"] == b.confirmation_code
    assert sessions[-1][-1].true_ts > b.created_at - timedelta(minutes=30)


def test_leaked_booking_ends_in_mobile_gateway_timeout(model):
    b = next(b for b in model.bookings if b.leaked)
    final = model.booking_sessions(b)[-1]
    assert not by_name(final, "booking_confirmed")
    failures = by_name(final, "payment_failed")
    assert failures and {f.payload["properties"]["error_code"] for f in failures} == {
        "gateway_timeout"
    }
    assert final[0].visitor.device == "mobile"
    assert final[-1].true_ts < b.created_at


def test_generation_is_deterministic_and_window_additive(model):
    a, b, c = NOW - timedelta(days=3), NOW - timedelta(days=2, hours=5), NOW - timedelta(days=1)
    whole = [e.payload["event_id"] for e in model.events(a, c)]
    again = [e.payload["event_id"] for e in model.events(a, c)]
    parts = [e.payload["event_id"] for e in model.events(a, b) + model.events(b, c)]
    assert whole == again
    assert sorted(whole) == sorted(parts)


def test_generated_events_satisfy_the_contract(window_events):
    sample = [{**e.payload, "sent_at": web.iso(e.true_ts)} for e in window_events[:3000]]
    accepted, rejected = collector.process(sample, "UA", NOW)
    assert not rejected and len(accepted) == len(sample)


def test_traffic_volume_matches_target_conversion(window_events):
    sessions = {e.payload["session_hint"] for e in window_events if e.visitor.device != "bot"}
    bookings = len(by_name(window_events, "booking_confirmed"))
    assert 0.015 < bookings / len(sessions) < 0.04


def test_consent_rate_drops_with_anomaly_a5(model):
    assert model.consent_rate(ANCHOR - timedelta(days=90)) == web.BASE_CONSENT_RATE
    assert model.consent_rate(ANCHOR - timedelta(days=30)) == 0.55


def test_deliveries_drop_untracked_visitors_and_add_noise(window_events):
    delivered = web.deliveries(window_events)
    tracked = [e for e in window_events if e.visitor.tracked]
    assert len(tracked) < len(window_events)
    assert all(v.tracked for _, v, _ in delivered)
    ids = Counter(p.get("event_id") for _, _, p in delivered)
    duplicates = sum(c - 1 for c in ids.values())
    assert 0 < duplicates < 0.02 * len(tracked)


def test_clock_skew_is_recoverable_with_derived_timestamp(model, window_events):
    skewed = next(e for e in window_events if e.visitor.clock_skew)
    delivered_at = skewed.true_ts + skewed.delivery_delay
    event_ts = datetime.fromisoformat(skewed.payload["event_ts"])
    sent_at = delivered_at + skewed.visitor.clock_skew
    derived = delivered_at - (sent_at - event_ts)
    assert abs(derived - skewed.true_ts) < timedelta(milliseconds=2)
