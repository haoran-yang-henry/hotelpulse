-- Share of visits with a payment attempt that ended with a booking
SELECT round(sum(booked)::numeric / nullif(sum(attempted_payment), 0), 4) AS payment_success_rate
FROM marts.web_funnel_daily
WHERE
    {{period}}
    AND {{device}}
    AND {{channel}}
