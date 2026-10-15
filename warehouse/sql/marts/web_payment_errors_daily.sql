-- Failed payment attempts per day, device and error code.

DELETE FROM marts.web_payment_errors_daily;

INSERT INTO marts.web_payment_errors_daily (session_date, device_type, error_code, failures)
SELECT
    s.session_date,
    s.device_type,
    coalesce(e.error_code, '(unknown)') AS error_code,
    count(*) AS failures
FROM core.fct_web_event AS e
INNER JOIN core.fct_web_session AS s ON e.session_id = s.session_id
WHERE e.event_name = 'payment_failed'
GROUP BY s.session_date, s.device_type, coalesce(e.error_code, '(unknown)');
