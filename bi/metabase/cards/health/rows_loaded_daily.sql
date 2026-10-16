-- Rows loaded per day and dataset (database extractions and landing files)
SELECT
    loaded_on,
    dataset,
    sum(rows_loaded) AS rows_loaded
FROM audit.loads_daily
WHERE {{period}}
GROUP BY loaded_on, dataset
ORDER BY loaded_on, dataset
