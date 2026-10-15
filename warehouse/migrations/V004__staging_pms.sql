-- Staging: one current, cleaned row per entity. No personal data beyond this point
-- except the salted guest_key.

CREATE TABLE staging.pms_hotels (
    hotel_id smallint PRIMARY KEY,
    hotel_code text NOT NULL,
    hotel_name text NOT NULL,
    city text NOT NULL,
    country_code text NOT NULL,
    timezone text NOT NULL,
    total_rooms integer NOT NULL,
    pms_live_date date NOT NULL,
    updated_at timestamptz NOT NULL,
    _batch_id text NOT NULL,
    _loaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE staging.pms_room_types (
    hotel_id smallint NOT NULL,
    room_type_code text NOT NULL,
    room_type_name text NOT NULL,
    room_count integer NOT NULL,
    updated_at timestamptz NOT NULL,
    _batch_id text NOT NULL,
    _loaded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (hotel_id, room_type_code)
);

CREATE TABLE staging.pms_guests (
    guest_id bigint PRIMARY KEY,
    guest_key text NOT NULL,
    country_code text,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    dq_issues text[] NOT NULL DEFAULT '{}',
    _batch_id text NOT NULL,
    _loaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE staging.pms_reservations (
    reservation_id bigint PRIMARY KEY,
    confirmation_code text NOT NULL,
    hotel_id smallint NOT NULL,
    guest_id bigint NOT NULL,
    channel_code text NOT NULL,
    market_segment text,
    distribution_channel text,
    reserved_room_type text,
    assigned_room_type text,
    arrival_date date NOT NULL,
    departure_date date NOT NULL,
    nights integer NOT NULL,
    booked_date date NOT NULL,
    lead_time_days integer NOT NULL,
    adults integer NOT NULL,
    children integer NOT NULL,
    babies integer NOT NULL,
    meal_plan text NOT NULL,
    adr_source numeric(10, 2),
    adr numeric(10, 2),
    deposit_type text,
    customer_type text,
    is_repeated_guest boolean NOT NULL,
    special_requests integer NOT NULL,
    parking_spaces integer NOT NULL,
    status text NOT NULL,
    created_at timestamptz NOT NULL,
    checked_in_at timestamptz,
    checked_out_at timestamptz,
    canceled_at timestamptz,
    updated_at timestamptz NOT NULL,
    dq_issues text[] NOT NULL DEFAULT '{}',
    _batch_id text NOT NULL,
    _loaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX pms_reservations_batch_idx ON staging.pms_reservations (_batch_id);
