-- Booking funnel: sessions reaching each step, per day, device, traffic channel and hotel.
-- Steps are cumulative ("closed funnel"): reaching a later step implies the earlier ones, so a
-- single lost event (e.g. rejected by the collector) cannot break the funnel.

DELETE FROM marts.web_funnel_daily;

INSERT INTO marts.web_funnel_daily (
    session_date, device_type, channel_group, hotel_code, sessions, searched, selected_room,
    attempted_payment, failed_payment, booked, booking_value
)
SELECT
    session_date,
    device_type,
    channel_group,
    coalesce(hotel_code, '(none)') AS hotel_code,
    count(*) AS sessions,
    count(*) FILTER (
        WHERE reached_search OR reached_room_selection OR reached_payment OR payment_failed OR booked
    ) AS searched,
    count(*) FILTER (
        WHERE reached_room_selection OR reached_payment OR payment_failed OR booked
    ) AS selected_room,
    count(*) FILTER (WHERE reached_payment OR payment_failed OR booked) AS attempted_payment,
    count(*) FILTER (WHERE payment_failed) AS failed_payment,
    count(*) FILTER (WHERE booked) AS booked,
    coalesce(sum(booking_value) FILTER (WHERE booked), 0) AS booking_value
FROM core.fct_web_session
GROUP BY session_date, device_type, channel_group, coalesce(hotel_code, '(none)');
