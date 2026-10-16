-- Datasets that missed their freshness SLA at the latest check
SELECT count(*) FILTER (WHERE f.status <> 'ok') AS stale_datasets
FROM audit.freshness AS f
WHERE f.checked_at = (SELECT max(latest.checked_at) FROM audit.freshness AS latest)
