-- Booking pace for the next 120 nights: rooms on the books (OTB) now, 7 days ago, and at the
-- same time last year (STLY, -364 days so weekdays line up), plus last year's final result.
-- A room night counts as "on the books at time T" if it was created before T and not yet
-- canceled at T - which is why fct_room_night keeps canceled reservations.

DELETE FROM marts.booking_pace;

INSERT INTO marts.booking_pace (
    snapshot_date, hotel_id, hotel_name, stay_date, days_out, rooms_available, otb_rooms,
    otb_revenue, otb_rooms_7d_ago, pickup_7d, stly_otb_rooms, stly_otb_revenue, ly_final_rooms
)
WITH snapshot AS (
    SELECT
        now() AS snapshot_ts,
        (now() AT TIME ZONE 'Europe/Lisbon')::date AS snapshot_date
),

horizon AS (
    SELECT
        h.hotel_id,
        h.hotel_name,
        h.total_rooms,
        s.snapshot_ts,
        s.snapshot_date,
        d.date_day AS stay_date
    FROM core.dim_hotel AS h
    CROSS JOIN snapshot AS s
    INNER JOIN core.dim_date AS d ON d.date_day BETWEEN s.snapshot_date AND s.snapshot_date + 119
),

pace AS (
    SELECT
        hz.hotel_id,
        hz.stay_date,
        -- now
        count(*) FILTER (
            WHERE rn.stay_date = hz.stay_date
            AND rn.created_at <= hz.snapshot_ts
            AND (rn.canceled_at IS NULL OR rn.canceled_at > hz.snapshot_ts)
            AND rn.status <> 'no_show'
        ) AS otb_rooms,
        coalesce(sum(rn.room_revenue) FILTER (
            WHERE rn.stay_date = hz.stay_date
            AND rn.created_at <= hz.snapshot_ts
            AND (rn.canceled_at IS NULL OR rn.canceled_at > hz.snapshot_ts)
            AND rn.status <> 'no_show'
        ), 0) AS otb_revenue,
        -- 7 days ago
        count(*) FILTER (
            WHERE rn.stay_date = hz.stay_date
            AND rn.created_at <= hz.snapshot_ts - interval '7 days'
            AND (rn.canceled_at IS NULL OR rn.canceled_at > hz.snapshot_ts - interval '7 days')
        ) AS otb_rooms_7d_ago,
        -- same time last year
        count(*) FILTER (
            WHERE rn.stay_date = hz.stay_date - 364
            AND rn.created_at <= hz.snapshot_ts - interval '364 days'
            AND (rn.canceled_at IS NULL OR rn.canceled_at > hz.snapshot_ts - interval '364 days')
        ) AS stly_otb_rooms,
        coalesce(sum(rn.room_revenue) FILTER (
            WHERE rn.stay_date = hz.stay_date - 364
            AND rn.created_at <= hz.snapshot_ts - interval '364 days'
            AND (rn.canceled_at IS NULL OR rn.canceled_at > hz.snapshot_ts - interval '364 days')
        ), 0) AS stly_otb_revenue,
        -- last year's final result
        count(*) FILTER (WHERE rn.stay_date = hz.stay_date - 364 AND rn.is_sold) AS ly_final_rooms
    FROM horizon AS hz
    LEFT JOIN core.fct_room_night AS rn
        ON
            hz.hotel_id = rn.hotel_id
            AND rn.stay_date IN (hz.stay_date, hz.stay_date - 364)
    GROUP BY hz.hotel_id, hz.stay_date
)

SELECT
    hz.snapshot_date,
    hz.hotel_id,
    hz.hotel_name,
    hz.stay_date,
    hz.stay_date - hz.snapshot_date AS days_out,
    hz.total_rooms AS rooms_available,
    p.otb_rooms,
    p.otb_revenue,
    p.otb_rooms_7d_ago,
    p.otb_rooms - p.otb_rooms_7d_ago AS pickup_7d,
    p.stly_otb_rooms,
    p.stly_otb_revenue,
    p.ly_final_rooms
FROM horizon AS hz
INNER JOIN pace AS p ON hz.hotel_id = p.hotel_id AND hz.stay_date = p.stay_date;
