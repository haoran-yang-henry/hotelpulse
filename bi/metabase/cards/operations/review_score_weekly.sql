-- Weekly average review score per hotel (complete weeks only)
SELECT
    date_trunc('week', posted_date)::date AS week,
    hotel_name,
    round(avg(rating), 2) AS average_review_score
FROM marts.guest_reviews
WHERE
    {{hotel}}
    AND {{period}}
    AND posted_date < date_trunc('week', current_date)
GROUP BY week, hotel_name
ORDER BY week, hotel_name
