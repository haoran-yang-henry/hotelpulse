-- Suggested order for the next 14 nights, with the change in the usage rate
SELECT
    hotel_name,
    item_name,
    usage_per_driver,
    usage_per_driver_prev,
    round(usage_per_driver / nullif(usage_per_driver_prev, 0) - 1, 3) AS usage_change,
    forecast_driver_units,
    suggested_quantity,
    unit,
    estimated_cost_eur
FROM marts.purchase_suggestion
WHERE {{hotel}}
ORDER BY hotel_name, item_code
