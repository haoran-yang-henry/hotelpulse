-- Daily KPIs per hotel, on stay-date basis. Past dates are actuals, future dates are
-- on-the-books (OTB). ly_* columns hold the same weekday one year earlier (-364 days).
CREATE TABLE marts.hotel_daily_kpi (
    hotel_id smallint NOT NULL,
    hotel_name text NOT NULL,
    stay_date date NOT NULL,
    is_future boolean NOT NULL,
    rooms_available integer NOT NULL,
    rooms_sold integer NOT NULL,
    direct_rooms_sold integer NOT NULL,
    room_revenue numeric(12, 2) NOT NULL,
    commission_cost numeric(12, 2) NOT NULL,
    net_room_revenue numeric(12, 2) NOT NULL,
    occupancy numeric(6, 4) NOT NULL,
    adr numeric(10, 2),
    revpar numeric(10, 2) NOT NULL,
    direct_share numeric(6, 4),
    arrivals integer NOT NULL,
    departures integer NOT NULL,
    ly_rooms_sold integer,
    ly_room_revenue numeric(12, 2),
    ly_occupancy numeric(6, 4),
    ly_adr numeric(10, 2),
    ly_revpar numeric(10, 2),
    built_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (hotel_id, stay_date)
);

-- Room nights and revenue per hotel, stay date and channel.
CREATE TABLE marts.channel_daily (
    hotel_id smallint NOT NULL,
    hotel_name text NOT NULL,
    stay_date date NOT NULL,
    channel_code text NOT NULL,
    channel_name text NOT NULL,
    channel_group text NOT NULL,
    is_direct boolean NOT NULL,
    rooms_sold integer NOT NULL,
    room_revenue numeric(12, 2) NOT NULL,
    commission_cost numeric(12, 2) NOT NULL,
    built_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (hotel_id, stay_date, channel_code)
);

-- Booking intake per hotel, booking date and channel (when the booking was made).
CREATE TABLE marts.channel_bookings_daily (
    hotel_id smallint NOT NULL,
    hotel_name text NOT NULL,
    booked_date date NOT NULL,
    channel_code text NOT NULL,
    channel_name text NOT NULL,
    channel_group text NOT NULL,
    is_direct boolean NOT NULL,
    bookings integer NOT NULL,
    room_nights integer NOT NULL,
    booked_revenue numeric(12, 2) NOT NULL,
    canceled_bookings integer NOT NULL,
    avg_lead_time_days numeric(8, 1),
    built_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (hotel_id, booked_date, channel_code)
);

-- Booking pace: on-the-books for the next 120 nights vs. same time last year.
CREATE TABLE marts.booking_pace (
    snapshot_date date NOT NULL,
    hotel_id smallint NOT NULL,
    hotel_name text NOT NULL,
    stay_date date NOT NULL,
    days_out integer NOT NULL,
    rooms_available integer NOT NULL,
    otb_rooms integer NOT NULL,
    otb_revenue numeric(12, 2) NOT NULL,
    otb_rooms_7d_ago integer NOT NULL,
    pickup_7d integer NOT NULL,
    stly_otb_rooms integer NOT NULL,
    stly_otb_revenue numeric(12, 2) NOT NULL,
    ly_final_rooms integer NOT NULL,
    built_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (snapshot_date, hotel_id, stay_date)
);
