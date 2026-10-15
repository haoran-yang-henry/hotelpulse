-- severity: error
-- description: Each funnel step has at most as many sessions as the step before.
SELECT
    session_date,
    device_type,
    channel_group,
    hotel_code
FROM marts.web_funnel_daily
WHERE NOT (
        sessions >= searched
        AND searched >= selected_room
        AND selected_room >= attempted_payment
        AND attempted_payment >= booked
    )
