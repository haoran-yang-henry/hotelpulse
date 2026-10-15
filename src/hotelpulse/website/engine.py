"""Booking engine of the simulated PMS: room offers, availability and new website bookings.

New bookings are written into the simulator's timeline (``sim`` schema) and revealed right
away, so they move through check-in and check-out like every other reservation.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

import psycopg

from hotelpulse.simulator import pms

TEST_DECLINED_CARD = "4000000000000002"
BREAKFAST_PER_PERSON_NIGHT = Decimal("14.00")
MAX_NIGHTS = 14
CHECK_IN_HOUR, CHECK_OUT_HOUR = 15, 11


@dataclass(frozen=True)
class Hotel:
    hotel_id: int
    code: str
    name: str
    city: str
    total_rooms: int
    timezone: str


@dataclass(frozen=True)
class RoomOffer:
    code: str
    name: str
    nightly_rate: Decimal
    total: Decimal


@dataclass(frozen=True)
class Stay:
    hotel: Hotel
    checkin: date
    checkout: date
    adults: int
    children: int

    @property
    def nights(self) -> int:
        return (self.checkout - self.checkin).days


class InvalidStay(ValueError):
    pass


def money(value: Decimal | float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def load_hotels(conn: psycopg.Connection) -> dict[str, Hotel]:
    rows = conn.execute(
        "SELECT hotel_id, hotel_code, hotel_name, city, total_rooms, timezone"
        " FROM public.hotels ORDER BY hotel_id"
    ).fetchall()
    return {r[1]: Hotel(*r) for r in rows}


def load_price_table(conn: psycopg.Connection) -> dict[tuple[str, str, int], Decimal]:
    """Typical nightly rate per hotel, room type and month, learned from past bookings."""
    rows = conn.execute(
        """
        SELECT h.hotel_code, p.reserved_room_type, extract(MONTH FROM p.arrival_date)::int,
               round(avg(p.adr))
        FROM sim.reservation_plan AS p
        JOIN public.hotels AS h ON h.hotel_id = p.hotel_id
        WHERE p.canceled_at IS NULL AND p.adr BETWEEN 20 AND 1000
        GROUP BY 1, 2, 3
        HAVING count(*) >= 20
        """
    ).fetchall()
    return {(hotel, room, month): money(rate) for hotel, room, month, rate in rows}


def validate_stay(
    hotels: dict[str, Hotel], hotel: str, checkin: date, checkout: date, adults: int, children: int
) -> Stay:
    if hotel not in hotels:
        raise InvalidStay("Please choose a hotel.")
    today = datetime.now(ZoneInfo(hotels[hotel].timezone)).date()
    if checkin < today:
        raise InvalidStay("Check-in cannot be in the past.")
    if not 1 <= (checkout - checkin).days <= MAX_NIGHTS:
        raise InvalidStay(f"Stays are bookable online for 1 to {MAX_NIGHTS} nights.")
    if not (1 <= adults <= 4 and 0 <= children <= 3):
        raise InvalidStay("Rooms sleep up to 4 adults and 3 children.")
    return Stay(hotels[hotel], checkin, checkout, adults, children)


def room_offers(
    conn: psycopg.Connection, prices: dict[tuple[str, str, int], Decimal], stay: Stay
) -> list[RoomOffer]:
    rows = conn.execute(
        "SELECT room_type_code, room_type_name FROM public.room_types"
        " WHERE hotel_id = %s ORDER BY room_type_code",
        (stay.hotel.hotel_id,),
    ).fetchall()
    nights = [stay.checkin + timedelta(days=i) for i in range(stay.nights)]
    offers = []
    for code, name in rows:
        rates = [prices.get((stay.hotel.code, code, night.month)) for night in nights]
        if None in rates:
            continue  # room type not sold in this season
        total = money(sum(rates))
        offers.append(RoomOffer(code, name, money(total / stay.nights), total))
    return sorted(offers, key=lambda o: o.total)


def rooms_left(conn: psycopg.Connection, stay: Stay) -> int:
    """Rooms still free on the busiest night of the stay (hotel-wide)."""
    busiest = conn.execute(
        """
        SELECT coalesce(max(booked), 0) FROM (
            SELECT night, count(r.reservation_id) AS booked
            FROM generate_series(%(checkin)s::date, %(last_night)s::date, INTERVAL '1 day') AS night
            LEFT JOIN public.reservations AS r
                ON r.hotel_id = %(hotel_id)s
                AND r.status IN ('confirmed', 'checked_in')
                AND night >= r.arrival_date AND night < r.departure_date
            GROUP BY night
        ) AS n
        """,
        {
            "checkin": stay.checkin,
            "last_night": stay.checkout - timedelta(days=1),
            "hotel_id": stay.hotel.hotel_id,
        },
    ).fetchone()[0]
    return max(0, stay.hotel.total_rooms - busiest)


def breakfast_total(stay: Stay) -> Decimal:
    return money(BREAKFAST_PER_PERSON_NIGHT * (stay.adults + stay.children) * stay.nights)


def create_booking(
    conn: psycopg.Connection,
    stay: Stay,
    offer: RoomOffer,
    *,
    first_name: str,
    last_name: str,
    email: str,
    country_code: str | None,
    breakfast: bool,
) -> str:
    """Create a website booking in the simulated PMS and return its confirmation code."""
    tz = ZoneInfo(stay.hotel.timezone)
    now = datetime.now(UTC)
    check_in = datetime.combine(stay.checkin, time(CHECK_IN_HOUR), tz).astimezone(UTC)
    check_out = datetime.combine(stay.checkout, time(CHECK_OUT_HOUR), tz).astimezone(UTC)
    with conn.transaction():
        guest_id = conn.execute("SELECT nextval('sim.engine_guest_id_seq')").fetchone()[0]
        reservation_id = conn.execute("SELECT nextval('sim.engine_reservation_id_seq')").fetchone()[
            0
        ]
        conn.execute(
            "INSERT INTO sim.guest_plan"
            " (guest_id, first_name, last_name, email, country_code, created_at)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            (guest_id, first_name, last_name, email.lower(), country_code, now),
        )
        conn.execute(
            """
            INSERT INTO sim.reservation_plan (
                reservation_id, confirmation_code, hotel_id, guest_id, booking_source,
                market_segment, distribution_channel, reserved_room_type, assigned_room_type,
                arrival_date, departure_date, adults, children, babies, meal_plan, adr,
                deposit_type, customer_type, is_repeated_guest, previous_cancellations,
                previous_bookings_not_canceled, booking_changes, days_in_waiting_list,
                parking_spaces, special_requests, created_at, checked_in_at, checked_out_at
            ) VALUES (
                %s, %s, %s, %s, 'website', 'Direct', 'Direct', %s, %s, %s, %s, %s, %s, 0, %s, %s,
                'No Deposit', 'Transient', FALSE, 0, 0, 0, 0, 0, 0, %s, %s, %s
            )
            """,
            (
                reservation_id, f"HP{reservation_id}", stay.hotel.hotel_id, guest_id,
                offer.code, offer.code, stay.checkin, stay.checkout, stay.adults, stay.children,
                "BB" if breakfast else "SC", offer.nightly_rate,
                now, max(check_in, now + timedelta(minutes=30)), check_out,
            ),
        )  # fmt: skip
    pms.reveal(conn, now)
    conn.commit()
    return f"HP{reservation_id}"


def find_booking(conn: psycopg.Connection, confirmation_code: str) -> dict | None:
    row = conn.execute(
        """
        SELECT r.confirmation_code, h.hotel_code, h.hotel_name, r.reserved_room_type,
               rt.room_type_name, r.arrival_date, r.departure_date, r.adults, r.children,
               r.adr, r.meal_plan, r.departure_date - r.arrival_date AS nights
        FROM public.reservations AS r
        JOIN public.hotels AS h ON h.hotel_id = r.hotel_id
        LEFT JOIN public.room_types AS rt
            ON rt.hotel_id = r.hotel_id AND rt.room_type_code = r.reserved_room_type
        WHERE r.confirmation_code = %s
        """,
        (confirmation_code,),
    ).fetchone()
    if row is None:
        return None
    keys = (
        "confirmation_code", "hotel_code", "hotel_name", "room_type_code", "room_type_name",
        "checkin", "checkout", "adults", "children", "nightly_rate", "meal_plan", "nights",
    )  # fmt: skip
    booking = dict(zip(keys, row, strict=True))
    booking["room_total"] = money(booking["nightly_rate"] * booking["nights"])
    return booking
