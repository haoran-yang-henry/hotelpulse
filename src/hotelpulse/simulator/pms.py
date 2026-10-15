"""Simulated PMS: turns the booking dataset into a live, time-shifted source system.

``seed``   builds the full reservation timeline once (``sim`` schema) and creates the
           PMS application tables (``public`` schema).
``reveal`` writes every event that has happened up to a point in time into the PMS
           tables - new bookings, check-ins, check-outs, cancellations, no-shows.

See ADR-0003 for the reasoning behind time shifting and progressive reveal.
"""

import argparse
import logging
import random
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg

from hotelpulse import settings
from hotelpulse.simulator import anomalies as anomaly_catalogue
from hotelpulse.simulator import dataset
from hotelpulse.simulator.dataset import Booking

log = logging.getLogger(__name__)

SQL_DIR = Path(__file__).with_name("sql")
TZ = ZoneInfo("Europe/Lisbon")
# The dataset's "today" is chosen inside this one-year window: it leaves 12-24 months of
# history (arrivals start 2015-07-01) and 2-14 months of future arrivals (end 2017-08-31).
TODAY_WINDOW_START = (7, 1)  # month, day
RANDOM_SEED = 42
FIRST_RESERVATION_ID = 1_000_001


@dataclass(frozen=True)
class Hotel:
    hotel_id: int
    code: str
    name: str
    city: str
    total_rooms: int
    pms_live_date: date  # dataset date from which the hotel's data is complete


# Room counts are set just above the highest occupancy observed in the dataset
# (City: 226 rooms sold, Resort: 187), giving realistic 80-95 % peak occupancy.
#
# PMS go-live: the dataset only contains arrivals from 2015-07-01, so guests already in house
# on that date are missing (left-censoring), and the city hotel's records are sparse until
# September 2015 (~34 rooms a night in July vs. ~185 from September). Each hotel therefore
# gets a go-live date - with a two-week buffer - from which reporting is reliable, just like
# a property that migrated to a new PMS. Earlier records are kept but not reported.
HOTELS = {
    "City Hotel": Hotel(1, "CITY", "HotelPulse City Lisbon", "Lisbon", 240, date(2015, 9, 15)),
    "Resort Hotel": Hotel(
        2, "RESORT", "HotelPulse Resort Algarve", "Albufeira", 200, date(2015, 7, 15)
    ),
}

ROOM_TYPE_NAMES = {
    "A": "Standard Double",
    "B": "Standard Twin",
    "C": "Superior Double",
    "D": "Deluxe Double",
    "E": "Junior Suite",
    "F": "Family Room",
    "G": "Suite",
    "H": "Premium Suite",
    "I": "Accessible Room",
    "K": "Executive Room",
    "L": "Penthouse",
    "P": "Staff / Complimentary",
}

MEAL_PLANS = {
    "BB": "BB",
    "HB": "HB",
    "FB": "FB",
    "SC": "SC",
    "Undefined": "Undefined",  # kept as delivered by the vendor; cleaned in staging
}

FIRST_NAMES = {
    "PRT": ["Joao", "Maria", "Tiago", "Ana", "Rui", "Ines", "Pedro", "Sofia", "Miguel", "Rita"],
    "GBR": ["James", "Emily", "Oliver", "Sophie", "Harry", "Charlotte", "Jack", "Lucy"],
    "FRA": ["Louis", "Camille", "Hugo", "Lea", "Jules", "Chloe", "Arthur", "Manon"],
    "ESP": ["Javier", "Lucia", "Pablo", "Carmen", "Diego", "Elena", "Alvaro", "Marta"],
    "DEU": ["Lukas", "Anna", "Felix", "Lena", "Jonas", "Laura", "Paul", "Julia"],
    "ITA": ["Marco", "Giulia", "Luca", "Chiara", "Matteo", "Sara", "Andrea", "Francesca"],
}
LAST_NAMES = {
    "PRT": ["Silva", "Santos", "Ferreira", "Pereira", "Oliveira", "Costa", "Rodrigues", "Martins"],
    "GBR": ["Smith", "Jones", "Taylor", "Brown", "Williams", "Wilson", "Evans", "Thomas"],
    "FRA": ["Martin", "Bernard", "Dubois", "Thomas", "Robert", "Richard", "Petit", "Durand"],
    "ESP": ["Garcia", "Fernandez", "Gonzalez", "Rodriguez", "Lopez", "Martinez", "Sanchez"],
    "DEU": ["Muller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner", "Becker"],
    "ITA": ["Rossi", "Russo", "Ferrari", "Esposito", "Bianchi", "Romano", "Colombo", "Ricci"],
}
DEFAULT_FIRST = ["Alex", "Sam", "Chris", "Maria", "Daniel", "Laura", "David", "Anna", "Michael"]
DEFAULT_LAST = ["Anderson", "Novak", "Jensen", "Kowalski", "Haddad", "Tanaka", "Silva", "Kim"]


