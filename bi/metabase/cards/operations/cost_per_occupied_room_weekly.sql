-- Weekly consumables cost per occupied room, per hotel (complete weeks only)
SELECT
    date_trunc('week', usage_date)::date AS week,
    hotel_name,
    round(sum(cost_eur) / nullif(sum(rooms_sold), 0), 2) AS cost_per_occupied_room
FROM (
    SELECT
        usage_date,
        hotel_name,
        sum(cost_eur) AS cost_eur,
        max(rooms_sold) AS rooms_sold
    FROM marts.consumables_daily
    WHERE
        {{hotel}}
        AND {{period}}
        AND usage_date < date_trunc('week', current_date)
    GROUP BY usage_date, hotel_name
) AS daily
GROUP BY week, hotel_name
ORDER BY week, hotel_name
