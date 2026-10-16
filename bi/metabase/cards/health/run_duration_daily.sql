-- Average run duration per DAG and day (minutes)
SELECT
    (start_date AT TIME ZONE 'Europe/Lisbon')::date AS day,
    dag_id,
    round(avg(duration_s) / 60, 2) AS avg_minutes
FROM audit.dag_runs
WHERE
    {{period}}
    AND state = 'success'
GROUP BY day, dag_id
ORDER BY day, dag_id
