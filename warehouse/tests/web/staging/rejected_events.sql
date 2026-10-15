-- severity: warn
-- description: Events rejected by the collector stay below 1 % (files loaded in the last 7 days).
WITH recent AS (
    SELECT
        (
            SELECT count(*) FROM raw.web_events
            WHERE _loaded_at >= now() - interval '7 days'
        ) AS accepted,
        (
            SELECT count(*) FROM raw.web_events_rejected
            WHERE _loaded_at >= now() - interval '7 days'
        ) AS rejected
)

SELECT
    accepted,
    rejected
FROM recent
WHERE rejected > 0.01 * (accepted + rejected)
