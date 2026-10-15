-- Weekly ADR and RevPAR
SELECT
    date_trunc('week', stay_date)::date AS week,
    round(sum(room_revenue) / nullif(sum(rooms_sold), 0), 2) AS adr,
    round(sum(room_revenue) / sum(rooms_available), 2) AS revpar,
    round(sum(ly_room_revenue) / nullif(sum(ly_rooms_sold), 0), 2) AS adr_last_year
FROM marts.hotel_daily_kpi
WHERE
    stay_date < date_trunc('week', current_date)
    AND {{hotel}}
    AND {{period}}
GROUP BY 1
ORDER BY 1
