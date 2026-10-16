-- Platform observability (ADR-0018): alerts, DAG run history and dataset freshness.

CREATE TABLE audit.alerts (
    alert_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    raised_at timestamptz NOT NULL DEFAULT now(),
    severity text NOT NULL CHECK (severity IN ('error', 'warn')),
    source text NOT NULL,
    message text NOT NULL,
    details jsonb,
    dedupe_key text NOT NULL,
    notified boolean NOT NULL DEFAULT FALSE
);

CREATE INDEX alerts_dedupe_idx ON audit.alerts (dedupe_key, raised_at DESC);
CREATE INDEX alerts_raised_at_idx ON audit.alerts (raised_at DESC);

-- DAG runs mirrored from the Airflow REST API by the platform_health watchdog.
CREATE TABLE audit.dag_runs (
    dag_id text NOT NULL,
    run_id text NOT NULL,
    run_type text NOT NULL,
    state text NOT NULL,
    data_interval_start timestamptz,
    data_interval_end timestamptz,
    start_date timestamptz,
    end_date timestamptz,
    duration_s numeric(10, 1),
    synced_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dag_id, run_id)
);

CREATE INDEX dag_runs_start_idx ON audit.dag_runs (start_date DESC);

-- Freshness of each monitored dataset, checked every 15 minutes.
CREATE TABLE audit.freshness (
    checked_at timestamptz NOT NULL,
    dataset text NOT NULL,
    last_update timestamptz,
    age_hours numeric(10, 2),
    sla_hours numeric(10, 2) NOT NULL,
    status text NOT NULL CHECK (status IN ('ok', 'stale', 'empty')),
    PRIMARY KEY (checked_at, dataset)
);

-- Rows loaded per day and dataset: database extractions (load_log) and landing files.
CREATE VIEW audit.loads_daily AS
SELECT
    (loaded_at AT TIME ZONE 'Europe/Lisbon')::date AS loaded_on,
    dataset,
    count(*) AS loads,
    sum(rows_loaded) AS rows_loaded
FROM audit.load_log
GROUP BY 1, 2
UNION ALL
SELECT
    (loaded_at AT TIME ZONE 'Europe/Lisbon')::date AS loaded_on,
    'landing.' || dataset AS dataset,
    count(*) AS loads,
    sum(rows_loaded) AS rows_loaded
FROM audit.loaded_files
GROUP BY 1, 2;
