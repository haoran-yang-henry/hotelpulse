"""Simulated website traffic, consistent with the simulated PMS (see ADR-0014).

* Every website booking in the PMS timeline gets a converting session that ends with
  ``booking_confirmed`` and its confirmation code - plus 0-3 earlier visits of the same
  visitor from other traffic sources (multi-touch attribution).
* Bookings that leaked to an OTA during anomaly A1 get a mobile session that ends with a
  failed payment (``gateway_timeout``), shortly before the OTA booking was made.
* Non-converting browsing sessions and bots fill up the traffic.

Generation is deterministic per entity (booking, hour), so any time window can be generated
again with identical event ids: a replay only yields duplicates, which staging removes.
Visitors who reject analytics cookies (anomaly A5 lowers the consent rate) or block the
tracker produce no events at all. Realistic noise is added on purpose: duplicated deliveries,
invalid events and devices with a wrong clock.
"""

import json
import logging
import math
import random
import uuid
from collections import Counter, defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx
import psycopg

from hotelpulse import landing
from hotelpulse.simulator import anomalies as anomaly_catalogue
from hotelpulse.simulator import pms
from hotelpulse.tracking.collector import process

log = logging.getLogger(__name__)

SITE = "https://www.hotelpulse.example"
TZ = ZoneInfo("Europe/Lisbon")
TRACKING_GO_LIVE_DAYS = 196  # website tracking went live this many days before the anchor
ENGINE_FIRST_ID = 9_000_001  # bookings made on the demo website are tracked for real
TARGET_CONVERSION = 0.025
BASE_CONSENT_RATE = 0.80
ADBLOCK_RATE = 0.07
BOT_SHARE = 0.03
DUPLICATE_RATE = 0.007
INVALID_RATE = 0.002
CLOCK_SKEW_SHARE = 0.02
RETURNING_SHARE = 0.25
LOOKAHEAD = timedelta(days=21)  # earlier visits happen up to 20 days before a booking
SAFETY_LAG = timedelta(minutes=30)  # only emit sessions that are surely over
MAX_CATCH_UP = timedelta(days=14)
WATERMARK_KEY = "web_sim_watermark"

# relative traffic per local hour of day
DIURNAL = (2, 1, 1, 1, 1, 2, 3, 5, 6, 7, 7, 7, 7, 7, 6, 6, 6, 7, 8, 9, 10, 9, 7, 4)

DEVICE_MIX = {"mobile": 0.58, "desktop": 0.37, "tablet": 0.05}
BOOKER_DEVICE_MIX = {"mobile": 0.50, "desktop": 0.45, "tablet": 0.05}
USER_AGENTS = {
    "desktop": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/141.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/19.0 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:143.0) Gecko/20100101 Firefox/143.0",
    ],
    "mobile": [
        "Mozilla/5.0 (iPhone; CPU iPhone OS 19_0 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/19.0 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (Linux; Android 16; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/141.0.0.0 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 15; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/141.0.0.0 Mobile Safari/537.36",
    ],
    "tablet": [
        "Mozilla/5.0 (iPad; CPU OS 19_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/19.0 Mobile/15E148 Safari/604.1",
    ],
    "bot": [
        "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
        "Mozilla/5.0 (compatible; AhrefsBot/7.0; +http://ahrefs.com/robot/)",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "HeadlessChrome/141.0.0.0 Safari/537.36",
    ],
}
SCREENS = {
    "desktop": ["1920x1080", "1536x864", "2560x1440", "1440x900"],
    "mobile": ["390x844", "393x852", "412x915", "360x780"],
    "tablet": ["820x1180", "1024x1366"],
    "bot": ["1280x720"],
}
LOCALES = {
    "en-GB": 0.24, "pt-PT": 0.24, "de-DE": 0.12, "fr-FR": 0.12, "es-ES": 0.12, "en-US": 0.10,
    "it-IT": 0.06,
}  # fmt: skip

