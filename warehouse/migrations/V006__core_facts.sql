-- Grain: one row per reservation, current state (SCD1).
CREATE TABLE core.fct_reservation (
    reservation_id bigint PRIMARY KEY,
    confirmation_code text NOT NULL,
    hotel_id smallint NOT NULL REFERENCES core.dim_hotel (hotel_id),
    guest_key text,
    guest_country text,
    channel_code text NOT NULL REFERENCES core.dim_channel (channel_code),
    market_segment text,
    reserved_room_type text,
    assigned_room_type text,
    booked_date date NOT NULL,
    created_at timestamptz NOT NULL,
    arrival_date date NOT NULL,
    departure_date date NOT NULL,
    nights integer NOT NULL,
    lead_time_days integer NOT NULL,
    guests integer NOT NULL,
    meal_plan text NOT NULL,
    adr numeric(10, 2),
    booked_revenue numeric(12, 2) NOT NULL,  -- adr x nights, regardless of status
    deposit_type text,
    customer_type text,
    is_repeated_guest boolean NOT NULL,
    status text NOT NULL,
    is_canceled boolean NOT NULL,
    is_no_show boolean NOT NULL,
    canceled_at timestamptz,
    canceled_date date,
    dq_issues text[] NOT NULL,
    _batch_id text NOT NULL,
    _loaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX fct_reservation_hotel_booked_idx ON core.fct_reservation (hotel_id, booked_date);
CREATE INDEX fct_reservation_batch_idx ON core.fct_reservation (_batch_id);

-- Grain: one row per reservation and night. Canceled and no-show reservations are kept
-- (is_sold = false) together with created_at/canceled_at, so the on-the-books position
-- can be reconstructed for any point in time (booking pace, same time last year).
CREATE TABLE core.fct_room_night (
    reservation_id bigint NOT NULL REFERENCES core.fct_reservation (reservation_id),
    stay_date date NOT NULL REFERENCES core.dim_date (date_day),
    hotel_id smallint NOT NULL REFERENCES core.dim_hotel (hotel_id),
    room_type_code text,
    channel_code text NOT NULL REFERENCES core.dim_channel (channel_code),
    status text NOT NULL,
    is_sold boolean NOT NULL,
    created_at timestamptz NOT NULL,
    canceled_at timestamptz,
    room_revenue numeric(10, 2) NOT NULL,
    commission_cost numeric(10, 2) NOT NULL,
    _batch_id text NOT NULL,
    PRIMARY KEY (reservation_id, stay_date)
);

CREATE INDEX fct_room_night_hotel_stay_idx ON core.fct_room_night (hotel_id, stay_date);
