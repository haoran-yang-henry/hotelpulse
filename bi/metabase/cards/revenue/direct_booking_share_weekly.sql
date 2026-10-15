-- Booking intake by booking week: share of new bookings made direct and on the website
SELECT
    date_trunc('week', booked_date)::date AS booking_week,
    round(sum(bookings) FILTER (WHERE is_direct)::numeric / nullif(sum(bookings), 0), 4)
        AS direct_share_of_bookings,
    round(
        sum(bookings) FILTER (WHERE channel_code = 'website')::numeric / nullif(sum(bookings), 0), 4
    ) AS website_share_of_bookings
FROM marts.channel_bookings_daily
WHERE
    {{hotel}}
    AND {{period}}
    AND booked_date < date_trunc('week', current_date)
GROUP BY 1
ORDER BY 1
