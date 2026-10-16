-- severity: warn
-- description: Review topics carry a positive or negative sentiment.
SELECT
    r.review_id,
    t.value AS topic
FROM staging.reviews AS r
CROSS JOIN LATERAL jsonb_array_elements(r.topics) AS t
WHERE coalesce(t.value ->> 'sentiment', '') NOT IN ('positive', 'negative')
