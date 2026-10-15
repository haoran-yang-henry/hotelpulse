-- severity: error
-- description: Clock-corrected event time is never after the collector received the event.
SELECT
    event_id,
    derived_ts,
    collector_ts
FROM staging.web_events
WHERE derived_ts > collector_ts + interval '1 minute'
