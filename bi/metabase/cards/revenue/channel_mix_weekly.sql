-- Sold room nights per channel group and week
SELECT
    date_trunc('week', stay_date)::date AS week,
    channel_group,
    sum(rooms_sold) AS room_nights
FROM marts.channel_daily
WHERE
    {{hotel}}
    AND {{period}}
    AND stay_date < date_trunc('week', current_date)
GROUP BY week, channel_group
ORDER BY
    week,
    CASE channel_group
        WHEN 'Direct' THEN 1
        WHEN 'OTA' THEN 2
        WHEN 'Wholesale' THEN 3
        WHEN 'Groups' THEN 4
        WHEN 'Corporate' THEN 5
        ELSE 6
    END