# traffic source -> (utm parameters, external referrer, landing path)
SOURCES: dict[str, tuple[dict[str, str] | None, str | None, str]] = {
    "direct": (None, None, "/"),
    "organic": (None, "https://www.google.com/", "/"),
    "paid_brand": (
        {"utm_source": "google", "utm_medium": "cpc", "utm_campaign": "brand"},
        "https://www.google.com/",
        "/",
    ),
    "paid_generic": (
        {"utm_source": "google", "utm_medium": "cpc", "utm_campaign": "generic_portugal_hotels"},
        "https://www.google.com/",
        "/hotels/{hotel}",
    ),
    "metasearch": (
        {"utm_source": "trivago", "utm_medium": "metasearch", "utm_campaign": "pt_listing"},
        "https://www.trivago.com/",
        "/hotels/{hotel}",
    ),
    "email": (
        {"utm_source": "newsletter", "utm_medium": "email", "utm_campaign": "seasonal_offers"},
        None,
        "/offers",
    ),
    "social": (
        {"utm_source": "instagram", "utm_medium": "social", "utm_campaign": "stories"},
        "https://www.instagram.com/",
        "/offers",
    ),
    "referral": (None, "https://www.visitportugal.com/", "/hotels/{hotel}"),
}
FIRST_TOUCH_MIX = {
    "metasearch": 0.30, "paid_generic": 0.25, "organic": 0.25, "social": 0.10, "referral": 0.10,
}  # fmt: skip
CLOSING_MIX = {
    "direct": 0.35,
    "paid_brand": 0.25,
    "organic": 0.20,
    "email": 0.12,
    "metasearch": 0.08,
}
SINGLE_VISIT_MIX = {
    "direct": 0.25, "organic": 0.25, "paid_brand": 0.15, "metasearch": 0.15, "email": 0.10,
    "paid_generic": 0.05, "social": 0.03, "referral": 0.02,
}  # fmt: skip
BROWSING_MIX = {
    "organic": 0.30, "direct": 0.20, "metasearch": 0.15, "paid_generic": 0.12, "social": 0.10,
    "paid_brand": 0.05, "referral": 0.05, "email": 0.03,
}  # fmt: skip
HOTEL_SLUGS = {"CITY": "lisbon-city", "RESORT": "algarve-resort"}
CONTENT_PAGES = ("/hotels/lisbon-city", "/hotels/algarve-resort", "/offers", "/gallery", "/faq")
DECLINE_CODES = {"card_declined": 0.6, "insufficient_funds": 0.25, "3ds_failed": 0.15}


# --------------------------------------------------------------------------- helpers


def rng_for(*key: object) -> random.Random:
    """Deterministic RNG per entity (string seeds are hashed with SHA-512 by `random`)."""
    return random.Random(":".join(str(k) for k in key))


def pick(rng: random.Random, mix: dict[str, float]) -> str:
    return rng.choices(list(mix), weights=list(mix.values()))[0]


def new_uuid(rng: random.Random) -> str:
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def iso(ts: datetime) -> str:
    return ts.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def hours(start: datetime, end: datetime) -> Iterator[datetime]:
    hour = start.replace(minute=0, second=0, microsecond=0)
    while hour < end:
        yield hour
        hour += timedelta(hours=1)


# --------------------------------------------------------------------------- model


@dataclass(frozen=True)
class WebBooking:
    reservation_id: int
    confirmation_code: str
    hotel_code: str
    room_type_code: str
    arrival: date
    departure: date
    adults: int
    children: int
    adr: float
    meal_plan: str
    created_at: datetime
    leaked: bool  # A1: moved to an OTA after the website payment failed

    @property
    def nights(self) -> int:
        return (self.departure - self.arrival).days


@dataclass(frozen=True)
class Visitor:
    anonymous_id: str
    device: str
    user_agent: str
    screen: str
    locale: str
    clock_skew: timedelta
    tracked: bool  # accepted analytics cookies and does not block the tracker


@dataclass(frozen=True)
class SimEvent:
    true_ts: datetime
    visitor: Visitor
    payload: dict  # as the tracker builds it; `sent_at` is added at delivery
    delivery_delay: timedelta


