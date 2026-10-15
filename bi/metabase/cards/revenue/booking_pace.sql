-- Rooms on the books per stay week (next ~4 months) vs. same time last year and last
-- year's final result. Only complete weeks are shown so the comparison is like for like.
SELECT
    date_trunc('week', stay_date)::date AS stay_week,
    sum(otb_rooms) AS on_the_books,
    sum(stly_otb_rooms) AS same_time_last_year,
    sum(ly_final_rooms) AS last_year_final
FROM marts.booking_pace
WHERE {{hotel}}
GROUP BY 1
HAVING count(DISTINCT stay_date) = 7
ORDER BY 1
