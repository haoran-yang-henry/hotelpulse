-- Reviews linked to the stay they are about: the hotel's average occupancy during the stay
-- shows whether guests of a full house rate (and complain) differently.

DELETE FROM marts.review_topics;
DELETE FROM marts.guest_reviews;

INSERT INTO marts.guest_reviews (
    review_id, platform, hotel_id, hotel_name, posted_date, rating, reservation_id,
    arrival_date, departure_date, channel_group, stay_occupancy, occupancy_band,
    negative_topics, breakfast_complaint
)
WITH stay_occupancy AS (
    SELECT
        r.reservation_id,
        avg(k.occupancy) AS occupancy
    FROM core.fct_reservation AS r
    INNER JOIN marts.hotel_daily_kpi AS k
        ON
            r.hotel_id = k.hotel_id
            AND r.arrival_date <= k.stay_date
            AND r.departure_date > k.stay_date
    WHERE r.confirmation_code IN (SELECT confirmation_code FROM staging.reviews)
    GROUP BY r.reservation_id
)

SELECT
    v.review_id,
    v.platform,
    h.hotel_id,
    h.hotel_name,
    (v.posted_at AT TIME ZONE h.timezone)::date AS posted_date,
    v.rating,
    r.reservation_id,
    r.arrival_date,
    r.departure_date,
    c.channel_group,
    round(o.occupancy, 4) AS stay_occupancy,
    CASE
        WHEN o.occupancy IS NULL THEN NULL
        WHEN o.occupancy < 0.70 THEN 'below 70 %'
        WHEN o.occupancy < 0.80 THEN '70-80 %'
        WHEN o.occupancy < 0.90 THEN '80-90 %'
        ELSE '90 % and above'
    END AS occupancy_band,
    (
        SELECT count(*) FROM jsonb_array_elements(v.topics) AS t
        WHERE t ->> 'sentiment' = 'negative'
    ) AS negative_topics,
    coalesce(v.topics @> '[{"topic": "breakfast", "sentiment": "negative"}]', FALSE)
        AS breakfast_complaint
FROM staging.reviews AS v
INNER JOIN core.dim_hotel AS h ON v.hotel_code = h.hotel_code
LEFT JOIN core.fct_reservation AS r ON v.confirmation_code = r.confirmation_code
LEFT JOIN core.dim_channel AS c ON r.channel_code = c.channel_code
LEFT JOIN stay_occupancy AS o ON r.reservation_id = o.reservation_id
WHERE (v.posted_at AT TIME ZONE h.timezone)::date >= h.pms_live_date;

INSERT INTO marts.review_topics (
    review_id, hotel_id, hotel_name, posted_date, topic, sentiment, occupancy_band
)
SELECT DISTINCT ON (g.review_id, t ->> 'topic')
    g.review_id,
    g.hotel_id,
    g.hotel_name,
    g.posted_date,
    t ->> 'topic' AS topic,
    t ->> 'sentiment' AS sentiment,
    g.occupancy_band
FROM marts.guest_reviews AS g
INNER JOIN staging.reviews AS v ON g.review_id = v.review_id
CROSS JOIN LATERAL jsonb_array_elements(v.topics) AS t
ORDER BY g.review_id ASC, t ->> 'topic' ASC;