# --------------------------------------------------------------------------- time shift


def shift_days(anchor: date) -> int:
    """Days to add to dataset dates so that the anchor date becomes the dataset's "today".

    The shift is a whole number of years (seasons stay put: the resort still peaks in
    summer) rounded to whole weeks (weekday patterns stay put). The resulting drift of a
    few days against the calendar is irrelevant for hotel seasonality.
    """
    first_year = 2016 if (anchor.month, anchor.day) >= TODAY_WINDOW_START else 2017
    years = anchor.year - first_year
    return round(years * 365.2425 / 7) * 7


def local_ts(day: date, hour_from: float, hour_to: float, rng: random.Random) -> datetime:
    """Random local timestamp on `day` between two (fractional) hours, as aware UTC."""
    seconds = int(rng.uniform(hour_from * 3600, hour_to * 3600))
    naive = datetime.combine(day, time()) + timedelta(seconds=seconds)
    return naive.replace(tzinfo=TZ).astimezone(UTC)


# --------------------------------------------------------------------------- mapping


def booking_source(b: Booking, rng: random.Random) -> str | None:
    """Map dataset market segment / distribution channel to a concrete booking source."""
    if b.distribution_channel == "GDS":
        return "gds"
    match b.market_segment:
        case "Online TA":
            r = rng.random()
            return "booking_com" if r < 0.62 else "expedia" if r < 0.90 else "other_ota"
        case "Direct":
            if b.lead_time == 0:
                return "walk_in"
            return "website" if rng.random() < 0.65 else "phone"
        case "Offline TA/TO":
            return "travel_agent"
        case "Groups":
            return "group"
        case "Corporate":
            return "corporate"
        case "Aviation":
            return "aviation"
        case "Complementary":
            return "complimentary"
        case _:
            return None  # "Undefined" in the source - surfaced by data-quality checks


def room_inventory(bookings: list[Booking]) -> dict[str, dict[str, int]]:
    """Split each hotel's rooms across room types proportionally to observed room nights."""
    nights: dict[str, Counter[str]] = defaultdict(Counter)
    for b in bookings:
        if not b.is_canceled:
            nights[b.hotel][b.assigned_room_type] += max(b.nights, 1)
    inventory: dict[str, dict[str, int]] = {}
    for hotel_name, counter in nights.items():
        total_rooms = HOTELS[hotel_name].total_rooms
        total_nights = sum(counter.values())
        rooms = {code: max(1, round(total_rooms * n / total_nights)) for code, n in counter.items()}
        largest = max(rooms, key=rooms.__getitem__)
        rooms[largest] += total_rooms - sum(rooms.values())
        inventory[hotel_name] = dict(sorted(rooms.items()))
    return inventory


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


# --------------------------------------------------------------------------- plan


@dataclass
class Plan:
    guests: list[tuple]
    reservations: list[tuple]


