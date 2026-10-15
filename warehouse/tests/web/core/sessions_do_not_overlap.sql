-- severity: error
-- description: Sessions of the same visitor never overlap in time.
SELECT
    anonymous_id,
    session_id,
    session_start,
    previous_end
FROM (
    SELECT
        anonymous_id,
        session_id,
        session_start,
        lag(session_end) OVER (PARTITION BY anonymous_id ORDER BY session_start) AS previous_end
    FROM core.fct_web_session
) AS s
WHERE session_start <= previous_end
