-- Data-quality checks whose latest result is a warning or a failure
SELECT count(*) AS failing_checks
FROM (
    SELECT DISTINCT ON (check_name) status
    FROM audit.dq_results
    ORDER BY check_name ASC, checked_at DESC
) AS latest
WHERE status <> 'pass'
