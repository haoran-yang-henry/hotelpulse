-- Website bookings credited to each channel under first-touch vs. last-touch attribution
SELECT
    channel,
    attribution_model,
    count(*) AS bookings
FROM (
    SELECT
        first_touch_channel AS channel,
        'First touch' AS attribution_model
    FROM marts.web_attribution
    WHERE {{period}}
    UNION ALL
    SELECT
        last_touch_channel AS channel,
        'Last touch' AS attribution_model
    FROM marts.web_attribution
    WHERE {{period}}
) AS touches
GROUP BY channel, attribution_model
ORDER BY channel, attribution_model
