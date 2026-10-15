-- severity: warn
-- description: Bot traffic stays below 15 % of events collected in the last 7 days.
SELECT
    count(*) FILTER (WHERE is_bot) AS bot_events,
    count(*) AS all_events
FROM staging.web_events
WHERE collector_ts >= now() - interval '7 days'
HAVING count(*) FILTER (WHERE is_bot) > 0.15 * count(*)
