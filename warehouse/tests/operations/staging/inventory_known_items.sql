-- severity: error
-- description: Every consumables row has a known hotel and an item in the consumables master.
SELECT
    u.usage_date,
    u.hotel_code,
    u.item_code
FROM staging.inventory_usage AS u
LEFT JOIN core.dim_hotel AS h ON u.hotel_code = h.hotel_code
LEFT JOIN core.dim_consumable AS c ON u.item_code = c.item_code
WHERE h.hotel_id IS NULL OR c.item_code IS NULL
