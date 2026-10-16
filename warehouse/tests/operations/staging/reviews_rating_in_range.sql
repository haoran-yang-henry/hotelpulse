-- severity: error
-- description: Review ratings are on the 1-10 scale and every review has a known hotel.
SELECT
    r.review_id,
    r.hotel_code,
    r.rating
FROM staging.reviews AS r
LEFT JOIN core.dim_hotel AS h ON r.hotel_code = h.hotel_code
WHERE r.rating NOT BETWEEN 1 AND 10 OR h.hotel_id IS NULL
