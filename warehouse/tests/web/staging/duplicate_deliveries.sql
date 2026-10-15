-- severity: warn
-- description: Re-delivered events (same event_id) stay below 2 % of raw rows (last 7 days).
SELECT
    count(*) AS raw_rows,
    count(DISTINCT payload ->> 'event_id') AS unique_events
FROM raw.web_events
WHERE _loaded_at >= now() - interval '7 days'
HAVING count(*) - count(DISTINCT payload ->> 'event_id') > 0.02 * count(*)
