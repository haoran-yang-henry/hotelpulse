-- One row per unique event (first delivery wins), typed, with corrected timestamps.
CREATE TABLE staging.web_events (
    event_id uuid PRIMARY KEY,
    event_name text NOT NULL,
    anonymous_id uuid NOT NULL,
    session_hint text,
    event_ts_device timestamptz NOT NULL,
    sent_at_device timestamptz NOT NULL,
    collector_ts timestamptz NOT NULL,
    derived_ts timestamptz NOT NULL,  -- collector_ts - (sent_at - event_ts): device clock corrected
    clock_skew_s integer NOT NULL,
    page_url text NOT NULL,
    page_path text,
    page_type text,
    referrer text,
    referrer_host text,
    utm_source text,
    utm_medium text,
    utm_campaign text,
    locale text,
    user_agent text,
    device_type text NOT NULL,
    is_bot boolean NOT NULL,
    hotel_code text,
    confirmation_code text,
    value numeric(12, 2),
    error_code text,
    properties jsonb NOT NULL,
    _batch_id text NOT NULL,
    _loaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX web_events_batch_idx ON staging.web_events (_batch_id);
CREATE INDEX web_events_visitor_idx ON staging.web_events (anonymous_id, derived_ts);
