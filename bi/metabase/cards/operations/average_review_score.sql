-- Average review score (1-10) of the reviews posted in the selected period
SELECT round(avg(rating), 2) AS average_review_score
FROM marts.guest_reviews
WHERE {{hotel}} AND {{period}}
