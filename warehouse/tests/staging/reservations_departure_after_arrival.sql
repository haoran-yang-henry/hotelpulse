-- severity: error
-- description: Departure date must not be before arrival date.
SELECT
    reservation_id,
    arrival_date,
    departure_date
FROM staging.pms_reservations
WHERE departure_date < arrival_date
