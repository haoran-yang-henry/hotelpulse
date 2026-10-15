-- Share of the PMS's website bookings that the tracker saw
SELECT round(sum(tracked_bookings)::numeric / nullif(sum(pms_website_bookings), 0), 4) AS tracking_coverage
FROM marts.tracking_coverage_daily
WHERE {{period}}