@dataclass(frozen=True)
class Stay:
    hotel_code: str
    checkin: date
    checkout: date
    adults: int
    children: int
    room_type_code: str
    nightly_rate: float

    @property
    def nights(self) -> int:
        return (self.checkout - self.checkin).days

    @property
    def value(self) -> float:
        return round(self.nightly_rate * self.nights, 2)

    def query(self, room: bool = False) -> dict[str, object]:
        q: dict[str, object] = {
            "hotel": self.hotel_code,
            "checkin": self.checkin.isoformat(),
            "checkout": self.checkout.isoformat(),
            "adults": self.adults,
            "children": self.children,
        }
        if room:
            q["room"] = self.room_type_code
        return q


class SessionBuilder:
    """Emits the events of one visit, advancing a clock between interactions."""

    def __init__(
        self, rng: random.Random, visitor: Visitor, start: datetime, source: str, hotel: str
    ):
        self.rng, self.visitor, self.ts = rng, visitor, start
        self.source, self.hotel = source, hotel
        self.hint = f"{rng.getrandbits(64):016x}"
        self.events: list[SimEvent] = []
        self.url: str = SITE + "/"
        self.referrer: str | None = None

    def wait(self, low_s: float, high_s: float) -> None:
        self.ts += timedelta(seconds=self.rng.uniform(low_s, high_s))

    def _delay(self) -> timedelta:
        if self.visitor.device != "desktop" and self.rng.random() < 0.15:
            return timedelta(seconds=self.rng.uniform(5, 90))  # flaky mobile network
        return timedelta(seconds=self.rng.uniform(0.2, 2.5))

    def track(self, name: str, properties: dict) -> None:
        v = self.visitor
        payload = {
            "schema_version": 1,
            "event_id": new_uuid(self.rng),
            "event_name": name,
            "event_ts": iso(self.ts + v.clock_skew),
            "anonymous_id": v.anonymous_id,
            "session_hint": self.hint,
            "page_url": self.url,
            "referrer": self.referrer,
            "locale": v.locale,
            "screen": v.screen,
            "properties": properties,
        }
        self.events.append(SimEvent(self.ts, v, payload, self._delay()))

    def land(self) -> None:
        utm, referrer, path = SOURCES[self.source]
        url = SITE + path.format(hotel=HOTEL_SLUGS[self.hotel])
        self.url = url + ("?" + urlencode(utm) if utm else "")
        self.referrer = referrer
        self.track("page_view", {"page_type": "landing"})

    def page(self, path: str, page_type: str, query: dict | None = None) -> None:
        self.referrer = self.url
        self.url = SITE + path + ("?" + urlencode(query) if query else "")
        self.track("page_view", {"page_type": page_type})

    # ---- funnel steps
    def browse(self, pages: int) -> None:
        for _ in range(pages):
            self.wait(15, 90)
            self.page(self.rng.choice(CONTENT_PAGES), "content")

    def search(self, stay: Stay) -> None:
        self.wait(10, 60)
        self.page("/rooms", "rooms", stay.query())
        self.track(
            "search_availability",
            {
                "hotel_code": stay.hotel_code,
                "checkin": stay.checkin.isoformat(),
                "checkout": stay.checkout.isoformat(),
                "nights": stay.nights,
                "adults": stay.adults,
                "children": stay.children,
            },
        )

    def select(self, stay: Stay) -> None:
        self.wait(20, 120)
        self.track(
            "select_room",
            {
                "hotel_code": stay.hotel_code,
                "room_type_code": stay.room_type_code,
                "nightly_rate": stay.nightly_rate,
                "currency": "EUR",
            },
        )
        self.wait(0.5, 2)
        self.page("/checkout", "checkout", stay.query(room=True))
        self.track(
            "begin_checkout",
            {
                "hotel_code": stay.hotel_code,
                "room_type_code": stay.room_type_code,
                "value": stay.value,
                "currency": "EUR",
            },
        )

    def extras(self, stay: Stay) -> None:
        self.wait(10, 40)
        value = round(14.0 * (stay.adults + stay.children) * stay.nights, 2)
        self.track("add_extras", {"extras": ["breakfast"], "value": value, "currency": "EUR"})

    def pay(self, stay: Stay) -> None:
        self.wait(40, 180)
        method = "card" if self.rng.random() < 0.85 else "paypal"
        self.track(
            "payment_submitted", {"payment_method": method, "value": stay.value, "currency": "EUR"}
        )

    def fail(self, stay: Stay, error_code: str) -> None:
        self.wait(3, 40)
        self.track(
            "payment_failed", {"error_code": error_code, "value": stay.value, "currency": "EUR"}
        )

    def confirm(self, stay: Stay, code: str) -> None:
        self.wait(2, 8)
        self.page(f"/confirmation/{code}", "confirmation")
        self.track(
            "booking_confirmed",
            {
                "confirmation_code": code,
                "hotel_code": stay.hotel_code,
                "room_type_code": stay.room_type_code,
                "checkin": stay.checkin.isoformat(),
                "checkout": stay.checkout.isoformat(),
                "value": stay.value,
                "currency": "EUR",
            },
        )


