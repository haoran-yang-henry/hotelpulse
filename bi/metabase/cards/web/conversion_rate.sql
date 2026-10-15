-- Share of tracked visits that ended with a booking
SELECT round(sum(booked)::numeric / nullif(sum(sessions), 0), 4) AS conversion_rate
FROM marts.web_funnel_daily
WHERE
    {{period}}
    AND {{device}}
    AND {{channel}}
