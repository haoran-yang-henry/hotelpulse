-- Operations & guest experience (ADR-0019): consumables usage and guest reviews.
-- Both arrive as daily export files in the landing zone (same exactly-once loader as web).

CREATE TABLE raw.inventory_usage (
    payload jsonb NOT NULL,
    _file text NOT NULL,
    _line integer NOT NULL,
    _batch_id text NOT NULL,
    _loaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX inventory_usage_batch_idx ON raw.inventory_usage (_batch_id);
CREATE INDEX inventory_usage_file_idx ON raw.inventory_usage (_file);

CREATE TABLE raw.reviews (
    payload jsonb NOT NULL,
    _file text NOT NULL,
    _line integer NOT NULL,
    _batch_id text NOT NULL,
    _loaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX reviews_batch_idx ON raw.reviews (_batch_id);
CREATE INDEX reviews_file_idx ON raw.reviews (_file);

-- Consumables master data (procurement): what drives usage and how much buffer to order.
CREATE TABLE core.dim_consumable (
    item_code text PRIMARY KEY,
    item_name text NOT NULL,
    unit text NOT NULL,
    usage_driver text NOT NULL CHECK (usage_driver IN ('room_night', 'breakfast_guest')),
    safety_factor numeric(4, 2) NOT NULL,
    sort_order integer NOT NULL
);

INSERT INTO core.dim_consumable VALUES
('towel_laundry', 'Towels laundered', 'towel', 'room_night', 1.10, 10),
('toiletry_kit', 'Toiletry kits', 'kit', 'room_night', 1.10, 20),
('coffee_capsule', 'Coffee capsules', 'capsule', 'room_night', 1.10, 30),
('water_bottle', 'Water bottles', 'bottle', 'room_night', 1.10, 40),
('breakfast_cover', 'Breakfast covers', 'cover', 'breakfast_guest', 1.05, 50);

-- One row per hotel, day and item; a re-export of a day replaces it (latest file wins).
CREATE TABLE staging.inventory_usage (
    usage_date date NOT NULL,
    hotel_code text NOT NULL,
    item_code text NOT NULL,
    item_name text NOT NULL,
    unit text NOT NULL,
    quantity integer NOT NULL,
    unit_cost_eur numeric(8, 2) NOT NULL,
    _file text NOT NULL,
    _batch_id text NOT NULL,
    _loaded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (usage_date, hotel_code, item_code)
);

-- One row per review; aspect sentiment as delivered by the review-management tool.
CREATE TABLE staging.reviews (
    review_id text PRIMARY KEY,
    platform text NOT NULL,
    hotel_code text NOT NULL,
    confirmation_code text,
    posted_at timestamptz NOT NULL,
    rating numeric(3, 1) NOT NULL,
    title text,
    review_text text,
    topics jsonb NOT NULL,
    _batch_id text NOT NULL,
    _loaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX staging_reviews_batch_idx ON staging.reviews (_batch_id);

-- Consumables per hotel, day and item with the occupancy that drove them.
CREATE TABLE marts.consumables_daily (
    usage_date date NOT NULL,
    hotel_id smallint NOT NULL,
    hotel_name text NOT NULL,
    item_code text NOT NULL,
    item_name text NOT NULL,
    unit text NOT NULL,
    usage_driver text NOT NULL,
    quantity integer NOT NULL,
    unit_cost_eur numeric(8, 2) NOT NULL,
    cost_eur numeric(12, 2) NOT NULL,
    rooms_sold integer NOT NULL,
    breakfast_guests integer NOT NULL,
    driver_units integer NOT NULL,  -- rooms sold or breakfast guests, per usage_driver
    built_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (usage_date, hotel_id, item_code)
);

-- One row per review, linked to the stay it is about (via the confirmation code).
CREATE TABLE marts.guest_reviews (
    review_id text PRIMARY KEY,
    platform text NOT NULL,
    hotel_id smallint NOT NULL,
    hotel_name text NOT NULL,
    posted_date date NOT NULL,
    rating numeric(3, 1) NOT NULL,
    reservation_id bigint,
    arrival_date date,
    departure_date date,
    channel_group text,
    stay_occupancy numeric(6, 4),  -- average occupancy of the hotel during the stay
    occupancy_band text,
    negative_topics integer NOT NULL,
    breakfast_complaint boolean NOT NULL,
    built_at timestamptz NOT NULL DEFAULT now()
);

-- One row per review and mentioned topic.
CREATE TABLE marts.review_topics (
    review_id text NOT NULL,
    hotel_id smallint NOT NULL,
    hotel_name text NOT NULL,
    posted_date date NOT NULL,
    topic text NOT NULL,
    sentiment text NOT NULL,
    occupancy_band text,
    built_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (review_id, topic)
);

-- Suggested order for the next 14 nights per hotel and item (rule-based, ADR-0019).
CREATE TABLE marts.purchase_suggestion (
    hotel_id smallint NOT NULL,
    hotel_name text NOT NULL,
    item_code text NOT NULL,
    item_name text NOT NULL,
    unit text NOT NULL,
    usage_per_driver numeric(8, 3),  -- median of the last 28 days
    usage_per_driver_prev numeric(8, 3),  -- median of the 28 days before
    forecast_driver_units integer NOT NULL,  -- next 14 nights, from rooms on the books
    suggested_quantity integer NOT NULL,
    estimated_cost_eur numeric(12, 2) NOT NULL,
    built_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (hotel_id, item_code)
);
