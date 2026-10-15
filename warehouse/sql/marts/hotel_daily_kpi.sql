-- Daily KPIs per hotel on stay-date basis, plus the same weekday last year (-364 days).
-- Full rebuild in one transaction: readers keep seeing the previous version until commit.

DELETE FROM marts.hotel_daily_kpi;

INSERT INTO marts.hotel_daily_kpi (
    hotel_id, hotel_name, stay_date, is_future, rooms_available, rooms_sold, direct_rooms_sold,
    room_revenue, commission_cost, net_room_revenue, occupancy, adr, revpar, direct_share,
    arrivals, departures, ly_rooms_sold, ly_room_revenue, ly_occupancy, ly_adr, ly_revpar
)
WITH bounds AS (
    -- each hotel is reported from its PMS go-live (earlier data is incomplete) up to the
    -- furthest night on the books
    SELECT
        h.hotel_id,
        h.pms_live_date AS first_day,
        max(rn.stay_date) AS last_day
    FROM core.dim_hotel AS h
    INNER JOIN core.fct_room_night AS rn ON h.hotel_id = rn.hotel_id
    WHERE rn.is_sold
    GROUP BY h.hotel_id, h.pms_live_date
),

calendar AS (
    SELECT
        h.hotel_id,
        h.hotel_name,
        h.total_rooms,
        h.timezone,
        d.date_day AS stay_date
    FROM core.dim_hotel AS h
    INNER JOIN bounds AS b ON h.hotel_id = b.hotel_id
    INNER JOIN core.dim_date AS d ON d.date_day BETWEEN b.first_day AND b.last_day
),

sold AS (
    SELECT
        rn.hotel_id,
        rn.stay_date,
        count(*) AS rooms_sold,
        count(*) FILTER (WHERE c.is_direct) AS direct_rooms_sold,
        sum(rn.room_revenue) AS room_revenue,
        sum(rn.commission_cost) AS commission_cost
    FROM core.fct_room_night AS rn
    INNER JOIN core.dim_channel AS c ON rn.channel_code = c.channel_code
    WHERE rn.is_sold
    GROUP BY rn.hotel_id, rn.stay_date
),

movements AS (
    SELECT
        hotel_id,
        movement_date,
        count(*) FILTER (WHERE kind = 'arrival') AS arrivals,
        count(*) FILTER (WHERE kind = 'departure') AS departures
    FROM (
        SELECT
            hotel_id,
            arrival_date AS movement_date,
            'arrival' AS kind
        FROM core.fct_reservation
        WHERE NOT is_canceled AND NOT is_no_show AND nights > 0
        UNION ALL
        SELECT
            hotel_id,
            departure_date AS movement_date,
            'departure' AS kind
        FROM core.fct_reservation
        WHERE NOT is_canceled AND NOT is_no_show AND nights > 0
    ) AS m
    GROUP BY hotel_id, movement_date
),

daily AS (
    SELECT
        cal.hotel_id,
        cal.hotel_name,
        cal.stay_date,
        cal.stay_date >= (now() AT TIME ZONE cal.timezone)::date AS is_future,
        cal.total_rooms AS rooms_available,
        coalesce(s.rooms_sold, 0) AS rooms_sold,
        coalesce(s.direct_rooms_sold, 0) AS direct_rooms_sold,
        coalesce(s.room_revenue, 0) AS room_revenue,
        coalesce(s.commission_cost, 0) AS commission_cost,
        coalesce(mv.arrivals, 0) AS arrivals,
        coalesce(mv.departures, 0) AS departures
    FROM calendar AS cal
    LEFT JOIN sold AS s ON cal.hotel_id = s.hotel_id AND cal.stay_date = s.stay_date
    LEFT JOIN movements AS mv ON cal.hotel_id = mv.hotel_id AND cal.stay_date = mv.movement_date
),

kpi AS (
    SELECT
        *,
        room_revenue - commission_cost AS net_room_revenue,
        round(rooms_sold::numeric / rooms_available, 4) AS occupancy,
        round(room_revenue / nullif(rooms_sold, 0), 2) AS adr,
        round(room_revenue / rooms_available, 2) AS revpar,
        round(direct_rooms_sold::numeric / nullif(rooms_sold, 0), 4) AS direct_share
    FROM daily
)

SELECT
    k.hotel_id,
    k.hotel_name,
    k.stay_date,
    k.is_future,
    k.rooms_available,
    k.rooms_sold,
    k.direct_rooms_sold,
    k.room_revenue,
    k.commission_cost,
    k.net_room_revenue,
    k.occupancy,
    k.adr,
    k.revpar,
    k.direct_share,
    k.arrivals,
    k.departures,
    ly.rooms_sold AS ly_rooms_sold,
    ly.room_revenue AS ly_room_revenue,
    ly.occupancy AS ly_occupancy,
    ly.adr AS ly_adr,
    ly.revpar AS ly_revpar
FROM kpi AS k
LEFT JOIN kpi AS ly ON k.hotel_id = ly.hotel_id AND ly.stay_date = k.stay_date - 364;
