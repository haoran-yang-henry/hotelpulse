"""Hotel Booking Demand dataset (Antonio, Almeida & Nunes, Data in Brief 2019, CC BY 4.0).

119,390 bookings of a city hotel (Lisbon) and a resort hotel (Algarve), arrivals
2015-07-01 .. 2017-08-31. Downloaded from the TidyTuesday mirror (no account needed)
and verified by SHA-256.
"""

import csv
import hashlib
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

URL = (
    "https://raw.githubusercontent.com/rfordatascience/tidytuesday/master/"
    "data/2020/2020-02-11/hotels.csv"
)
SHA256 = "7c2ae42a7353905ea136e5c2287f17c92c5435826598bfbb8491c6f0c7b1fc06"
FILENAME = "hotel_booking_demand.csv"

MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ],
        start=1,
    )
}  # fmt: skip


@dataclass(frozen=True, slots=True)
class Booking:
    """One dataset row, typed. Source quirks (e.g. negative ADR) are kept on purpose."""

    hotel: str
    is_canceled: bool
    lead_time: int
    arrival_date: date
    nights: int
    adults: int
    children: int | None
    babies: int
    meal: str
    country: str | None
    market_segment: str
    distribution_channel: str
    is_repeated_guest: bool
    previous_cancellations: int
    previous_bookings_not_canceled: int
    reserved_room_type: str
    assigned_room_type: str
    booking_changes: int
    deposit_type: str
    agent: str | None
    company: str | None
    days_in_waiting_list: int
    customer_type: str
    adr: float
    parking_spaces: int
    special_requests: int
    reservation_status: str
    reservation_status_date: date

    @property
    def booking_date(self) -> date:
        return self.arrival_date - timedelta(days=self.lead_time)

    @property
    def departure_date(self) -> date:
        return self.arrival_date + timedelta(days=self.nights)


def _nullable(value: str) -> str | None:
    return None if value in ("NULL", "NA", "") else value


def parse_row(row: dict[str, str]) -> Booking:
    children = _nullable(row["children"])
    return Booking(
        hotel=row["hotel"],
        is_canceled=row["is_canceled"] == "1",
        lead_time=int(row["lead_time"]),
        arrival_date=date(
            int(row["arrival_date_year"]),
            MONTHS[row["arrival_date_month"]],
            int(row["arrival_date_day_of_month"]),
        ),
        nights=int(row["stays_in_weekend_nights"]) + int(row["stays_in_week_nights"]),
        adults=int(row["adults"]),
        children=int(children) if children is not None else None,
        babies=int(row["babies"]),
        meal=row["meal"],
        country=_nullable(row["country"]),
        market_segment=row["market_segment"],
        distribution_channel=row["distribution_channel"],
        is_repeated_guest=row["is_repeated_guest"] == "1",
        previous_cancellations=int(row["previous_cancellations"]),
        previous_bookings_not_canceled=int(row["previous_bookings_not_canceled"]),
        reserved_room_type=row["reserved_room_type"],
        assigned_room_type=row["assigned_room_type"],
        booking_changes=int(row["booking_changes"]),
        deposit_type=row["deposit_type"],
        agent=_nullable(row["agent"]),
        company=_nullable(row["company"]),
        days_in_waiting_list=int(row["days_in_waiting_list"]),
        customer_type=row["customer_type"],
        adr=float(row["adr"]),
        parking_spaces=int(row["required_car_parking_spaces"]),
        special_requests=int(row["total_of_special_requests"]),
        reservation_status=row["reservation_status"],
        reservation_status_date=date.fromisoformat(row["reservation_status_date"]),
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ensure_downloaded(data_dir: Path) -> Path:
    target = data_dir / "external" / FILENAME
    if target.exists() and _sha256(target) == SHA256:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    log.info("Downloading dataset from %s", URL)
    response = httpx.get(URL, timeout=120, follow_redirects=True)
    response.raise_for_status()
    tmp = target.with_suffix(".part")
    tmp.write_bytes(response.content)
    if (digest := _sha256(tmp)) != SHA256:
        tmp.unlink()
        raise RuntimeError(f"Dataset checksum mismatch: expected {SHA256}, got {digest}")
    tmp.replace(target)
    return target


def read(path: Path) -> list[Booking]:
    with path.open(newline="", encoding="utf-8") as f:
        return [parse_row(row) for row in csv.DictReader(f)]
