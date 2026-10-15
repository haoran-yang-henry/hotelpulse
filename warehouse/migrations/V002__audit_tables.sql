CREATE TABLE audit.load_log (
    load_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id text NOT NULL,
    dataset text NOT NULL,
    mode text NOT NULL CHECK (mode IN ('incremental', 'full')),
    window_start timestamptz,
    window_end timestamptz NOT NULL,
    rows_loaded integer NOT NULL,
    loaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX load_log_dataset_loaded_at_idx ON audit.load_log (dataset, loaded_at DESC);

CREATE TABLE audit.dq_results (
    result_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id text NOT NULL,
    check_name text NOT NULL,
    layer text NOT NULL,
    severity text NOT NULL CHECK (severity IN ('error', 'warn')),
    status text NOT NULL CHECK (status IN ('pass', 'fail', 'warn')),
    failing_rows integer NOT NULL,
    description text,
    sample jsonb,
    checked_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX dq_results_checked_at_idx ON audit.dq_results (checked_at DESC);
