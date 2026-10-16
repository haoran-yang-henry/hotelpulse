-- LLM tokens used for explanations per day
SELECT
    (created_at AT TIME ZONE 'Europe/Lisbon')::date AS day,
    sum(prompt_tokens) AS prompt_tokens,
    sum(completion_tokens) AS completion_tokens
FROM insight.explanations
WHERE {{period}}
GROUP BY day
ORDER BY day
