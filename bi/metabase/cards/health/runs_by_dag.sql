-- Pipeline runs per DAG and outcome
SELECT
    dag_id,
    state,
    count(*) AS runs
FROM audit.dag_runs
WHERE {{period}}
GROUP BY dag_id, state
ORDER BY dag_id, state
