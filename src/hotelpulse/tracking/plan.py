"""Render the tracking plan (docs/tracking-plan.md) from the event contract.

    python -m hotelpulse.tracking.plan > docs/tracking-plan.md

A unit test fails when the committed document is out of date, so the plan the web team reads
is always the contract the collector enforces.
"""

from hotelpulse.tracking.schema import REQUIRED_PROPERTIES, SCHEMA_VERSION, EventName, TrackingEvent

FUNNEL_STEP = {
    EventName.PAGE_VIEW: "Visit",
    EventName.SEARCH_AVAILABILITY: "Searched availability",
    EventName.SELECT_ROOM: "Selected a room",
    EventName.BEGIN_CHECKOUT: "Selected a room",
    EventName.ADD_EXTRAS: "-",
    EventName.PAYMENT_SUBMITTED: "Attempted payment",
    EventName.PAYMENT_FAILED: "Attempted payment",
    EventName.BOOKING_CONFIRMED: "Booked",
}
WHEN = {
    EventName.PAGE_VIEW: "Every page load (`page_type`: home, rooms, checkout, confirmation, ...)",
    EventName.SEARCH_AVAILABILITY: "Availability results are shown",
    EventName.SELECT_ROOM: "A room offer is selected (sent immediately - the page navigates away)",
    EventName.BEGIN_CHECKOUT: "The checkout page is shown",
    EventName.ADD_EXTRAS: "An extra (e.g. breakfast) is added",
    EventName.PAYMENT_SUBMITTED: "The payment form is submitted (sent immediately)",
    EventName.PAYMENT_FAILED: "The payment provider declines or fails",
    EventName.BOOKING_CONFIRMED: "The confirmation page is first shown (not on reload)",
}


def render() -> str:
    fields = TrackingEvent.model_json_schema()["properties"]
    lines = [
        "# Tracking plan",
        "",
        f"Contract version **{SCHEMA_VERSION}** - generated from `hotelpulse.tracking.schema` by",
        "`python -m hotelpulse.tracking.plan`; do not edit by hand.",
        "",
        "The tracker (`/tracker.js` on the collector) sends nothing before the visitor accepts",
        "analytics cookies. Events are batched and posted as `text/plain` JSON",
        '(`{"events": [...]}`, at most 100 per request) to `/collect`. Invalid events are kept',
        "in a dead-letter dataset with the validation error.",
        "",
        "## Event envelope",
        "",
        "| Field | Type | Description |",
        "|---|---|---|",
    ]
    required = set(TrackingEvent.model_json_schema()["required"])
    for name, spec in fields.items():
        kind = spec.get("type") or " / ".join(
            t.get("type", "enum") for t in spec.get("anyOf", [{"type": "enum"}])
        )
        if spec.get("format"):
            kind += f" ({spec['format']})"
        note = spec.get("description", "")
        lines.append(f"| `{name}`{'' if name in required else ' (optional)'} | {kind} | {note} |")
    lines += [
        "",
        "The collector adds `collector_ts` (server clock) and `user_agent`. The warehouse derives",
        "`derived_ts = collector_ts - (sent_at - event_ts)` to correct wrong device clocks.",
        "",
        "## Events",
        "",
        "| Event | Fired when | Required properties | Funnel step |",
        "|---|---|---|---|",
    ]
    for event in EventName:
        props = ", ".join(f"`{p}`" for p in sorted(REQUIRED_PROPERTIES[event]))
        lines.append(f"| `{event}` | {WHEN[event]} | {props} | {FUNNEL_STEP[event]} |")
    lines += [
        "",
        "## Identifiers and privacy",
        "",
        "- `anonymous_id`: random first-party id in the `hp_aid` cookie, set only after consent.",
        "- `confirmation_code` (on `booking_confirmed`) is the only link to the PMS reservation.",
        "- No IP address, name or e-mail address is collected.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    print(render(), end="")
