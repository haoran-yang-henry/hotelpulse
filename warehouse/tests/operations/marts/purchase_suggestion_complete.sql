-- severity: error
-- description: There is a purchase suggestion for every hotel and consumable.
SELECT
    h.hotel_name,
    c.item_code
FROM core.dim_hotel AS h
CROSS JOIN core.dim_consumable AS c
LEFT JOIN marts.purchase_suggestion AS s ON h.hotel_id = s.hotel_id AND c.item_code = s.item_code
WHERE s.item_code IS NULL
