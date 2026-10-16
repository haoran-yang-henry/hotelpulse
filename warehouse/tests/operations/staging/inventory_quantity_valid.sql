-- severity: error
-- description: Consumption quantities are non-negative and unit costs positive.
SELECT
    usage_date,
    hotel_code,
    item_code,
    quantity,
    unit_cost_eur
FROM staging.inventory_usage
WHERE quantity < 0 OR unit_cost_eur <= 0
