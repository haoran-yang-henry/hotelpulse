"""Tracking event contract, schema version 1 - the single source of truth.

The collector validates incoming events against it, the traffic simulator builds events
with it, and ``docs/tracking-plan.md`` documents it. Timestamps sent by the browser use the
*device* clock, which may be wrong; the warehouse corrects them with the collector clock
(``derived_ts = collector_ts - (sent_at - event_ts)``).
"""

from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = 1
MAX_BATCH_SIZE = 100


class EventName(StrEnum):
    PAGE_VIEW = "page_view"
    SEARCH_AVAILABILITY = "search_availability"
    SELECT_ROOM = "select_room"
    BEGIN_CHECKOUT = "begin_checkout"
    ADD_EXTRAS = "add_extras"
    PAYMENT_SUBMITTED = "payment_submitted"
    PAYMENT_FAILED = "payment_failed"
    BOOKING_CONFIRMED = "booking_confirmed"


# Properties each event must carry (others are allowed and passed through).
REQUIRED_PROPERTIES: dict[EventName, frozenset[str]] = {
    EventName.PAGE_VIEW: frozenset({"page_type"}),
    EventName.SEARCH_AVAILABILITY: frozenset({"hotel_code", "checkin", "checkout", "adults"}),
    EventName.SELECT_ROOM: frozenset({"hotel_code", "room_type_code", "nightly_rate", "currency"}),
    EventName.BEGIN_CHECKOUT: frozenset({"hotel_code", "room_type_code", "value", "currency"}),
    EventName.ADD_EXTRAS: frozenset({"extras"}),
    EventName.PAYMENT_SUBMITTED: frozenset({"value", "currency"}),
    EventName.PAYMENT_FAILED: frozenset({"error_code"}),
    EventName.BOOKING_CONFIRMED: frozenset(
        {"confirmation_code", "hotel_code", "value", "currency"}
    ),
}


class TrackingEvent(BaseModel):
    """One event as sent by the tracker."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = Field(description="Contract version")
    event_id: UUID = Field(description="Random id per event; used to drop duplicates")
    event_name: EventName = Field(description="One of the events listed below")
    event_ts: AwareDatetime = Field(description="When the event happened (device clock)")
    sent_at: AwareDatetime = Field(description="When the batch was sent (device clock)")
    anonymous_id: UUID = Field(description="First-party visitor id (cookie), set after consent")
    session_hint: str | None = Field(None, max_length=64, description="Client-side session id")
    page_url: str = Field(max_length=2048, description="Full URL incl. UTM parameters")
    referrer: str | None = Field(None, max_length=2048, description="document.referrer")
    locale: str | None = Field(None, max_length=35, description="Browser language, e.g. pt-PT")
    screen: str | None = Field(None, max_length=20, description="Screen size, e.g. 390x844")
    properties: dict[str, Any] = Field(
        default_factory=dict, description="Event-specific fields, see the table below"
    )

    @model_validator(mode="after")
    def _required_properties(self) -> "TrackingEvent":
        missing = REQUIRED_PROPERTIES[self.event_name] - self.properties.keys()
        if missing:
            raise ValueError(f"{self.event_name} requires properties {sorted(missing)}")
        return self


def json_schema() -> dict[str, Any]:
    return TrackingEvent.model_json_schema()
