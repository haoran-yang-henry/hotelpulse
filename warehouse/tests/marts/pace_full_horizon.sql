-- severity: warn
-- description: The pace report covers the full 120-night horizon for every hotel.
SELECT
    h.hotel_id,
    count(p.stay_date) AS nights_covered
FROM core.dim_hotel AS h
LEFT JOIN marts.booking_pace AS p ON h.hotel_id = p.hotel_id
GROUP BY h.hotel_id
HAVING count(p.stay_date) < 120
