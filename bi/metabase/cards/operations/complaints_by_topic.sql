-- Negative mentions per 100 reviews, by topic
WITH mentions AS (
    SELECT
        review_id,
        topic,
        sentiment
    FROM marts.review_topics
    WHERE {{hotel}} AND {{period}}
)

SELECT
    topic,
    round(
        100.0 * count(*) FILTER (WHERE sentiment = 'negative')
        / (SELECT count(DISTINCT m.review_id) FROM mentions AS m),
        1
    ) AS complaints_per_100_reviews
FROM mentions
GROUP BY topic
ORDER BY complaints_per_100_reviews DESC
