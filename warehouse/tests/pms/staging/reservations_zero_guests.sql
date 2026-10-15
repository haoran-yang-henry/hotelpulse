-- severity: warn
-- description: Reservation has no adults, children or babies.
SELECT
    reservation_id,
    adults,
    children,
    babies,
    status
FROM staging.pms_reservations
WHERE 'zero_guests' = ANY(dq_issues)
