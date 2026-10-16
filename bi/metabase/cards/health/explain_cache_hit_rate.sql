-- Share of explanation requests answered from the cache
SELECT round(avg(cache_hit::int), 4) AS cache_hit_rate
FROM insight.requests
WHERE {{period}}
