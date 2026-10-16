-- "Explain this chart" service: explanation cache, request log and feedback (ADR-0016/17).
CREATE SCHEMA IF NOT EXISTS insight;

CREATE TABLE insight.explanations (
    explanation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cache_key text NOT NULL UNIQUE,
    dashboard_id integer NOT NULL,
    card_id integer NOT NULL,
    card_name text NOT NULL,
    parameters jsonb NOT NULL,
    data_hash text NOT NULL,
    lang text NOT NULL,
    mode text NOT NULL CHECK (mode IN ('llm', 'template')),
    model text,
    prompt_version text NOT NULL,
    verified boolean NOT NULL,
    unverified_numbers text[] NOT NULL DEFAULT '{}',
    attempts integer NOT NULL,
    prompt_tokens integer NOT NULL,
    completion_tokens integer NOT NULL,
    latency_ms integer NOT NULL,
    error text,
    response jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE insight.requests (
    request_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    explanation_id bigint NOT NULL REFERENCES insight.explanations (explanation_id),
    cache_hit boolean NOT NULL,
    requested_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE insight.feedback (
    feedback_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    explanation_id bigint NOT NULL REFERENCES insight.explanations (explanation_id),
    helpful boolean NOT NULL,
    comment text,
    created_at timestamptz NOT NULL DEFAULT now()
);

GRANT USAGE ON SCHEMA insight TO bi_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA insight TO bi_reader;

-- The service role is created by the Postgres init script; skip the grants on older volumes.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'insight_app') THEN
        GRANT USAGE ON SCHEMA insight TO insight_app;
        GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA insight TO insight_app;
        GRANT USAGE ON ALL SEQUENCES IN SCHEMA insight TO insight_app;
    END IF;
END
$$;
