-- First- vs. last-touch attribution of tracked website bookings. Touches are the visitor's
-- sessions within 30 days before the booking; revenue comes from the PMS, not the tracker.

DELETE FROM marts.web_attribution;

INSERT INTO marts.web_attribution (
    confirmation_code, reservation_id, hotel_name, booked_date, booked_revenue, is_canceled,
    first_touch_channel, first_touch_source, last_touch_channel, last_touch_source,
    sessions_to_convert, days_to_convert
)
WITH bookings AS (
    SELECT DISTINCT ON (s.confirmation_code)
        s.confirmation_code,
        s.anonymous_id,
        s.session_start AS booked_at,
        r.reservation_id,
        h.hotel_name,
        r.booked_date,
        r.booked_revenue,
        r.is_canceled
    FROM core.fct_web_session AS s
    INNER JOIN core.fct_reservation AS r ON s.confirmation_code = r.confirmation_code
    INNER JOIN core.dim_hotel AS h ON r.hotel_id = h.hotel_id
    WHERE s.booked
    ORDER BY s.confirmation_code ASC, s.session_start ASC
),

touches AS (
    SELECT
        b.confirmation_code,
        t.channel_group,
        t.source,
        t.session_start,
        row_number() OVER (PARTITION BY b.confirmation_code ORDER BY t.session_start ASC) AS from_first,
        row_number() OVER (PARTITION BY b.confirmation_code ORDER BY t.session_start DESC) AS from_last
    FROM bookings AS b
    INNER JOIN core.fct_web_session AS t
        ON
            b.anonymous_id = t.anonymous_id
            AND b.booked_at >= t.session_start
            AND t.session_start >= b.booked_at - interval '30 days'
)

SELECT
    b.confirmation_code,
    b.reservation_id,
    b.hotel_name,
    b.booked_date,
    b.booked_revenue,
    b.is_canceled,
    max(t.channel_group) FILTER (WHERE t.from_first = 1) AS first_touch_channel,
    max(t.source) FILTER (WHERE t.from_first = 1) AS first_touch_source,
    max(t.channel_group) FILTER (WHERE t.from_last = 1) AS last_touch_channel,
    max(t.source) FILTER (WHERE t.from_last = 1) AS last_touch_source,
    count(*) AS sessions_to_convert,
    round(extract(EPOCH FROM b.booked_at - min(t.session_start)) / 86400, 1) AS days_to_convert
FROM bookings AS b
INNER JOIN touches AS t ON b.confirmation_code = t.confirmation_code
GROUP BY
    b.confirmation_code, b.reservation_id, b.hotel_name, b.booked_date, b.booked_revenue,
    b.is_canceled, b.booked_at;
