-- Weekly usage per driver unit and item: per room night, breakfast covers per breakfast guest
SELECT
    date_trunc('week', usage_date)::date AS week,
    item_name,
    round(sum(quantity)::numeric / nullif(sum(driver_units), 0), 3) AS usage_per_room_night
FROM marts.consumables_daily
WHERE
    {{hotel}}
    AND {{period}}
    AND usage_date < date_trunc('week', current_date)
GROUP BY week, item_name
ORDER BY week, item_name
