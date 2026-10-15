-- Parse this batch's raw tracking events:
-- * duplicates (client retries) collapse to one row per event_id - the first delivery wins,
--   also across batches (ON CONFLICT DO NOTHING);
-- * device clocks are corrected: derived_ts = collector_ts - (sent_at - event_ts);
-- * devices and bots are classified from the user agent, UTM parameters parsed from the URL.
INSERT INTO staging.web_events (
    event_id, event_name, anonymous_id, session_hint, event_ts_device, sent_at_device,
    collector_ts, derived_ts, clock_skew_s, page_url, page_path, page_type, referrer,
    referrer_host, utm_source, utm_medium, utm_campaign, locale, user_agent, device_type, is_bot,
    hotel_code, confirmation_code, value, error_code, properties, _batch_id
)
SELECT DISTINCT ON (e.event_id)
    e.event_id,
    e.event_name,
    e.anonymous_id,
    e.session_hint,
    e.event_ts_device,
    e.sent_at_device,
    e.collector_ts,
    e.collector_ts - (e.sent_at_device - e.event_ts_device) AS derived_ts,
    round(extract(EPOCH FROM e.sent_at_device - e.collector_ts))::int AS clock_skew_s,
    e.page_url,
    substring(e.page_url FROM '^https?://[^/]+(/[^?#]*)') AS page_path,
    e.properties ->> 'page_type' AS page_type,
    e.referrer,
    substring(e.referrer FROM '^https?://([^/:?#]+)') AS referrer_host,
    substring(e.page_url FROM '[?&]utm_source=([^&#]+)') AS utm_source,
    substring(e.page_url FROM '[?&]utm_medium=([^&#]+)') AS utm_medium,
    substring(e.page_url FROM '[?&]utm_campaign=([^&#]+)') AS utm_campaign,
    e.locale,
    e.user_agent,
    CASE
        WHEN e.user_agent ~* '(bot|spider|crawl|headless)' THEN 'bot'
        WHEN e.user_agent ~* '(ipad|tablet)' THEN 'tablet'
        WHEN e.user_agent ~* '(mobi|iphone|android)' THEN 'mobile'
        ELSE 'desktop'
    END AS device_type,
    coalesce(e.user_agent ~* '(bot|spider|crawl|headless)', FALSE) AS is_bot,
    e.properties ->> 'hotel_code' AS hotel_code,
    e.properties ->> 'confirmation_code' AS confirmation_code,
    (e.properties ->> 'value')::numeric(12, 2) AS value,
    e.properties ->> 'error_code' AS error_code,
    e.properties,
    e._batch_id
FROM (
    SELECT
        (r.payload ->> 'event_id')::uuid AS event_id,
        r.payload ->> 'event_name' AS event_name,
        (r.payload ->> 'anonymous_id')::uuid AS anonymous_id,
        r.payload ->> 'session_hint' AS session_hint,
        (r.payload ->> 'event_ts')::timestamptz AS event_ts_device,
        (r.payload ->> 'sent_at')::timestamptz AS sent_at_device,
        (r.payload ->> 'collector_ts')::timestamptz AS collector_ts,
        r.payload ->> 'page_url' AS page_url,
        r.payload ->> 'referrer' AS referrer,
        r.payload ->> 'locale' AS locale,
        r.payload ->> 'user_agent' AS user_agent,
        coalesce(r.payload -> 'properties', '{}'::jsonb) AS properties,
        r._batch_id
    FROM raw.web_events AS r
    WHERE r._batch_id = '{{ run_id }}'
) AS e
ORDER BY e.event_id ASC, e.collector_ts ASC
ON CONFLICT (event_id) DO NOTHING;
