-- Visits and conversion rate per traffic channel
SELECT
    channel_group,
    sum(sessions) AS sessions,
    round(sum(booked)::numeric / nullif(sum(sessions), 0), 4) AS conversion_rate
FROM marts.web_funnel_daily
WHERE
    {{period}}
    AND {{device}}
    AND {{channel}}
GROUP BY channel_group
ORDER BY conversion_rate DESC