class TrafficModel:
    """Generates the website events of any time window, consistently with the PMS."""

    def __init__(self, anchor: date, bookings: list[WebBooking]):
        self.go_live = datetime.combine(
            anchor - timedelta(days=TRACKING_GO_LIVE_DAYS), time(), TZ
        ).astimezone(UTC)
        catalogue = anomaly_catalogue.load(anchor)
        self.a1, self.a5 = catalogue["A1"], catalogue["A5"]
        self.bookings = sorted(bookings, key=lambda b: b.created_at)
        self.bookings_per_day = Counter(b.created_at.astimezone(TZ).date() for b in bookings)
        self.rates: dict[str, list[tuple[str, float]]] = defaultdict(list)
        for b in bookings:
            if 20 <= b.adr <= 1000:
                self.rates[b.hotel_code].append((b.room_type_code, b.adr))

    # ---- volumes and visitors
    def browsing_sessions_per_day(self, day: date) -> float:
        week = [self.bookings_per_day.get(day + timedelta(days=d), 0) for d in range(-3, 4)]
        return max(sum(week) / 7, 2.0) * (1 / TARGET_CONVERSION - 1)

    def consent_rate(self, day: date) -> float:
        if self.a5.active_on(day):
            return self.a5.effect("web", "consent_rate", BASE_CONSENT_RATE)
        return BASE_CONSENT_RATE

    def visitor(self, key: str, first_seen: date, device: str | None = None) -> Visitor:
        rng = rng_for("visitor", key)
        anonymous_id = new_uuid(rng)
        device = device or pick(rng, DEVICE_MIX)
        skew = timedelta(0)
        if rng.random() < CLOCK_SKEW_SHARE:
            skew = timedelta(hours=rng.choice((-1, 1)) * rng.uniform(1, 36))
        tracked = rng.random() < self.consent_rate(first_seen) and rng.random() >= ADBLOCK_RATE
        return Visitor(
            anonymous_id=anonymous_id,
            device=device,
            user_agent=rng.choice(USER_AGENTS[device]),
            screen=rng.choice(SCREENS[device]),
            locale=pick(rng, LOCALES),
            clock_skew=skew,
            tracked=tracked,
        )

    def random_stay(self, rng: random.Random, day: date) -> Stay:
        hotel = "CITY" if rng.random() < 0.6 else "RESORT"
        room, rate = rng.choice(self.rates[hotel] or [("A", 100.0)])
        checkin = day + timedelta(days=int(rng.expovariate(1 / 45)) + 1)
        nights = rng.choice((1, 2, 2, 3, 3, 4, 5, 7))
        return Stay(
            hotel_code=hotel,
            checkin=checkin,
            checkout=checkin + timedelta(days=nights),
            adults=rng.choice((1, 2, 2, 2, 3)),
            children=rng.choice((0, 0, 0, 1, 2)),
            room_type_code=room,
            nightly_rate=round(rate * rng.uniform(0.9, 1.15), 2),
        )

    # ---- sessions driven by PMS bookings
    def booking_sessions(self, b: WebBooking) -> list[list[SimEvent]]:
        rng = rng_for("booking", b.reservation_id)
        stay = Stay(
            b.hotel_code,
            b.arrival,
            b.departure,
            b.adults,
            b.children,
            b.room_type_code,
            round(b.adr, 2),
        )
        prior = rng.choices((0, 1, 2, 3), weights=(0.55, 0.25, 0.15, 0.05))[0]
        prior_starts = sorted(
            b.created_at - timedelta(days=rng.uniform(0.2, 20)) for _ in range(prior)
        )
        first_seen = (prior_starts[0] if prior_starts else b.created_at).astimezone(TZ).date()
        device = "mobile" if b.leaked else pick(rng, BOOKER_DEVICE_MIX)
        visitor = self.visitor(f"booking:{b.reservation_id}", first_seen, device)

        sessions = []
        for i, start in enumerate(prior_starts):
            source = pick(rng, FIRST_TOUCH_MIX if i == 0 else BROWSING_MIX)
            s = SessionBuilder(rng, visitor, start, source, b.hotel_code)
            s.land()
            s.browse(rng.randint(0, 2))
            if rng.random() < 0.7:
                s.search(stay)
                if rng.random() < 0.35:
                    s.select(stay)
            sessions.append(s.events)

        source = pick(rng, CLOSING_MIX if prior else SINGLE_VISIT_MIX)
        minutes_before = rng.uniform(6, 20) if not b.leaked else rng.uniform(15, 45)
        s = SessionBuilder(rng, visitor, b.created_at - timedelta(minutes=minutes_before), source,
                           b.hotel_code)  # fmt: skip
        s.land()
        s.browse(rng.choice((0, 0, 1, 2)))
        s.search(stay)
        s.select(stay)
        if b.meal_plan in ("BB", "HB", "FB") and rng.random() < 0.7:
            s.extras(stay)
        s.pay(stay)
        if b.leaked:
            error = self.a1.effect("web", "error_code", "gateway_timeout")
            s.fail(stay, error)
            if rng.random() < self.a1.effect("web", "retry_share", 0.0):
                s.pay(stay)
                s.fail(stay, error)
        else:
            s.confirm(stay, b.confirmation_code)
        sessions.append(s.events)
        return sessions

    # ---- browsing sessions and bots, seeded per hour
    def hourly_sessions(self, hour: datetime) -> list[list[SimEvent]]:
        rng = rng_for("hour", hour.astimezone(UTC).isoformat())
        local = hour.astimezone(TZ)
        day = local.date()
        expected = self.browsing_sessions_per_day(day) * DIURNAL[local.hour] / sum(DIURNAL)
        count = max(0, round(rng.gauss(expected, math.sqrt(expected))))
        iso_year, iso_week, _ = day.isocalendar()
        pool_size = max(20, int(self.browsing_sessions_per_day(day) * 7 * 0.3))
        sessions = []
        for i in range(count):
            start = hour + timedelta(seconds=rng.uniform(0, 3600))
            if rng.random() < RETURNING_SHARE:
                key = f"pool:{iso_year}-W{iso_week}:{rng.randrange(pool_size)}"
                visitor = self.visitor(key, date.fromisocalendar(iso_year, iso_week, 1))
            else:
                visitor = self.visitor(f"hour:{hour.isoformat()}:{i}", day)
            sessions.append(self.browsing_session(rng, visitor, start))
        bots = max(0, round(rng.gauss(expected * BOT_SHARE, math.sqrt(expected * BOT_SHARE))))
        for i in range(bots):
            sessions.append(
                self.bot_session(rng, hour + timedelta(seconds=rng.uniform(0, 3600)), i)
            )
        return sessions

    def browsing_session(self, rng: random.Random, visitor: Visitor, start: datetime) -> list:
        day = start.astimezone(TZ).date()
        stay = self.random_stay(rng, day)
        s = SessionBuilder(rng, visitor, start, pick(rng, BROWSING_MIX), stay.hotel_code)
        s.land()
        s.browse(rng.choice((0, 0, 1, 1, 2, 3)))
        if rng.random() < 0.38:
            s.search(stay)
            if rng.random() < 0.4:
                s.select(stay)
                if rng.random() < 0.3:
                    s.extras(stay)
                if rng.random() < 0.03:  # baseline payment declines
                    s.pay(stay)
                    s.fail(stay, pick(rng, DECLINE_CODES))
        return s.events

    def bot_session(self, rng: random.Random, start: datetime, i: int) -> list[SimEvent]:
        bot_rng = rng_for("bot", start.isoformat(), i)
        visitor = Visitor(
            anonymous_id=new_uuid(bot_rng),
            device="bot",
            user_agent=bot_rng.choice(USER_AGENTS["bot"]),
            screen=SCREENS["bot"][0],
            locale="en-US",
            clock_skew=timedelta(0),
            tracked=True,  # crawlers that run JavaScript simply click "accept"
        )
        s = SessionBuilder(bot_rng, visitor, start, "direct", "CITY")
        s.land()
        for _ in range(bot_rng.randint(3, 12)):
            s.wait(0.3, 3)
            s.page(bot_rng.choice(("/", *CONTENT_PAGES)), "content")
        return s.events

    # ---- windows
    def events(self, start: datetime, end: datetime) -> list[SimEvent]:
        """Events of all sessions that *start* within [start, end)."""
        start = max(start, self.go_live)
        if end <= start:
            return []
        out: list[SimEvent] = []
        for b in self.bookings:
            if b.created_at < start or b.created_at >= end + LOOKAHEAD:
                continue
            for session in self.booking_sessions(b):
                if start <= session[0].true_ts < end:
                    out.extend(session)
        for hour in hours(start, end):
            for session in self.hourly_sessions(hour):
                if start <= session[0].true_ts < end:
                    out.extend(session)
        return out


