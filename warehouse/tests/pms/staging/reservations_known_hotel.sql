-- severity: error
-- description: Every reservation references a known hotel.
SELECT
    r.reservation_id,
    r.hotel_id
FROM staging.pms_reservations AS r
LEFT JOIN staging.pms_hotels AS h ON r.hotel_id = h.hotel_id
WHERE h.hotel_id IS NULL
