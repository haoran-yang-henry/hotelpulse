-- Most recent alerts
SELECT
    raised_at,
    severity,
    source,
    message,
    notified
FROM audit.alerts
ORDER BY raised_at DESC
LIMIT 50
