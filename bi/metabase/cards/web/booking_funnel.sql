-- Closed booking funnel: visits reaching each step
WITH totals AS (
    SELECT
        sum(sessions) AS visits,
        sum(searched) AS searched,
        sum(selected_room) AS selected_room,
        sum(attempted_payment) AS attempted_payment,
        sum(booked) AS booked
    FROM marts.web_funnel_daily
    WHERE
        {{period}}
        AND {{device}}
        AND {{channel}}
)

SELECT
    v.step,
    v.visits
FROM totals AS t
CROSS JOIN
    LATERAL (
        VALUES
        (1, 'Visit', t.visits),
        (2, 'Searched availability', t.searched),
        (3, 'Selected a room', t.selected_room),
        (4, 'Attempted payment', t.attempted_payment),
        (5, 'Booked', t.booked)
    ) AS v (step_order, step, visits)
ORDER BY v.step_order
