-- severity: warn
-- description: Booking source is missing in the PMS; mapped to channel "unknown".
SELECT
    reservation_id,
    market_segment,
    distribution_channel
FROM staging.pms_reservations
WHERE 'unknown_channel' = ANY(dq_issues)
