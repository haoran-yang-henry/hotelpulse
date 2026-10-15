-- Occupancy for the selected period (actuals only)
SELECT round(sum(rooms_sold)::numeric / nullif(sum(rooms_available), 0), 4) AS occupancy
FROM marts.hotel_daily_kpi
WHERE
    NOT is_future
    AND {{hotel}}
    AND {{period}}
