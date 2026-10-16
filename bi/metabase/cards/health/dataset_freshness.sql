-- Latest freshness check per dataset
SELECT
    f.dataset,
    f.status,
    f.age_hours,
    f.sla_hours,
    f.last_update
FROM audit.freshness AS f
WHERE f.checked_at = (SELECT max(latest.checked_at) FROM audit.freshness AS latest)
ORDER BY f.status DESC, f.dataset ASC
