-- Tracking coverage: which share of the PMS's website bookings did the tracker see?
-- Visitors who reject cookies or block the tracker are invisible to web analytics; this mart
-- quantifies the gap (ADR-0013). The last two days are excluded because the PMS is loaded
-- daily and the web hourly.

DELETE FROM marts.tracking_coverage_daily;

INSERT INTO marts.tracking_coverage_daily (
    booked_date, hotel_name, pms_website_bookings, tracked_bookings, coverage
)
WITH tracking_start AS (
    SELECT min(session_date) AS first_day
    FROM core.fct_web_session
),

website_bookings AS (
    SELECT
        r.booked_date,
        h.hotel_name,
        r.confirmation_code
    FROM core.fct_reservation AS r
    INNER JOIN core.dim_hotel AS h ON r.hotel_id = h.hotel_id
    CROSS JOIN tracking_start AS ts
    WHERE
        r.channel_code = 'website'
        AND r.booked_date >= ts.first_day
        AND r.booked_date < (now() AT TIME ZONE 'Europe/Lisbon')::date - 1
),

tracked AS (
    SELECT DISTINCT confirmation_code
    FROM core.fct_web_session
    WHERE booked
)

SELECT
    w.booked_date,
    w.hotel_name,
    count(*) AS pms_website_bookings,
    count(t.confirmation_code) AS tracked_bookings,
    round(count(t.confirmation_code)::numeric / count(*), 4) AS coverage
FROM website_bookings AS w
LEFT JOIN tracked AS t ON w.confirmation_code = t.confirmation_code
GROUP BY w.booked_date, w.hotel_name;
