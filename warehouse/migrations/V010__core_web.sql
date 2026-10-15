-- Sessionized events of human visitors (bots excluded).
CREATE TABLE core.fct_web_event (
    event_id uuid PRIMARY KEY,
    session_id uuid NOT NULL,
    anonymous_id uuid NOT NULL,
    event_seq integer NOT NULL,
    event_name text NOT NULL,
    event_ts timestamptz NOT NULL,  -- derived (clock-corrected) timestamp
    page_path text,
    page_type text,
    hotel_code text,
    confirmation_code text,
    value numeric(12, 2),
    error_code text,
    _batch_id text NOT NULL
);

CREATE INDEX fct_web_event_visitor_idx ON core.fct_web_event (anonymous_id);
CREATE INDEX fct_web_event_session_idx ON core.fct_web_event (session_id);

-- Grain: one visit. A new session starts after 30 minutes of inactivity (GA4 definition).
CREATE TABLE core.fct_web_session (
    session_id uuid PRIMARY KEY,
    anonymous_id uuid NOT NULL,
    visitor_session_number integer NOT NULL,
    session_start timestamptz NOT NULL,
    session_end timestamptz NOT NULL,
    session_date date NOT NULL,  -- Europe/Lisbon
    duration_s integer NOT NULL,
    events integer NOT NULL,
    page_views integer NOT NULL,
    landing_path text,
    source text NOT NULL,
    medium text NOT NULL,
    campaign text,
    channel_group text NOT NULL,
    device_type text NOT NULL,
    locale text,
    hotel_code text,
    reached_search boolean NOT NULL,
    reached_room_selection boolean NOT NULL,
    reached_payment boolean NOT NULL,
    payment_failed boolean NOT NULL,
    booked boolean NOT NULL,
    confirmation_code text,
    booking_value numeric(12, 2),
    _batch_id text NOT NULL
);

CREATE INDEX fct_web_session_visitor_idx ON core.fct_web_session (anonymous_id, session_start);
CREATE INDEX fct_web_session_date_idx ON core.fct_web_session (session_date);
CREATE INDEX fct_web_session_code_idx ON core.fct_web_session (confirmation_code)
WHERE confirmation_code IS NOT NULL;
