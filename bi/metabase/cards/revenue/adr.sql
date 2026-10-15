-- Average daily rate: room revenue per room sold
SELECT round(sum(room_revenue) / nullif(sum(rooms_sold), 0), 2) AS adr
FROM marts.hotel_daily_kpi
WHERE
    NOT is_future
    AND {{hotel}}
    AND {{period}}
