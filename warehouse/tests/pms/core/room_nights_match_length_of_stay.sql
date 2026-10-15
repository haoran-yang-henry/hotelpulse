-- severity: error
-- description: Each reservation has exactly one room night per night of stay.
SELECT
    f.reservation_id,
    f.nights,
    coalesce(rn.room_nights, 0) AS room_nights
FROM core.fct_reservation AS f
LEFT JOIN (
    SELECT
        reservation_id,
        count(*) AS room_nights
    FROM core.fct_room_night
    GROUP BY reservation_id
) AS rn ON f.reservation_id = rn.reservation_id
WHERE f.nights <> coalesce(rn.room_nights, 0)
