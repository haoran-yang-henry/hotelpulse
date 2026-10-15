-- Sessionization, incremental per visitor (ADR-0012): every visitor seen in this batch gets
-- all of their sessions rebuilt, which is exactly what a full rebuild would produce for them.
-- A session ends after 30 minutes of inactivity (GA4 definition). Bots are excluded.

CREATE TEMP TABLE affected_visitors ON COMMIT DROP AS
SELECT DISTINCT anonymous_id
FROM staging.web_events
WHERE _batch_id = '{{ run_id }}' AND NOT is_bot;

DELETE FROM core.fct_web_event AS e
USING affected_visitors AS a
WHERE e.anonymous_id = a.anonymous_id;

DELETE FROM core.fct_web_session AS s
USING affected_visitors AS a
WHERE s.anonymous_id = a.anonymous_id;

CREATE TEMP TABLE sessionized ON COMMIT DROP AS
WITH ordered AS (
    SELECT
        e.*,
        lag(e.derived_ts) OVER (PARTITION BY e.anonymous_id ORDER BY e.derived_ts, e.event_id) AS previous_ts
    FROM staging.web_events AS e
    INNER JOIN affected_visitors AS a ON e.anonymous_id = a.anonymous_id
    WHERE NOT e.is_bot
),

numbered AS (
    SELECT
        *,
        sum(
            CASE WHEN previous_ts IS NULL OR derived_ts - previous_ts > interval '30 minutes' THEN 1 ELSE 0 END
        ) OVER (PARTITION BY anonymous_id ORDER BY derived_ts, event_id) AS visitor_session_number
    FROM ordered
)

SELECT
    *,
    md5(
        anonymous_id::text || ':'
        || first_value(event_id) OVER (
            PARTITION BY anonymous_id, visitor_session_number ORDER BY derived_ts, event_id
        )::text
    )::uuid AS session_id,
    row_number() OVER (
        PARTITION BY anonymous_id, visitor_session_number ORDER BY derived_ts, event_id
    ) AS event_seq
FROM numbered;

INSERT INTO core.fct_web_event (
    event_id, session_id, anonymous_id, event_seq, event_name, event_ts, page_path, page_type,
    hotel_code, confirmation_code, value, error_code, _batch_id
)
SELECT
    event_id,
    session_id,
    anonymous_id,
    event_seq,
    event_name,
    derived_ts,
    page_path,
    page_type,
    hotel_code,
    confirmation_code,
    value,
    error_code,
    '{{ run_id }}'
FROM sessionized;

INSERT INTO core.fct_web_session (
    session_id, anonymous_id, visitor_session_number, session_start, session_end, session_date,
    duration_s, events, page_views, landing_path, source, medium, campaign, channel_group,
    device_type, locale, hotel_code, reached_search, reached_room_selection, reached_payment,
    payment_failed, booked, confirmation_code, booking_value, _batch_id
)
WITH landing AS (
    -- traffic source of a visit = UTM parameters of its first hit, else the external referrer
    SELECT DISTINCT ON (session_id)
        session_id,
        page_path AS landing_path,
        utm_campaign,
        device_type,
        locale,
        coalesce(
            utm_source,
            CASE WHEN referrer_host <> substring(page_url FROM '^https?://([^/:?#]+)') THEN referrer_host END,
            '(direct)'
        ) AS source,
        coalesce(
            utm_medium,
            CASE
                WHEN referrer_host = substring(page_url FROM '^https?://([^/:?#]+)') THEN '(none)'
                WHEN referrer_host ~ '(^|\.)(google|bing|duckduckgo|yahoo|ecosia)\.' THEN 'organic'
                WHEN referrer_host IS NOT NULL THEN 'referral'
            END,
            '(none)'
        ) AS medium
    FROM sessionized
    ORDER BY session_id ASC, event_seq ASC
)

SELECT
    s.session_id,
    s.anonymous_id,
    s.visitor_session_number,
    min(s.derived_ts) AS session_start,
    max(s.derived_ts) AS session_end,
    (min(s.derived_ts) AT TIME ZONE 'Europe/Lisbon')::date AS session_date,
    round(extract(EPOCH FROM max(s.derived_ts) - min(s.derived_ts)))::int AS duration_s,
    count(*) AS events,
    count(*) FILTER (WHERE s.event_name = 'page_view') AS page_views,
    l.landing_path,
    l.source,
    l.medium,
    l.utm_campaign AS campaign,
    CASE
        WHEN l.medium = 'cpc' THEN 'Paid search'
        WHEN l.medium = 'metasearch' THEN 'Metasearch'
        WHEN l.medium = 'email' THEN 'Email'
        WHEN l.medium = 'social' OR l.source ~ '(instagram|facebook|tiktok|pinterest)' THEN 'Social'
        WHEN l.medium = 'organic' THEN 'Organic search'
        WHEN l.medium = 'referral' THEN 'Referral'
        ELSE 'Direct'
    END AS channel_group,
    l.device_type,
    l.locale,
    (array_agg(s.hotel_code ORDER BY s.event_seq) FILTER (WHERE s.hotel_code IS NOT NULL))[1] AS hotel_code,
    bool_or(s.event_name = 'search_availability') AS reached_search,
    bool_or(s.event_name IN ('select_room', 'begin_checkout')) AS reached_room_selection,
    bool_or(s.event_name = 'payment_submitted') AS reached_payment,
    bool_or(s.event_name = 'payment_failed') AS payment_failed,
    bool_or(s.event_name = 'booking_confirmed') AS booked,
    max(s.confirmation_code) FILTER (WHERE s.event_name = 'booking_confirmed') AS confirmation_code,
    max(s.value) FILTER (WHERE s.event_name = 'booking_confirmed') AS booking_value,
    '{{ run_id }}' AS _batch_id
FROM sessionized AS s
INNER JOIN landing AS l ON s.session_id = l.session_id
GROUP BY
    s.session_id, s.anonymous_id, s.visitor_session_number, l.landing_path, l.source, l.medium,
    l.utm_campaign, l.device_type, l.locale;
