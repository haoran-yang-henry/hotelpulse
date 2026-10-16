-- Latest result of every data-quality check, problems first
SELECT
    layer AS suite,
    check_name,
    severity,
    status,
    failing_rows,
    description,
    checked_at
FROM (
    SELECT DISTINCT ON (check_name) *
    FROM audit.dq_results
    ORDER BY check_name ASC, checked_at DESC
) AS latest
ORDER BY
    CASE status WHEN 'fail' THEN 1 WHEN 'warn' THEN 2 ELSE 3 END,
    check_name
