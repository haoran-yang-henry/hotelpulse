-- severity: error
-- description: Reservation status is one of the PMS lifecycle states.
SELECT
    reservation_id,
    status
FROM staging.pms_reservations
WHERE status NOT IN ('confirmed', 'checked_in', 'checked_out', 'canceled', 'no_show')
