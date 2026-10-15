-- severity: warn
-- description: Actuals reach at least the day before yesterday (data is fresh).
SELECT
    hotel_id,
    max(stay_date) AS latest_actual_day
FROM marts.hotel_daily_kpi
WHERE NOT is_future AND rooms_sold > 0
GROUP BY hotel_id
HAVING max(stay_date) < (now() AT TIME ZONE 'Europe/Lisbon')::date - 2