def build_plan(bookings: list[Booking], anchor: date) -> Plan:
    """Deterministically build the full reservation and guest timeline."""
    rng = random.Random(RANDOM_SEED)
    offset = timedelta(days=shift_days(anchor))
    catalogue = anomaly_catalogue.load(anchor)
    a1 = catalogue["A1"]
    leak_share = a1.effect("pms", "website_to_ota_share", 0.0)

    # 1) timestamps per booking, in shifted (simulated) time
    staged = []
    for b in bookings:
        arrival = b.arrival_date + offset
        departure = b.departure_date + offset
        booked_on = b.booking_date + offset
        if b.lead_time == 0:
            created = local_ts(arrival, 9, 19, rng)
        else:
            created = local_ts(booked_on, 7, 23.5, rng)

        checked_in = checked_out = canceled = no_show = None
        if b.reservation_status == "Check-Out":
            checked_in = max(local_ts(arrival, 14, 22, rng), created + timedelta(minutes=15))
            if b.nights == 0:  # day use
                checked_out = checked_in + timedelta(hours=rng.uniform(3, 6))
            else:
                checked_out = local_ts(departure, 7.5, 11.5, rng)
        elif b.reservation_status == "Canceled":
            status_day = b.reservation_status_date + offset
            canceled = max(local_ts(status_day, 8, 23, rng), created + timedelta(minutes=10))
        elif b.reservation_status == "No-Show":
            # flagged by the night audit in the early hours after the arrival day
            no_show = local_ts(arrival + timedelta(days=1), 2, 2.5, rng)

        source = booking_source(b, rng)
        market_segment, channel, anomaly_id = b.market_segment, b.distribution_channel, None
        created_day = created.astimezone(TZ).date()
        if source == "website" and a1.active_on(created_day) and rng.random() < leak_share:
            source, market_segment, channel, anomaly_id = "booking_com", "Online TA", "TA/TO", "A1"

        staged.append(
            (created, b, arrival, departure, checked_in, checked_out, canceled, no_show,
             source, market_segment, channel, anomaly_id)
        )  # fmt: skip

    # 2) ids follow booking time, like a real PMS sequence
    staged.sort(key=lambda s: s[0])

    guests: list[tuple] = []
    guests_by_country: dict[str, list[int]] = defaultdict(list)
    reservations: list[tuple] = []
    for i, (created, b, arrival, departure, ci, co, cx, ns, source, seg, channel, aid) in enumerate(
        staged
    ):
        reservation_id = FIRST_RESERVATION_ID + i
        country = b.country or "UNK"
        pool = guests_by_country[country]
        if b.is_repeated_guest and pool:
            guest_id = rng.choice(pool)
        else:
            guest_id = len(guests) + 1
            first = rng.choice(FIRST_NAMES.get(country, DEFAULT_FIRST))
            last = rng.choice(LAST_NAMES.get(country, DEFAULT_LAST))
            email = _ascii(f"{first}.{last}.{guest_id}@example.com").lower()
            guests.append((guest_id, first, last, email, b.country, created))
            pool.append(guest_id)

        reservations.append(
            (
                reservation_id, f"HP{reservation_id}", HOTELS[b.hotel].hotel_id, guest_id,
                source, seg, channel, b.reserved_room_type, b.assigned_room_type,
                arrival, departure, b.adults, b.children, b.babies, MEAL_PLANS.get(b.meal, b.meal),
                round(b.adr, 2), b.deposit_type, b.customer_type, b.is_repeated_guest,
                b.previous_cancellations, b.previous_bookings_not_canceled, b.booking_changes,
                b.days_in_waiting_list, b.agent, b.company, b.parking_spaces, b.special_requests,
                created, ci, co, cx, ns, aid,
            )
        )  # fmt: skip
    return Plan(guests=guests, reservations=reservations)


# --------------------------------------------------------------------------- database

PLAN_COLUMNS = (
    "reservation_id, confirmation_code, hotel_id, guest_id, booking_source, market_segment, "
    "distribution_channel, reserved_room_type, assigned_room_type, arrival_date, departure_date, "
    "adults, children, babies, meal_plan, adr, deposit_type, customer_type, is_repeated_guest, "
    "previous_cancellations, previous_bookings_not_canceled, booking_changes, "
    "days_in_waiting_list, agent_id, company_id, parking_spaces, special_requests, created_at, "
    "checked_in_at, checked_out_at, canceled_at, no_show_at, anomaly_id"
)


