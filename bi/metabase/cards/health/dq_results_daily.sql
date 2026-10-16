-- Data-quality check results per day and outcome
SELECT
    (checked_at AT TIME ZONE 'Europe/Lisbon')::date AS day,
    status,
    count(*) AS checks
FROM audit.dq_results
WHERE {{period}}
GROUP BY day, status
ORDER BY day, status
