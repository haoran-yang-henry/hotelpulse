-- Room revenue and commission cost per channel for the selected period
SELECT
    channel_name,
    sum(room_revenue) AS room_revenue,
    sum(commission_cost) AS commission_cost,
    round(sum(commission_cost) / nullif(sum(room_revenue), 0), 4) AS commission_rate
FROM marts.channel_daily
WHERE
    {{hotel}}
    AND {{period}}
    AND stay_date < current_date
GROUP BY 1
HAVING sum(commission_cost) > 0
ORDER BY 3 DESC
