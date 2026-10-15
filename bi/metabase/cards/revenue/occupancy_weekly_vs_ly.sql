-- Weekly occupancy against the same weeks last year (weekday-aligned, -364 days)
SELECT
    date_trunc('week', stay_date)::date AS week,
    round(sum(rooms_sold)::numeric / sum(rooms_available), 4) AS occupancy,
    round(
        sum(ly_rooms_sold)::numeric
        / nullif(sum(rooms_available) FILTER (WHERE ly_rooms_sold IS NOT NULL), 0),
        4
    ) AS occupancy_last_year
FROM marts.hotel_daily_kpi
WHERE
    stay_date < date_trunc('week', current_date)
    AND {{hotel}}
    AND {{period}}
GROUP BY 1
ORDER BY 1
