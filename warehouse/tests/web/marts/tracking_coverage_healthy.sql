-- severity: warn
-- description: The tracker sees at least 60 % of website bookings (last 14 days).
SELECT
    sum(tracked_bookings) AS tracked,
    sum(pms_website_bookings) AS website_bookings,
    round(sum(tracked_bookings)::numeric / nullif(sum(pms_website_bookings), 0), 3) AS coverage
FROM marts.tracking_coverage_daily
WHERE booked_date >= (now() AT TIME ZONE 'Europe/Lisbon')::date - 16
HAVING sum(tracked_bookings) < 0.6 * sum(pms_website_bookings)
