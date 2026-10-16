-- Explanation requests per day, served from cache or generated
SELECT
    (requested_at AT TIME ZONE 'Europe/Lisbon')::date AS day,
    CASE WHEN cache_hit THEN 'from cache' ELSE 'generated' END AS source,
    count(*) AS requests
FROM insight.requests
WHERE {{period}}
GROUP BY day, source
ORDER BY day, source
