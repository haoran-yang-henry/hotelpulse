-- Booking intake per hotel, booking date and channel: what was booked on a given day,
-- and how much of it has been canceled since.

DELETE FROM marts.channel_bookings_daily;

INSERT INTO marts.channel_bookings_daily (
    hotel_id, hotel_name, booked_date, channel_code, channel_name, channel_group, is_direct,
    bookings, room_nights, booked_revenue, canceled_bookings, avg_lead_time_days
)
SELECT
    f.hotel_id,
    h.hotel_name,
    f.booked_date,
    c.channel_code,
    c.channel_name,
    c.channel_group,
    c.is_direct,
    count(*) AS bookings,
    sum(f.nights) AS room_nights,
    sum(f.booked_revenue) AS booked_revenue,
    count(*) FILTER (WHERE f.is_canceled) AS canceled_bookings,
    round(avg(f.lead_time_days), 1) AS avg_lead_time_days
FROM core.fct_reservation AS f
INNER JOIN core.dim_hotel AS h ON f.hotel_id = h.hotel_id
INNER JOIN core.dim_channel AS c ON f.channel_code = c.channel_code
WHERE f.booked_date >= h.pms_live_date
GROUP BY f.hotel_id, h.hotel_name, f.booked_date, c.channel_code, c.channel_name, c.channel_group, c.is_direct;
