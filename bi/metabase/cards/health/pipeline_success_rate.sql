-- Share of finished pipeline runs that succeeded (the alert drill is excluded)
SELECT round(avg((state = 'success')::int), 4) AS success_rate
FROM audit.dag_runs
WHERE
    {{period}}
    AND state IN ('success', 'failed')
    AND dag_id <> 'ops_alert_drill'
