CREATE TABLE core.dim_date (
    date_day date PRIMARY KEY,
    year integer NOT NULL,
    quarter integer NOT NULL,
    month integer NOT NULL,
    month_name text NOT NULL,
    month_start date NOT NULL,
    iso_year integer NOT NULL,
    iso_week integer NOT NULL,
    week_start date NOT NULL,
    day_of_week integer NOT NULL,  -- ISO: 1 = Monday
    day_name text NOT NULL,
    is_weekend boolean NOT NULL
);

INSERT INTO core.dim_date
SELECT
    d::date AS date_day,
    extract(YEAR FROM d)::int AS year,
    extract(QUARTER FROM d)::int AS quarter,
    extract(MONTH FROM d)::int AS month,
    trim(to_char(d, 'Month')) AS month_name,
    date_trunc('month', d)::date AS month_start,
    extract(ISOYEAR FROM d)::int AS iso_year,
    extract(WEEK FROM d)::int AS iso_week,
    date_trunc('week', d)::date AS week_start,
    extract(ISODOW FROM d)::int AS day_of_week,
    trim(to_char(d, 'Day')) AS day_name,
    extract(ISODOW FROM d) IN (6, 7) AS is_weekend
FROM generate_series(date '2023-01-01', date '2028-12-31', interval '1 day') AS d;

CREATE TABLE core.dim_hotel (
    hotel_id smallint PRIMARY KEY,
    hotel_code text NOT NULL UNIQUE,
    hotel_name text NOT NULL,
    city text NOT NULL,
    country_code text NOT NULL,
    timezone text NOT NULL,
    total_rooms integer NOT NULL,
    pms_live_date date NOT NULL,  -- reporting starts here; earlier data is incomplete
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE core.dim_room_type (
    hotel_id smallint NOT NULL REFERENCES core.dim_hotel (hotel_id),
    room_type_code text NOT NULL,
    room_type_name text NOT NULL,
    room_count integer NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (hotel_id, room_type_code)
);

-- Distribution channels with commission rates (share of room revenue).
CREATE TABLE core.dim_channel (
    channel_code text PRIMARY KEY,
    channel_name text NOT NULL,
    channel_group text NOT NULL,
    is_direct boolean NOT NULL,
    commission_rate numeric(5, 4) NOT NULL,
    sort_order integer NOT NULL
);

INSERT INTO core.dim_channel VALUES
('website', 'Hotel website', 'Direct', TRUE, 0.0300, 10),
('phone', 'Phone & e-mail', 'Direct', TRUE, 0.0000, 11),
('walk_in', 'Walk-in', 'Direct', TRUE, 0.0000, 12),
('booking_com', 'Booking.com', 'OTA', FALSE, 0.1700, 20),
('expedia', 'Expedia', 'OTA', FALSE, 0.1800, 21),
('other_ota', 'Other OTAs', 'OTA', FALSE, 0.1500, 22),
('travel_agent', 'Travel agents & tour operators', 'Wholesale', FALSE, 0.1000, 30),
('gds', 'GDS', 'Wholesale', FALSE, 0.1000, 31),
('group', 'Groups', 'Groups', FALSE, 0.0800, 40),
('corporate', 'Corporate', 'Corporate', FALSE, 0.0000, 50),
('aviation', 'Airline crew', 'Corporate', FALSE, 0.0000, 51),
('complimentary', 'Complimentary', 'Other', FALSE, 0.0000, 60),
('unknown', 'Unknown', 'Other', FALSE, 0.0000, 99);
