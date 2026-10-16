-- Share of feedback that rated an explanation helpful
SELECT round(avg(helpful::int), 4) AS helpful_share
FROM insight.feedback
WHERE {{period}}
