"""Simulated operational sources: daily consumables export and review-platform export.

Both are derived from the simulated PMS so the cross-domain story holds:

* **Consumables** - usage per hotel, day and item is driven by rooms sold and breakfast
  guests that night (plus noise). Anomaly A2: the resort's towels laundered per room night
  rise by ~35 % after a laundry-supplier change.
* **Reviews** - about 12 % of checked-out stays leave a review a few days later, with a
  rating and the aspect sentiment the review-management tool delivers. Anomaly A3: when the
  hotel was (nearly) full during the stay, breakfast complaints are twice as likely.

Files land in the landing zone in the collector's format (gzip JSONL, partitioned by export
time); generation is deterministic per entity, and a watermark advances one day at a time.
"""

import logging
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg

from hotelpulse import landing
from hotelpulse.simulator import anomalies as anomaly_catalogue
from hotelpulse.simulator import pms

log = logging.getLogger(__name__)

TZ = ZoneInfo("Europe/Lisbon")
WATERMARK_KEY = "ops_sim_watermark"
EXPORT_HOUR = 2  # nightly export, after the night audit

# item -> (name, unit, driver, usage per driver unit, unit cost EUR)
ITEMS = {
    "towel_laundry": ("Towels laundered", "towel", "rooms", 1.8, 0.85),
    "toiletry_kit": ("Toiletry kits", "kit", "rooms", 1.0, 1.10),
    "coffee_capsule": ("Coffee capsules", "capsule", "rooms", 2.2, 0.35),
    "water_bottle": ("Water bottles", "bottle", "rooms", 1.5, 0.40),
    "breakfast_cover": ("Breakfast covers", "cover", "breakfast_guests", 1.0, 6.50),
}
REVIEW_SHARE = 0.12
PLATFORMS = {"booking_com": 0.55, "google": 0.30, "tripadvisor": 0.15}
# topic -> (probability of being mentioned, probability that a mention is negative)
TOPICS = {
    "cleanliness": (0.45, 0.10),
    "breakfast": (0.35, 0.09),
    "staff": (0.50, 0.06),
    "location": (0.40, 0.04),
    "noise": (0.15, 0.45),
    "value": (0.30, 0.20),
    "wifi": (0.12, 0.30),
}
PHRASES = {
    ("cleanliness", "positive"): "The room was spotless.",
    ("cleanliness", "negative"): "The bathroom was not properly cleaned.",
    ("breakfast", "positive"): "Lovely breakfast with fresh pastries and local fruit.",
    ("breakfast", "negative"): "Breakfast was chaotic - long queue and empty buffet trays.",
    ("staff", "positive"): "Reception staff were friendly and helpful.",
    ("staff", "negative"): "Check-in took far too long.",
    ("location", "positive"): "Great location, everything within walking distance.",
    ("location", "negative"): "A bit far from the centre.",
    ("noise", "positive"): "Quiet room, we slept very well.",
    ("noise", "negative"): "Street noise kept us awake at night.",
    ("value", "positive"): "Good value for money.",
    ("value", "negative"): "Too expensive for what you get.",
    ("wifi", "positive"): "Fast wifi everywhere.",
    ("wifi", "negative"): "The wifi kept dropping.",
}
BASE_RATING = {"CITY": 8.2, "RESORT": 8.6}


def rng_for(*key: object) -> random.Random:
    return random.Random(":".join(str(k) for k in key))


@dataclass(frozen=True)
class Night:
    hotel: str
    day: date
    rooms: int
    breakfast_guests: int
    total_rooms: int

    @property
    def occupancy(self) -> float:
        return self.rooms / self.total_rooms


NIGHTS_SQL = """
SELECT h.hotel_code, n::date, count(*), sum(CASE WHEN p.meal_plan IN ('BB', 'HB', 'FB')
       THEN coalesce(p.adults, 0) + coalesce(p.children, 0) + coalesce(p.babies, 0)
       ELSE 0 END), h.total_rooms
FROM sim.reservation_plan AS p
JOIN public.hotels AS h ON h.hotel_id = p.hotel_id
CROSS JOIN LATERAL generate_series(p.arrival_date::timestamp, (p.departure_date - 1)::timestamp,
                                   INTERVAL '1 day') AS n
WHERE p.canceled_at IS NULL AND p.no_show_at IS NULL
  AND n >= %(start)s AND n < %(end)s
GROUP BY h.hotel_code, n::date, h.total_rooms
"""

