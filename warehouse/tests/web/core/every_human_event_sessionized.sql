-- severity: error
-- description: Every non-bot staging event belongs to exactly one session.
SELECT
    (
        SELECT count(*) FROM staging.web_events
        WHERE NOT is_bot
    ) AS human_events,
    (SELECT count(*) FROM core.fct_web_event) AS sessionized_events
WHERE (
    SELECT count(*) FROM staging.web_events
    WHERE NOT is_bot
) <> (SELECT count(*) FROM core.fct_web_event
)
