-- Alerts raised in the last 24 hours
SELECT count(*) AS open_alerts
FROM audit.alerts
WHERE raised_at > now() - interval '24 hours'