def is_seeded(conn: psycopg.Connection) -> bool:
    exists = conn.execute("SELECT to_regclass('sim.config') IS NOT NULL").fetchone()[0]
    if not exists:
        return False
    row = conn.execute("SELECT value FROM sim.config WHERE key = 'seeded_at'").fetchone()
    return row is not None


def get_anchor(conn: psycopg.Connection) -> date:
    row = conn.execute("SELECT value FROM sim.config WHERE key = 'anchor_date'").fetchone()
    return date.fromisoformat(row[0])


def seed(conn: psycopg.Connection, anchor: date, data_dir: Path) -> None:
    """Create the PMS schema and load the full simulated timeline (once)."""
    if is_seeded(conn):
        log.info("PMS already seeded (anchor %s) - skipping", get_anchor(conn))
        return
    path = dataset.ensure_downloaded(data_dir)
    bookings = dataset.read(path)
    log.info("Building timeline for %d bookings, anchor %s", len(bookings), anchor)
    plan = build_plan(bookings, anchor)
    inventory = room_inventory(bookings)

    with conn.transaction():
        conn.execute((SQL_DIR / "pms_schema.sql").read_text())
        with conn.cursor() as cur:
            for name, h in HOTELS.items():
                cur.execute(
                    "INSERT INTO public.hotels (hotel_id, hotel_code, hotel_name, city,"
                    " country_code, timezone, total_rooms, pms_live_date)"
                    " VALUES (%s, %s, %s, %s, 'PT', 'Europe/Lisbon', %s, %s)",
                    (
                        h.hotel_id,
                        h.code,
                        h.name,
                        h.city,
                        h.total_rooms,
                        h.pms_live_date + timedelta(days=shift_days(anchor)),
                    ),
                )
                cur.executemany(
                    "INSERT INTO public.room_types"
                    " (hotel_id, room_type_code, room_type_name, room_count)"
                    " VALUES (%s, %s, %s, %s)",
                    [
                        (h.hotel_id, code, ROOM_TYPE_NAMES.get(code, f"Room type {code}"), rooms)
                        for code, rooms in inventory[name].items()
                    ],
                )
            with cur.copy(
                "COPY sim.guest_plan"
                " (guest_id, first_name, last_name, email, country_code, created_at) FROM STDIN"
            ) as copy:
                for row in plan.guests:
                    copy.write_row(row)
            with cur.copy(f"COPY sim.reservation_plan ({PLAN_COLUMNS}) FROM STDIN") as copy:
                for row in plan.reservations:
                    copy.write_row(row)
            cur.executemany(
                "INSERT INTO sim.config (key, value) VALUES (%s, %s)",
                [
                    ("anchor_date", anchor.isoformat()),
                    ("shift_days", str(shift_days(anchor))),
                    ("dataset_sha256", dataset.SHA256),
                    ("seeded_at", datetime.now(UTC).isoformat()),
                ],
            )
    log.info("Seeded %d guests, %d reservations", len(plan.guests), len(plan.reservations))


def reveal(conn: psycopg.Connection, as_of: datetime) -> tuple[int, int]:
    """Apply all source events up to `as_of`. Returns (guests_written, reservations_written)."""
    params = {"as_of": as_of}
    with conn.transaction():
        guests = conn.execute((SQL_DIR / "reveal_guests.sql").read_text(), params).rowcount
        reservations = conn.execute(
            (SQL_DIR / "reveal_reservations.sql").read_text(), params
        ).rowcount
    log.info("Revealed up to %s: %d guests, %d reservation changes", as_of, guests, reservations)
    return guests, reservations


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["seed", "reveal"])
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with psycopg.connect(settings.pms_admin_dsn()) as conn:
        if args.command == "seed":
            seed(conn, settings.sim_anchor_date() or date.today(), settings.DATA_DIR)
        reveal(conn, datetime.now(UTC))


if __name__ == "__main__":
    main()
