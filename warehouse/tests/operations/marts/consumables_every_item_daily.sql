-- severity: warn
-- description: Each hotel reported every consumable on each of the last 7 complete days.
SELECT
    h.hotel_name,
    d.date_day,
    count(c.item_code) AS items_reported
FROM core.dim_hotel AS h
CROSS JOIN core.dim_date AS d
LEFT JOIN marts.consumables_daily AS c ON h.hotel_id = c.hotel_id AND d.date_day = c.usage_date
WHERE d.date_day BETWEEN (now() AT TIME ZONE 'Europe/Lisbon')::date - 8
    AND (now() AT TIME ZONE 'Europe/Lisbon')::date - 2
GROUP BY h.hotel_name, d.date_day
HAVING count(c.item_code) < (SELECT count(*) FROM core.dim_consumable)
