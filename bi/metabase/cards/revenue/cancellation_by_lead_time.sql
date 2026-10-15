-- Cancellation rate by booking lead time (bookings made in the selected period)
SELECT
    CASE
        WHEN core.fct_reservation.lead_time_days <= 7 THEN '0-7 days'
        WHEN core.fct_reservation.lead_time_days <= 30 THEN '8-30 days'
        WHEN core.fct_reservation.lead_time_days <= 90 THEN '31-90 days'
        WHEN core.fct_reservation.lead_time_days <= 180 THEN '91-180 days'
        ELSE '181+ days'
    END AS lead_time,
    count(*) AS bookings,
    round(avg(core.fct_reservation.is_canceled::int), 4) AS cancellation_rate
FROM core.fct_reservation
INNER JOIN core.dim_hotel ON core.fct_reservation.hotel_id = core.dim_hotel.hotel_id
WHERE
    {{hotel}}
    AND {{period}}
GROUP BY lead_time
ORDER BY min(core.fct_reservation.lead_time_days)
