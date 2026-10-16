-- Share of AI-written explanations whose numbers all matched the data
SELECT round(avg(verified::int), 4) AS verified_share
FROM insight.explanations
WHERE
    {{period}}
    AND mode = 'llm'
