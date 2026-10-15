from datetime import date

from hotelpulse.simulator.dataset import parse_row

ROW = {
    "hotel": "Resort Hotel", "is_canceled": "0", "lead_time": "342", "arrival_date_year": "2015",
    "arrival_date_month": "July", "arrival_date_week_number": "27",
    "arrival_date_day_of_month": "1",
    "stays_in_weekend_nights": "1", "stays_in_week_nights": "2", "adults": "2", "children": "NA",
    "babies": "0", "meal": "BB", "country": "PRT", "market_segment": "Direct",
    "distribution_channel": "Direct", "is_repeated_guest": "0", "previous_cancellations": "0",
    "previous_bookings_not_canceled": "0", "reserved_room_type": "C", "assigned_room_type": "C",
    "booking_changes": "3", "deposit_type": "No Deposit", "agent": "NULL", "company": "NULL",
    "days_in_waiting_list": "0", "customer_type": "Transient", "adr": "-6.38",
    "required_car_parking_spaces": "0", "total_of_special_requests": "0",
    "reservation_status": "Check-Out", "reservation_status_date": "2015-07-04",
}  # fmt: skip


def test_parse_row_types_and_nulls():
    b = parse_row(ROW)
    assert b.arrival_date == date(2015, 7, 1)
    assert b.nights == 3
    assert b.departure_date == date(2015, 7, 4)
    assert b.booking_date == date(2014, 7, 24)
    assert b.children is None and b.agent is None and b.company is None
    assert b.adr == -6.38  # source quirks are preserved for the warehouse to flag
