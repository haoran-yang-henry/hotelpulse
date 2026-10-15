-- Revenue per available room
SELECT round(sum(room_revenue) / nullif(sum(rooms_available), 0), 2) AS revpar
FROM marts.hotel_daily_kpi
WHERE
    NOT is_future
    AND {{hotel}}
    AND {{period}}
