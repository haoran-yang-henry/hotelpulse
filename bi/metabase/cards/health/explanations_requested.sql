-- "Explain this chart" requests
SELECT count(*) AS requests
FROM insight.requests
WHERE {{period}}
