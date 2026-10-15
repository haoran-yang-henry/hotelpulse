-- severity: warn
-- description: Events from devices whose clock is off by more than 1 hour stay below 5 %.
SELECT
    count(*) FILTER (WHERE abs(clock_skew_s) > 3600) AS skewed_events,
    count(*) AS all_events
FROM staging.web_events
WHERE collector_ts >= now() - interval '7 days'
HAVING count(*) FILTER (WHERE abs(clock_skew_s) > 3600) > 0.05 * count(*)
