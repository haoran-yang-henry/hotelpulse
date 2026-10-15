-- Tracked visits (humans only; visitors who rejected cookies are not included)
SELECT sum(sessions) AS sessions
FROM marts.web_funnel_daily
WHERE
    {{period}}
    AND {{device}}
    AND {{channel}}
