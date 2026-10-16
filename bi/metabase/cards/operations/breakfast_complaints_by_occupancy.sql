-- Share of reviews complaining about breakfast, by hotel occupancy during the guest's stay
SELECT
    occupancy_band,
    round(avg(breakfast_complaint::int), 4) AS breakfast_complaint_rate,
    count(*) AS reviews
FROM marts.guest_reviews
WHERE
    occupancy_band IS NOT NULL
    AND {{hotel}}
    AND {{period}}
GROUP BY occupancy_band
ORDER BY min(stay_occupancy)