# --------------------------------------------------------------------------- delivery


def corrupt(payload: dict, rng: random.Random) -> dict:
    """Break an event the way buggy clients do."""
    broken = dict(payload)
    match rng.randrange(4):
        case 0:
            del broken["anonymous_id"]
        case 1:
            broken["event_name"] = "PageView"
        case 2:
            broken["event_ts"] = "yesterday"
        case _:
            broken["properties"] = {}
    return broken


def deliveries(events: list[SimEvent]) -> list[tuple[datetime, Visitor, dict]]:
    """What reaches the collector: untracked visitors are dropped, noise is added."""
    out = []
    for e in events:
        if not e.visitor.tracked:
            continue
        rng = rng_for("noise", e.payload["event_id"])
        payload = corrupt(e.payload, rng) if rng.random() < INVALID_RATE else e.payload
        delivered = e.true_ts + e.delivery_delay
        out.append((delivered, e.visitor, payload))
        if rng.random() < DUPLICATE_RATE:  # retried request, same event id
            out.append((delivered + timedelta(seconds=rng.uniform(10, 300)), e.visitor, payload))
    return out


def write_landing(events: list[SimEvent], landing_root: Path) -> tuple[int, int]:
    """Write events straight to the landing zone in the collector's output format."""
    events_writer = landing.LandingWriter(landing_root / landing.WEB_EVENTS, max_buffered=10**9)
    rejected_writer = landing.LandingWriter(
        landing_root / landing.WEB_EVENTS_REJECTED, max_buffered=10**9
    )
    accepted_total = rejected_total = 0
    for delivered, visitor, payload in deliveries(events):
        body = {**payload, "sent_at": iso(delivered + visitor.clock_skew)}
        accepted, rejected = process([body], visitor.user_agent, delivered)
        events_writer.add_many(accepted, delivered)
        rejected_writer.add_many(rejected, delivered)
        accepted_total += len(accepted)
        rejected_total += len(rejected)
    events_writer.flush()
    rejected_writer.flush()
    return accepted_total, rejected_total