STAYS_SQL = """
SELECT p.reservation_id, p.confirmation_code, h.hotel_code, p.arrival_date, p.departure_date,
       p.checked_out_at
FROM sim.reservation_plan AS p
JOIN public.hotels AS h ON h.hotel_id = p.hotel_id
WHERE p.checked_out_at >= %(start)s AND p.checked_out_at < %(end)s
  AND p.departure_date > p.arrival_date
"""


def load_nights(conn: psycopg.Connection, start: date, end: date) -> dict[tuple[str, date], Night]:
    rows = conn.execute(NIGHTS_SQL, {"start": start, "end": end}).fetchall()
    return {(h, d): Night(h, d, rooms, guests or 0, total) for h, d, rooms, guests, total in rows}


# --------------------------------------------------------------------------- consumption


def consumption(night: Night, a2: anomaly_catalogue.Anomaly) -> list[dict]:
    """Usage records of one hotel and day (deterministic)."""
    out = []
    for code, (name, unit, driver, rate, cost) in ITEMS.items():
        rng = rng_for("usage", night.hotel, night.day.isoformat(), code)
        base = night.rooms if driver == "rooms" else night.breakfast_guests
        factor = rng.gauss(1.0, 0.06)
        if (
            a2.active_on(night.day)
            and night.hotel == a2.effect("inventory", "hotel")
            and code == a2.effect("inventory", "item")
        ):
            factor *= a2.effect("inventory", "factor", 1.0)
        out.append(
            {
                "export_date": night.day.isoformat(),
                "hotel_code": night.hotel,
                "item_code": code,
                "item_name": name,
                "unit": unit,
                "quantity": max(0, round(base * rate * factor)),
                "unit_cost_eur": cost,
            }
        )
    return out


# --------------------------------------------------------------------------- reviews


def review(
    stay: tuple, nights: dict[tuple[str, date], Night], a3: anomaly_catalogue.Anomaly
) -> dict | None:
    """Review left after a stay, or None (most guests do not review)."""
    reservation_id, code, hotel, arrival, departure, checked_out_at = stay
    rng = rng_for("review", reservation_id)
    if rng.random() >= REVIEW_SHARE:
        return None
    stay_nights = [
        nights[(hotel, arrival + timedelta(days=i))]
        for i in range((departure - arrival).days)
        if (hotel, arrival + timedelta(days=i)) in nights
    ]
    occupancy = sum(n.occupancy for n in stay_nights) / len(stay_nights) if stay_nights else 0
    busy = occupancy > a3.effect("reviews", "occupancy_above", 1.0)

    topics = []
    for topic, (p_mention, p_negative) in TOPICS.items():
        if topic == "noise" and hotel == "RESORT":
            p_negative /= 3  # quiet cliff-top resort
        if topic == "breakfast" and busy:
            p_negative = min(0.9, p_negative * a3.effect("reviews", "breakfast_complaint_factor"))
            p_mention = min(0.9, p_mention * 1.3)  # unhappy guests talk about it
        if rng.random() < p_mention:
            sentiment = "negative" if rng.random() < p_negative else "positive"
            topics.append({"topic": topic, "sentiment": sentiment})
    if not topics:
        topics.append({"topic": "staff", "sentiment": "positive"})

    negatives = sum(t["sentiment"] == "negative" for t in topics)
    positives = len(topics) - negatives
    rating = BASE_RATING[hotel] + rng.gauss(0, 0.6) - 1.6 * negatives + 0.2 * positives
    rating = round(min(10.0, max(1.0, rating)), 1)
    posted_at = checked_out_at + timedelta(days=rng.uniform(0.3, 7))
    return {
        "review_id": f"R{reservation_id}",
        "platform": rng.choices(list(PLATFORMS), weights=list(PLATFORMS.values()))[0],
        "hotel_code": hotel,
        "confirmation_code": code,
        "posted_at": posted_at.astimezone(UTC).isoformat(timespec="seconds"),
        "rating": rating,
        "title": "Great stay"
        if rating >= 8
        else "Good, but..."
        if rating >= 6
        else "Disappointing",
        "text": " ".join(PHRASES[(t["topic"], t["sentiment"])] for t in topics),
        "topics": topics,
    }


