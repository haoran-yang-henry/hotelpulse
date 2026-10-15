-- Raw layer: rows exactly as extracted from the PMS, append-only.
-- Every extraction appends a new version, so these tables double as a change log.

CREATE TABLE raw.pms_hotels (
    hotel_id smallint,
    hotel_code text,
    hotel_name text,
    city text,
    country_code text,
    timezone text,
    total_rooms integer,
    pms_live_date date,
    updated_at timestamptz,
    _batch_id text NOT NULL,
    _extracted_at timestamptz NOT NULL
);

CREATE TABLE raw.pms_room_types (
    hotel_id smallint,
    room_type_code text,
    room_type_name text,
    room_count integer,
    updated_at timestamptz,
    _batch_id text NOT NULL,
    _extracted_at timestamptz NOT NULL
);

CREATE TABLE raw.pms_guests (
    guest_id bigint,
    first_name text,
    last_name text,
    email text,
    country_code text,
    created_at timestamptz,
    updated_at timestamptz,
    _batch_id text NOT NULL,
    _extracted_at timestamptz NOT NULL
);

CREATE TABLE raw.pms_reservations (
    reservation_id bigint,
    confirmation_code text,
    hotel_id smallint,
    guest_id bigint,
    booking_source text,
    market_segment text,
    distribution_channel text,
    reserved_room_type text,
    assigned_room_type text,
    arrival_date date,
    departure_date date,
    adults smallint,
    children smallint,
    babies smallint,
    meal_plan text,
    adr numeric(10, 2),
    deposit_type text,
    customer_type text,
    is_repeated_guest boolean,
    previous_cancellations smallint,
    previous_bookings_not_canceled smallint,
    booking_changes smallint,
    days_in_waiting_list smallint,
    agent_id text,
    company_id text,
    parking_spaces smallint,
    special_requests smallint,
    status text,
    created_at timestamptz,
    checked_in_at timestamptz,
    checked_out_at timestamptz,
    canceled_at timestamptz,
    updated_at timestamptz,
    _batch_id text NOT NULL,
    _extracted_at timestamptz NOT NULL
);

CREATE INDEX pms_hotels_batch_idx ON raw.pms_hotels (_batch_id);
CREATE INDEX pms_room_types_batch_idx ON raw.pms_room_types (_batch_id);
CREATE INDEX pms_guests_batch_idx ON raw.pms_guests (_batch_id);
CREATE INDEX pms_reservations_batch_idx ON raw.pms_reservations (_batch_id);
CREATE INDEX pms_reservations_id_idx ON raw.pms_reservations (reservation_id, updated_at);
