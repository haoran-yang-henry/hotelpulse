-- Failed payment attempts per week and error code
SELECT
    date_trunc('week', session_date)::date AS week,
    error_code,
    sum(failures) AS failures
FROM marts.web_payment_errors_daily
WHERE
    {{period}}
    AND {{device}}
    AND session_date < date_trunc('week', current_date)
GROUP BY week, error_code
ORDER BY week, error_code
