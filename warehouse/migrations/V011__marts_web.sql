-- Booking funnel per day, device, traffic channel and hotel (sessions reaching each step).
CREATE TABLE marts.web_funnel_daily (
    session_date date NOT NULL,
    device_type text NOT NULL,
    channel_group text NOT NULL,
    hotel_code text NOT NULL,
    sessions integer NOT NULL,
    searched integer NOT NULL,
    selected_room integer NOT NULL,
    attempted_payment integer NOT NULL,
    failed_payment integer NOT NULL,
    booked integer NOT NULL,
    booking_value numeric(12, 2) NOT NULL,
    built_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (session_date, device_type, channel_group, hotel_code)
);

-- Failed payments per day, device and error code.
CREATE TABLE marts.web_payment_errors_daily (
    session_date date NOT NULL,
    device_type text NOT NULL,
    error_code text NOT NULL,
    failures integer NOT NULL,
    built_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (session_date, device_type, error_code)
);

-- One row per tracked website booking matched to the PMS, with first- and last-touch channel
-- (visits of the same visitor within 30 days before the booking).
CREATE TABLE marts.web_attribution (
    confirmation_code text PRIMARY KEY,
    reservation_id bigint NOT NULL,
    hotel_name text NOT NULL,
    booked_date date NOT NULL,
    booked_revenue numeric(12, 2) NOT NULL,
    is_canceled boolean NOT NULL,
    first_touch_channel text NOT NULL,
    first_touch_source text NOT NULL,
    last_touch_channel text NOT NULL,
    last_touch_source text NOT NULL,
    sessions_to_convert integer NOT NULL,
    days_to_convert numeric(6, 1) NOT NULL,
    built_at timestamptz NOT NULL DEFAULT now()
);

-- Tracking coverage: share of PMS website bookings that were seen by the tracker.
CREATE TABLE marts.tracking_coverage_daily (
    booked_date date NOT NULL,
    hotel_name text NOT NULL,
    pms_website_bookings integer NOT NULL,
    tracked_bookings integer NOT NULL,
    coverage numeric(6, 4),
    built_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (booked_date, hotel_name)
);
