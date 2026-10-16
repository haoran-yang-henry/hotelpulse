-- Reviews of this batch's export files; an edited review replaces the earlier version.
INSERT INTO staging.reviews (
    review_id, platform, hotel_code, confirmation_code, posted_at, rating, title, review_text,
    topics, _batch_id
)
SELECT DISTINCT ON (r.payload ->> 'review_id')
    r.payload ->> 'review_id' AS review_id,
    r.payload ->> 'platform' AS platform,
    r.payload ->> 'hotel_code' AS hotel_code,
    nullif(r.payload ->> 'confirmation_code', '') AS confirmation_code,
    (r.payload ->> 'posted_at')::timestamptz AS posted_at,
    (r.payload ->> 'rating')::numeric(3, 1) AS rating,
    r.payload ->> 'title' AS title,
    r.payload ->> 'text' AS review_text,
    coalesce(r.payload -> 'topics', '[]'::jsonb) AS topics,
    r._batch_id
FROM raw.reviews AS r
WHERE r._batch_id = '{{ run_id }}'
ORDER BY r.payload ->> 'review_id' ASC, r._file DESC, r._line DESC
ON CONFLICT (review_id) DO UPDATE SET
    platform = excluded.platform,
    hotel_code = excluded.hotel_code,
    confirmation_code = excluded.confirmation_code,
    posted_at = excluded.posted_at,
    rating = excluded.rating,
    title = excluded.title,
    review_text = excluded.review_text,
    topics = excluded.topics,
    _batch_id = excluded._batch_id,
    _loaded_at = now();
