-- Weekly payment success rate per device type: drops point to a broken checkout.
-- Weeks with fewer than 5 payment attempts on a device are left out (too noisy).
SELECT
    date_trunc('week', session_date)::date AS week,
    device_type,
    round(sum(booked)::numeric / nullif(sum(attempted_payment), 0), 4) AS payment_success_rate
FROM marts.web_funnel_daily
WHERE
    {{period}}
    AND {{device}}
    AND {{channel}}
    AND session_date < date_trunc('week', current_date)
GROUP BY week, device_type
HAVING sum(attempted_payment) >= 5
ORDER BY week, device_type
