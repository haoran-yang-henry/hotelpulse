from datetime import date

import pytest

from hotelpulse.simulator.dataset import Booking


def make_booking(**overrides) -> Booking:
    values = dict(
        hotel="City Hotel",
        is_canceled=False,
        lead_time=30,
        arrival_date=date(2017, 3, 1),
        nights=3,
        adults=2,
        children=0,
        babies=0,
        meal="BB",
        country="PRT",
        market_segment="Online TA",
        distribution_channel="TA/TO",
        is_repeated_guest=False,
        previous_cancellations=0,
        previous_bookings_not_canceled=0,
        reserved_room_type="A",
        assigned_room_type="A",
        booking_changes=0,
        deposit_type="No Deposit",
        agent="9",
        company=None,
        days_in_waiting_list=0,
        customer_type="Transient",
        adr=95.0,
        parking_spaces=0,
        special_requests=1,
        reservation_status="Check-Out",
        reservation_status_date=date(2017, 3, 4),
    )
    values.update(overrides)
    return Booking(**values)


@pytest.fixture
def booking_factory():
    return make_booking
