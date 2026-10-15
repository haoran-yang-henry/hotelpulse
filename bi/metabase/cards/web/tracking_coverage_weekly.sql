-- Weekly share of PMS website bookings seen by the tracker
SELECT
    date_trunc('week', booked_date)::date AS week,
    round(sum(tracked_bookings)::numeric / nullif(sum(pms_website_bookings), 0), 4) AS tracking_coverage
FROM marts.tracking_coverage_daily
WHERE
    {{period}}
    AND booked_date < date_trunc('week', current_date)
GROUP BY week
ORDER BY week
