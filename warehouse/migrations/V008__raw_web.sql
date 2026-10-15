-- Landing-zone files loaded so far (exactly-once file ingestion, ADR-0011).
CREATE TABLE audit.loaded_files (
    file_key text PRIMARY KEY,  -- path relative to the landing root
    dataset text NOT NULL,
    file_bytes bigint NOT NULL,
    rows_loaded integer NOT NULL,
    batch_id text NOT NULL,
    loaded_at timestamptz NOT NULL DEFAULT now()
);

-- Raw tracking events and dead letters exactly as the collector wrote them.
CREATE TABLE raw.web_events (
    payload jsonb NOT NULL,
    _file text NOT NULL,
    _line integer NOT NULL,
    _batch_id text NOT NULL,
    _loaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX web_events_batch_idx ON raw.web_events (_batch_id);
CREATE INDEX web_events_file_idx ON raw.web_events (_file);

CREATE TABLE raw.web_events_rejected (
    payload jsonb NOT NULL,
    _file text NOT NULL,
    _line integer NOT NULL,
    _batch_id text NOT NULL,
    _loaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX web_events_rejected_file_idx ON raw.web_events_rejected (_file);
