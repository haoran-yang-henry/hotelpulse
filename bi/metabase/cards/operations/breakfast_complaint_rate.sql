-- Share of reviews that complain about breakfast
SELECT round(avg(breakfast_complaint::int), 4) AS breakfast_complaint_rate
FROM marts.guest_reviews
WHERE {{hotel}} AND {{period}}
