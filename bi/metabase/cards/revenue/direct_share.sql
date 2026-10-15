-- Share of sold room nights booked through direct channels (website, phone, walk-in)
SELECT round(sum(direct_rooms_sold)::numeric / nullif(sum(rooms_sold), 0), 4) AS direct_share
FROM marts.hotel_daily_kpi
WHERE
    NOT is_future
    AND {{hotel}}
    AND {{period}}
