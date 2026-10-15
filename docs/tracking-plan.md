# Tracking plan

Contract version **1** - generated from `hotelpulse.tracking.schema` by
`python -m hotelpulse.tracking.plan`; do not edit by hand.

The tracker (`/tracker.js` on the collector) sends nothing before the visitor accepts
analytics cookies. Events are batched and posted as `text/plain` JSON
(`{"events": [...]}`, at most 100 per request) to `/collect`. Invalid events are kept
in a dead-letter dataset with the validation error.

## Event envelope

| Field | Type | Description |
|---|---|---|
| `schema_version` | integer | Contract version |
| `event_id` | string (uuid) | Random id per event; used to drop duplicates |
| `event_name` | enum | One of the events listed below |
| `event_ts` | string (date-time) | When the event happened (device clock) |
| `sent_at` | string (date-time) | When the batch was sent (device clock) |
| `anonymous_id` | string (uuid) | First-party visitor id (cookie), set after consent |
| `session_hint` (optional) | string / null | Client-side session id |
| `page_url` | string | Full URL incl. UTM parameters |
| `referrer` (optional) | string / null | document.referrer |
| `locale` (optional) | string / null | Browser language, e.g. pt-PT |
| `screen` (optional) | string / null | Screen size, e.g. 390x844 |
| `properties` (optional) | object | Event-specific fields, see the table below |

The collector adds `collector_ts` (server clock) and `user_agent`. The warehouse derives
`derived_ts = collector_ts - (sent_at - event_ts)` to correct wrong device clocks.

## Events

| Event | Fired when | Required properties | Funnel step |
|---|---|---|---|
| `page_view` | Every page load (`page_type`: home, rooms, checkout, confirmation, ...) | `page_type` | Visit |
| `search_availability` | Availability results are shown | `adults`, `checkin`, `checkout`, `hotel_code` | Searched availability |
| `select_room` | A room offer is selected (sent immediately - the page navigates away) | `currency`, `hotel_code`, `nightly_rate`, `room_type_code` | Selected a room |
| `begin_checkout` | The checkout page is shown | `currency`, `hotel_code`, `room_type_code`, `value` | Selected a room |
| `add_extras` | An extra (e.g. breakfast) is added | `extras` | - |
| `payment_submitted` | The payment form is submitted (sent immediately) | `currency`, `value` | Attempted payment |
| `payment_failed` | The payment provider declines or fails | `error_code` | Attempted payment |
| `booking_confirmed` | The confirmation page is first shown (not on reload) | `confirmation_code`, `currency`, `hotel_code`, `value` | Booked |

## Identifiers and privacy

- `anonymous_id`: random first-party id in the `hp_aid` cookie, set only after consent.
- `confirmation_code` (on `booking_confirmed`) is the only link to the PMS reservation.
- No IP address, name or e-mail address is collected.