def title(rating: float) -> str:
    if rating >= 8:
        return "Great stay"
    return "Good, but..." if rating >= 6 else "Disappointing"


# --------------------------------------------------------------------------- export


def export_time(day: date) -> datetime:
    """Files for `day` are exported in the following night."""
    return datetime.combine(day + timedelta(days=1), time(EXPORT_HOUR), TZ).astimezone(UTC)


def export_days(conn: psycopg.Connection, landing_root: Path, first: date, last: date) -> dict:
    """Write consumption and review exports for days first..last (inclusive)."""
    catalogue = anomaly_catalogue.load(pms.get_anchor(conn))
    nights = load_nights(conn, first - timedelta(days=30), last + timedelta(days=1))
    stays_start = datetime.combine(first, time(), TZ)
    stays_end = datetime.combine(last + timedelta(days=1), time(), TZ)
    stays = conn.execute(
        STAYS_SQL,
        {"start": stays_start - timedelta(days=7), "end": stays_end},
    ).fetchall()

    usage_writer = landing.LandingWriter(landing_root / landing.INVENTORY, max_buffered=10**9)
    review_writer = landing.LandingWriter(landing_root / landing.REVIEWS, max_buffered=10**9)
    by_day: dict[date, list[dict]] = defaultdict(list)
    for stay in stays:
        r = review(stay, nights, catalogue["A3"])
        if r is None:
            continue
        posted = datetime.fromisoformat(r["posted_at"]).astimezone(TZ).date()
        if first <= posted <= last:
            by_day[posted].append(r)

    usage_rows = reviews = 0
    day = first
    while day <= last:
        records = [
            rec
            for hotel in ("CITY", "RESORT")
            if (hotel, day) in nights
            for rec in consumption(nights[(hotel, day)], catalogue["A2"])
        ]
        usage_writer.add_many(records, export_time(day))
        review_writer.add_many(by_day.get(day, []), export_time(day))
        usage_rows += len(records)
        reviews += len(by_day.get(day, []))
        day += timedelta(days=1)
    usage_writer.flush()
    review_writer.flush()
    return {"consumption_rows": usage_rows, "reviews": reviews}


def get_watermark(conn: psycopg.Connection) -> date | None:
    row = conn.execute("SELECT value FROM sim.config WHERE key = %s", (WATERMARK_KEY,)).fetchone()
    return date.fromisoformat(row[0]) if row else None


def set_watermark(conn: psycopg.Connection, value: date) -> None:
    conn.execute(
        "INSERT INTO sim.config (key, value) VALUES (%s, %s)"
        " ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        (WATERMARK_KEY, value.isoformat()),
    )


def first_reporting_day(conn: psycopg.Connection) -> date:
    """Operational systems start with the PMS go-live of the first hotel."""
    return conn.execute("SELECT min(pms_live_date) FROM public.hotels").fetchone()[0]


def run(conn: psycopg.Connection, landing_root: Path, now: datetime) -> dict:
    """Export every complete day since the watermark (yesterday at the latest)."""
    yesterday = now.astimezone(TZ).date() - timedelta(days=1)
    watermark = get_watermark(conn)
    first = (watermark + timedelta(days=1)) if watermark else first_reporting_day(conn)
    if first > yesterday:
        return {"consumption_rows": 0, "reviews": 0}
    result = export_days(conn, landing_root, first, yesterday)
    set_watermark(conn, yesterday)
    conn.commit()
    log.info("Exported %s .. %s: %s", first, yesterday, result)
    return result