def post_to_collector(events: list[SimEvent], collector_url: str, now: datetime) -> int:
    """Send events like browsers do: one request per visitor batch, device-clock sent_at."""
    batches: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for _, visitor, payload in deliveries(events):
        body = {**payload, "sent_at": iso(now + visitor.clock_skew)}
        batches[(visitor.user_agent, visitor.anonymous_id)].append(body)
    sent = 0
    with httpx.Client(base_url=collector_url, timeout=30) as client:
        for (user_agent, _), batch in batches.items():
            for i in range(0, len(batch), 100):
                chunk = batch[i : i + 100]
                response = client.post(
                    "/collect",
                    content=json.dumps({"events": chunk}),
                    headers={"User-Agent": user_agent, "Content-Type": "text/plain"},
                )
                response.raise_for_status()
                sent += len(chunk)
    return sent


# --------------------------------------------------------------------------- database

BOOKINGS_SQL = """
SELECT p.reservation_id, p.confirmation_code, h.hotel_code,
       coalesce(p.assigned_room_type, p.reserved_room_type), p.arrival_date, p.departure_date,
       p.adults, coalesce(p.children, 0), p.adr::float, p.meal_plan, p.created_at,
       coalesce(p.anomaly_id = 'A1', FALSE)
FROM sim.reservation_plan AS p
JOIN public.hotels AS h ON h.hotel_id = p.hotel_id
WHERE (p.booking_source = 'website' OR p.anomaly_id = 'A1')
  AND p.reservation_id < %(engine_first_id)s
  AND p.departure_date > p.arrival_date
  AND p.created_at >= %(start)s AND p.created_at < %(end)s
"""


