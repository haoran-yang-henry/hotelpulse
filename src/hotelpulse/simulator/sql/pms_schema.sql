-- Simulated PMS (property management system).
-- Schema "public" = what the vendor PMS exposes to the hotel's reporting account.
-- Schema "sim"    = the simulator's full timeline ("future knowledge"); never readable
--                   by the extraction account pms_reader.

CREATE TABLE IF NOT EXISTS public.hotels (
    hotel_id smallint PRIMARY KEY,
    hotel_code text NOT NULL UNIQUE,
    hotel_name text NOT NULL,
    city text NOT NULL,
    country_code char(2) NOT NULL,
    timezone text NOT NULL,
    total_rooms integer NOT NULL,
    pms_live_date date NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.room_types (
    hotel_id smallint NOT NULL REFERENCES public.hotels (hotel_id),
    room_type_code text NOT NULL,
    room_type_name text NOT NULL,
    room_count integer NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (hotel_id, room_type_code)
);

CREATE TABLE IF NOT EXISTS public.guests (
    guest_id bigint PRIMARY KEY,
    first_name text,
    last_name text,
    email text,
    country_code text,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS public.reservations (
    reservation_id bigint PRIMARY KEY,
    confirmation_code text NOT NULL UNIQUE,
    hotel_id smallint NOT NULL REFERENCES public.hotels (hotel_id),
    guest_id bigint NOT NULL REFERENCES public.guests (guest_id),
    booking_source text,
    market_segment text,
    distribution_channel text,
    reserved_room_type text,
    assigned_room_type text,
    arrival_date date NOT NULL,
    departure_date date NOT NULL,
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
    status text NOT NULL,
    created_at timestamptz NOT NULL,
    checked_in_at timestamptz,
    checked_out_at timestamptz,
    canceled_at timestamptz,
    updated_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS reservations_updated_at_idx ON public.reservations (updated_at);

CREATE SCHEMA IF NOT EXISTS sim;
REVOKE ALL ON SCHEMA sim FROM public;

CREATE TABLE IF NOT EXISTS sim.config (
    key text PRIMARY KEY,
    value text NOT NULL
);

CREATE TABLE IF NOT EXISTS sim.guest_plan (
    guest_id bigint PRIMARY KEY,
    first_name text,
    last_name text,
    email text,
    country_code text,
    created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS sim.reservation_plan (
    reservation_id bigint PRIMARY KEY,
    confirmation_code text NOT NULL,
    hotel_id smallint NOT NULL,
    guest_id bigint NOT NULL,
    booking_source text,
    market_segment text,
    distribution_channel text,
    reserved_room_type text,
    assigned_room_type text,
    arrival_date date NOT NULL,
    departure_date date NOT NULL,
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
    created_at timestamptz NOT NULL,
    checked_in_at timestamptz,
    checked_out_at timestamptz,
    canceled_at timestamptz,
    no_show_at timestamptz,
    anomaly_id text
);

-- Bookings made on the demo website get ids from their own range (see website/engine.py).
CREATE SEQUENCE IF NOT EXISTS sim.engine_reservation_id_seq START 9000001;
CREATE SEQUENCE IF NOT EXISTS sim.engine_guest_id_seq START 9000001;

CREATE INDEX IF NOT EXISTS reservation_plan_created_at_idx ON sim.reservation_plan (created_at);
CREATE INDEX IF NOT EXISTS guest_plan_created_at_idx ON sim.guest_plan (created_at);
