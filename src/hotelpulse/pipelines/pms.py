"""PMS source tables and how they land in the raw layer."""

from hotelpulse.pipelines.extract import SourceTable

RESERVATION_COLUMNS = (
    "reservation_id", "confirmation_code", "hotel_id", "guest_id", "booking_source",
    "market_segment", "distribution_channel", "reserved_room_type", "assigned_room_type",
    "arrival_date", "departure_date", "adults", "children", "babies", "meal_plan", "adr",
    "deposit_type", "customer_type", "is_repeated_guest", "previous_cancellations",
    "previous_bookings_not_canceled", "booking_changes", "days_in_waiting_list", "agent_id",
    "company_id", "parking_spaces", "special_requests", "status", "created_at", "checked_in_at",
    "checked_out_at", "canceled_at", "updated_at",
)  # fmt: skip

HOTEL_COLUMNS = (
    "hotel_id", "hotel_code", "hotel_name", "city", "country_code", "timezone", "total_rooms",
    "pms_live_date", "updated_at",
)  # fmt: skip
GUEST_COLUMNS = (
    "guest_id", "first_name", "last_name", "email", "country_code", "created_at", "updated_at",
)  # fmt: skip

SOURCE_TABLES = {
    t.name: t
    for t in (
        SourceTable(
            name="hotels",
            source="public.hotels",
            target="raw.pms_hotels",
            columns=HOTEL_COLUMNS,
        ),
        SourceTable(
            name="room_types",
            source="public.room_types",
            target="raw.pms_room_types",
            columns=("hotel_id", "room_type_code", "room_type_name", "room_count", "updated_at"),
        ),
        SourceTable(
            name="guests",
            source="public.guests",
            target="raw.pms_guests",
            columns=GUEST_COLUMNS,
            incremental_column="updated_at",
        ),
        SourceTable(
            name="reservations",
            source="public.reservations",
            target="raw.pms_reservations",
            columns=RESERVATION_COLUMNS,
            incremental_column="updated_at",
        ),
    )
}
