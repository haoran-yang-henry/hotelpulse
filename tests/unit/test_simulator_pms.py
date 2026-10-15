from datetime import date, timedelta

import pytest

from hotelpulse.simulator import pms
from hotelpulse.simulator.pms import build_plan, shift_days

ANCHOR = date(2026, 10, 15)
# column positions in a reservation plan row (see pms.PLAN_COLUMNS)
COLS = [c.strip() for c in pms.PLAN_COLUMNS.split(",")]
IDX = {name: i for i, name in enumerate(COLS)}


def col(row, name):
    return row[IDX[name]]


@pytest.mark.parametrize(
    "anchor", [date(2026, 10, 15), date(2027, 3, 1), date(2026, 6, 30), date(2026, 7, 1)]
)
def test_shift_keeps_weekdays_and_seasons(anchor):
    days = shift_days(anchor)
    assert days % 7 == 0  # weekdays line up
    dataset_today = anchor - timedelta(days=days)
    drift = abs(dataset_today.timetuple().tm_yday - anchor.timetuple().tm_yday)
    assert min(drift, 365 - drift) <= 4  # seasons line up
    # leaves at least a year of history and some future arrivals in the dataset
    assert date(2016, 6, 25) <= dataset_today <= date(2017, 7, 5)


def test_plan_row_matches_declared_columns(booking_factory):
    plan = build_plan([booking_factory()], ANCHOR)
    assert len(plan.reservations[0]) == len(COLS)


def test_checked_out_booking_has_ordered_lifecycle(booking_factory):
    plan = build_plan([booking_factory()], ANCHOR)
    row = plan.reservations[0]
    assert col(row, "created_at") < col(row, "checked_in_at") < col(row, "checked_out_at")
    assert col(row, "canceled_at") is None and col(row, "no_show_at") is None
    offset = timedelta(days=shift_days(ANCHOR))
    assert col(row, "arrival_date") == date(2017, 3, 1) + offset
    assert col(row, "departure_date") == date(2017, 3, 4) + offset


def test_canceled_booking_is_canceled_after_creation(booking_factory):
    b = booking_factory(
        is_canceled=True,
        reservation_status="Canceled",
        reservation_status_date=date(2017, 1, 30),  # booking date is 2017-01-30 as well
    )
    row = build_plan([b], ANCHOR).reservations[0]
    assert col(row, "canceled_at") > col(row, "created_at")
    assert col(row, "checked_in_at") is None


def test_no_show_is_flagged_after_arrival_day(booking_factory):
    b = booking_factory(is_canceled=True, reservation_status="No-Show")
    row = build_plan([b], ANCHOR).reservations[0]
    assert col(row, "no_show_at").date() > col(row, "arrival_date")


def test_reservation_ids_follow_booking_time(booking_factory):
    bookings = [booking_factory(lead_time=lt) for lt in (5, 50, 20)]
    rows = build_plan(bookings, ANCHOR).reservations
    ordered = sorted(rows, key=lambda r: col(r, "created_at"))
    assert [col(r, "reservation_id") for r in ordered] == sorted(
        col(r, "reservation_id") for r in rows
    )


def test_plan_is_deterministic(booking_factory):
    bookings = [booking_factory(lead_time=lt, market_segment="Direct") for lt in range(1, 40)]
    assert build_plan(bookings, ANCHOR) == build_plan(bookings, ANCHOR)


def test_walk_in_and_undefined_sources(booking_factory):
    rng = __import__("random").Random(0)
    assert pms.booking_source(booking_factory(market_segment="Direct", lead_time=0), rng) == (
        "walk_in"
    )
    assert pms.booking_source(booking_factory(market_segment="Undefined"), rng) is None
    assert pms.booking_source(booking_factory(distribution_channel="GDS"), rng) == "gds"


def test_anomaly_a1_moves_website_bookings_to_ota_only_inside_window(booking_factory):
    offset = shift_days(ANCHOR)
    in_window = ANCHOR - timedelta(days=17)  # A1 runs from -24 to -10 days
    outside = ANCHOR - timedelta(days=60)

    def direct_bookings_on(day):
        arrival = day - timedelta(days=offset) + timedelta(days=30)
        return [
            booking_factory(market_segment="Direct", distribution_channel="Direct",
                            lead_time=30, arrival_date=arrival)
            for _ in range(400)
        ]  # fmt: skip

    def leaked(rows):
        return sum(col(r, "anomaly_id") == "A1" for r in rows)

    inside_rows = build_plan(direct_bookings_on(in_window), ANCHOR).reservations
    outside_rows = build_plan(direct_bookings_on(outside), ANCHOR).reservations
    assert leaked(outside_rows) == 0
    assert 0.15 * 400 < leaked(inside_rows) < 0.45 * 400  # 65 % website x 45 % leak ~ 29 %
    assert all(
        col(r, "booking_source") == "booking_com" for r in inside_rows if col(r, "anomaly_id")
    )


def test_room_inventory_sums_to_hotel_capacity(booking_factory):
    bookings = [
        booking_factory(assigned_room_type="A"),
        booking_factory(assigned_room_type="D", nights=1),
        booking_factory(hotel="Resort Hotel", assigned_room_type="E"),
    ]
    inventory = pms.room_inventory(bookings)
    assert sum(inventory["City Hotel"].values()) == pms.HOTELS["City Hotel"].total_rooms
    assert sum(inventory["Resort Hotel"].values()) == pms.HOTELS["Resort Hotel"].total_rooms