def load_model(conn: psycopg.Connection, start: datetime, end: datetime) -> TrafficModel:
    rows = conn.execute(
        BOOKINGS_SQL,
        {
            "engine_first_id": ENGINE_FIRST_ID,
            "start": start - timedelta(days=7),
            "end": end + LOOKAHEAD + timedelta(days=7),
        },
    ).fetchall()
    return TrafficModel(pms.get_anchor(conn), [WebBooking(*r) for r in rows])


def get_watermark(conn: psycopg.Connection) -> datetime | None:
    row = conn.execute("SELECT value FROM sim.config WHERE key = %s", (WATERMARK_KEY,)).fetchone()
    return datetime.fromisoformat(row[0]) if row else None


def set_watermark(conn: psycopg.Connection, value: datetime) -> None:
    conn.execute(
        "INSERT INTO sim.config (key, value) VALUES (%s, %s)"
        " ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        (WATERMARK_KEY, value.isoformat()),
    )


def window_end(now: datetime) -> datetime:
    end = now - SAFETY_LAG
    return end.replace(minute=end.minute - end.minute % 5, second=0, microsecond=0)


def seed_history(conn: psycopg.Connection, landing_root: Path, now: datetime) -> None:
    """Write the website history since tracking go-live to the landing zone (once)."""
    if get_watermark(conn) is not None:
        log.info("Website history already seeded - skipping")
        return
    anchor = pms.get_anchor(conn)
    start = datetime.combine(anchor - timedelta(days=TRACKING_GO_LIVE_DAYS), time(), TZ)
    end = window_end(now)
    model = load_model(conn, start, end)
    accepted = rejected = 0
    day = model.go_live
    while day < end:  # day by day keeps memory flat
        a, r = write_landing(model.events(day, min(day + timedelta(days=1), end)), landing_root)
        accepted, rejected = accepted + a, rejected + r
        day += timedelta(days=1)
    set_watermark(conn, end)
    conn.commit()
    log.info("Seeded website history: %d events, %d rejected", accepted, rejected)


def run_live(conn: psycopg.Connection, collector_url: str, now: datetime) -> int:
    """Send the traffic since the watermark to the collector and advance the watermark."""
    watermark = get_watermark(conn)
    end = window_end(now)
    start = max(watermark or end - timedelta(hours=1), end - MAX_CATCH_UP)
    if end <= start:
        return 0
    model = load_model(conn, start, end)
    sent = post_to_collector(model.events(start, end), collector_url, now)
    set_watermark(conn, end)
    conn.commit()
    log.info("Sent %d events for %s .. %s", sent, start, end)
    return sent
