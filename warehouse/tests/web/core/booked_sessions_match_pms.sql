-- severity: warn
-- description: Tracked confirmations older than two days exist as reservations in the PMS.
SELECT
    s.confirmation_code,
    s.session_start
FROM core.fct_web_session AS s
LEFT JOIN core.fct_reservation AS r ON s.confirmation_code = r.confirmation_code
WHERE
    s.booked
    AND s.session_start < now() - interval '2 days'
    AND r.reservation_id IS NULL
