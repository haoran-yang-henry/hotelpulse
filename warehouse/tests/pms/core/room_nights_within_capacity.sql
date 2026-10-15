-- severity: error
-- description: Rooms sold per hotel and night never exceed the hotel's room count.
SELECT
    rn.hotel_id,
    rn.stay_date,
    count(*) AS rooms_sold,
    max(h.total_rooms) AS total_rooms
FROM core.fct_room_night AS rn
INNER JOIN core.dim_hotel AS h ON rn.hotel_id = h.hotel_id
WHERE rn.is_sold
GROUP BY rn.hotel_id, rn.stay_date
HAVING count(*) > max(h.total_rooms)
