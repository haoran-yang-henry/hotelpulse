-- Tracked visits per week and traffic channel
SELECT
    date_trunc('week', session_date)::date AS week,
    channel_group,
    sum(sessions) AS sessions
FROM marts.web_funnel_daily
WHERE
    {{period}}
    AND {{device}}
    AND {{channel}}
    AND session_date < date_trunc('week', current_date)
GROUP BY week, channel_group
ORDER BY week, channel_group
