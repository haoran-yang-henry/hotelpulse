-- Consumables cost per occupied room (CPOR) for the selected period
SELECT round(sum(cost_eur) / nullif(sum(rooms_sold), 0), 2) AS cost_per_occupied_room
FROM (
    SELECT
        usage_date,
        hotel_id,
        sum(cost_eur) AS cost_eur,
        max(rooms_sold) AS rooms_sold
    FROM marts.consumables_daily
    WHERE {{hotel}} AND {{period}}
    GROUP BY usage_date, hotel_id
) AS daily
